"""3-index 하이브리드 검색 서비스.

검증된 쿼리 패턴 (세션 4):
  semantic (BM25 + semantic re-rank) + vectorQueries (content_vector)

3-index 체제에서 서비스별로 다른 인덱스 조합을 쓴다:
  - chat      : law + guide + video (3개 전부)
  - checklist : law + guide         (법정 기한·citation 근거 때문에 law 필수)
  - safecontract: law 단독          (등기부 → 조문 매칭)

아키텍처:
  parallel_search()         ← 범용 병렬 엔진 (임의의 인덱스 조합)
  ├─ parallel_search_3()    ← chat 용 얇은 wrapper
  └─ parallel_search_law_guide() ← checklist 용 얇은 wrapper

단일 인덱스 호출은 hybrid_search() 를 직접 사용 (safecontract).

Azure 미설정 또는 호출 실패 시 각 함수는 빈 값 반환 → 호출자가 로컬 폴백.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .azure_clients import (
    get_openai_client,
    get_search_client_guide,
    get_search_client_law,
    get_search_client_video,
)
from .config import get_settings

logger = logging.getLogger("movewise")

# 벡터 후보 수 (Azure가 벡터 검색에서 가져오는 raw 후보 — semantic re-rank 전 단계)
# 너무 작으면 recall 손실, 너무 크면 latency. 50은 Azure 문서 권장선.
VECTOR_K_NEIGHBORS = 50

# chat 용 기본 top-k (컨텍스트 배분)
DEFAULT_TOP_LAW_CHAT = 6
DEFAULT_TOP_GUIDE_CHAT = 4
DEFAULT_TOP_VIDEO_CHAT = 3

# checklist 용 기본 top-k (쿼리당 작게, 대신 쿼리 수가 많음)
DEFAULT_TOP_LAW_CHECKLIST = 3
DEFAULT_TOP_GUIDE_CHECKLIST = 3

# ThreadPoolExecutor 풀 타임아웃
PARALLEL_TIMEOUT_SEC = 30.0

# ============================================================
# 1. 임베딩
# ============================================================


def embed_query(text: str) -> Optional[list[float]]:
    """사용자 질문을 text-embedding-3-small 로 벡터화.

    실패 시 None 반환 → 호출자는 semantic-only 로 graceful fallback.
    """
    client = get_openai_client()
    if client is None:
        return None
    settings = get_settings()
    try:
        resp = client.embeddings.create(
            model=settings.azure_openai_embed_deployment,
            input=[text],
        )
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning(
            f"embed_query failed ({type(exc).__name__}): {exc} — semantic-only fallback"
        )
        return None


# ============================================================
# 2. 단일 인덱스 하이브리드 쿼리
# ============================================================


def hybrid_search(
    client,
    query: str,
    top: int,
    semantic_config: str,
    embedding: Optional[list[float]] = None,
    vector_field: str = "content_vector",
) -> list[dict]:
    """단일 인덱스에 semantic + vector 하이브리드 쿼리.

    embedding=None 이면 vector 쿼리 생략 (semantic-only). 이 경우에도 결과는 반환.
    top<=0 이면 호출 생략 (빈 리스트 반환).
    """
    if client is None or top <= 0:
        return []

    search_kwargs = {
        "search_text": query,
        "top": top,
        "query_type": "semantic",
        "semantic_configuration_name": semantic_config,
    }

    if embedding is not None:
        from azure.search.documents.models import VectorizedQuery

        vector_query = VectorizedQuery(
            vector=embedding,
            k_nearest_neighbors=VECTOR_K_NEIGHBORS,
            fields=vector_field,
        )
        search_kwargs["vector_queries"] = [vector_query]

    try:
        hits = list(client.search(**search_kwargs))
        return [dict(h) for h in hits]
    except Exception as exc:
        logger.warning(
            f"hybrid_search failed ({type(exc).__name__}) config={semantic_config}: {exc}"
        )
        return []


# ============================================================
# 3. 범용 병렬 엔진
# ============================================================


def parallel_search(
    query: str,
    targets: dict[str, tuple],
    embedding: Optional[list[float]] = None,
    embed_if_missing: bool = True,
) -> dict[str, list[dict]]:
    """임의의 인덱스 조합에 병렬 하이브리드 쿼리.

    Args:
        query: 검색 쿼리 텍스트
        targets: {kind_name: (client, top, semantic_config)} 형태.
                 예: {"law":   (law_client, 6, "law-semantic-config"),
                      "guide": (guide_client, 4, "guide-semantic-config")}
                 top=0 이면 해당 kind 스킵 (빈 리스트 반환).
        embedding: 미리 계산된 벡터. None 이고 embed_if_missing=True 면 내부에서 1회 호출.
        embed_if_missing: False 면 semantic-only (임베딩 호출 안 함).

    Returns:
        {kind_name: [hit dict, ...]} — targets의 모든 키에 대해 엔트리 보장.
    """
    # 1. 임베딩 준비 (1회 호출해서 모든 타겟에 재사용)
    if embedding is None and embed_if_missing:
        embedding = embed_query(query)
        if embedding is None:
            logger.info("parallel_search: semantic-only mode (no embedding)")

    results: dict[str, list[dict]] = {kind: [] for kind in targets}
    if not targets:
        return results

    # 2. 병렬 실행
    with ThreadPoolExecutor(max_workers=max(len(targets), 1)) as pool:
        future_to_kind = {
            pool.submit(
                hybrid_search,
                client,
                query,
                top,
                semantic_config,
                embedding,
            ): kind
            for kind, (client, top, semantic_config) in targets.items()
        }

        for future in as_completed(future_to_kind, timeout=PARALLEL_TIMEOUT_SEC):
            kind = future_to_kind[future]
            try:
                results[kind] = future.result()
            except Exception as exc:
                logger.warning(
                    f"parallel_search [{kind}] failed ({type(exc).__name__}): {exc}"
                )
                results[kind] = []

    summary = " ".join(f"{k}={len(v)}" for k, v in results.items())
    logger.info(
        f"parallel_search query={query!r} {summary} "
        f"embedding={'on' if embedding else 'off'}"
    )
    return results


# ============================================================
# 4. 서비스별 Wrapper
# ============================================================


def parallel_search_3(
    query: str,
    top_law: int = DEFAULT_TOP_LAW_CHAT,
    top_guide: int = DEFAULT_TOP_GUIDE_CHAT,
    top_video: int = DEFAULT_TOP_VIDEO_CHAT,
) -> tuple[list[dict], list[dict], list[dict]]:
    """챗봇용 — law/guide/video 3개 인덱스 병렬 하이브리드 쿼리.

    반환: (law_hits, guide_hits, video_hits)
    """
    settings = get_settings()
    targets = {
        "law": (
            get_search_client_law(),
            top_law,
            settings.azure_search_law_semantic_config,
        ),
        "guide": (
            get_search_client_guide(),
            top_guide,
            settings.azure_search_guide_semantic_config,
        ),
        "video": (
            get_search_client_video(),
            top_video,
            settings.azure_search_video_semantic_config,
        ),
    }
    results = parallel_search(query, targets)
    return results["law"], results["guide"], results["video"]


def parallel_search_law_guide(
    query: str,
    top_law: int = DEFAULT_TOP_LAW_CHECKLIST,
    top_guide: int = DEFAULT_TOP_GUIDE_CHECKLIST,
) -> tuple[list[dict], list[dict]]:
    """체크리스트용 — law + guide 2개 인덱스 병렬 하이브리드 쿼리.

    체크리스트 citation 이 법정 기한·과태료 조문을 정확히 인용하려면
    guide 뿐 아니라 law 조문 본문이 검색 결과에 반드시 포함돼야 함.

    반환: (law_hits, guide_hits)
    """
    settings = get_settings()
    targets = {
        "law": (
            get_search_client_law(),
            top_law,
            settings.azure_search_law_semantic_config,
        ),
        "guide": (
            get_search_client_guide(),
            top_guide,
            settings.azure_search_guide_semantic_config,
        ),
    }
    results = parallel_search(query, targets)
    return results["law"], results["guide"]