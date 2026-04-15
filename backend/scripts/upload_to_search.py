"""Create Azure AI Search 통합 인덱스 + 단일 jsonl 업로드.

Prereq:
  - AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY in .env
  - AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY (for embeddings)
  - 통합 인덱스 파일: data/indexes/index_unified.jsonl
    (먼저 `python3 backend/scripts/unify_indexes.py` 실행 필요)

Usage:
  python3 backend/scripts/upload_to_search.py [--create-index] [--skip-embeddings]

구 버전 (3 인덱스 분리 업로드) 은 option B 채택 후 단일 인덱스로 통합.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.schemas.unified_index import UnifiedChunk, azure_index_schema  # noqa: E402

UNIFIED_DATA = ROOT / "backend" / "data" / "indexes" / "index_unified.jsonl"
UNIFIED_INDEX_NAME = "moving-unified-index"
EMBEDDING_CACHE = ROOT / "backend" / "data" / "indexes" / "index_unified_embeddings.jsonl"

# Azure Search 가 거부하는 null 필드 제외 + datetime ISO 변환용
_DATE_FIELDS = ("fetched_at",)


def load_unified() -> list[dict]:
    if not UNIFIED_DATA.exists():
        print(f"❌ {UNIFIED_DATA} 가 없습니다. 먼저 unify_indexes.py 를 실행하세요.")
        sys.exit(2)
    return [json.loads(l) for l in UNIFIED_DATA.read_text(encoding="utf-8").splitlines() if l.strip()]


def _to_iso(value):
    if not value:
        return None
    if "T" in value:
        return value
    return f"{value}T00:00:00Z"


def _prepare_for_azure(d: dict) -> dict:
    """Azure Search 업로드용 정규화.

    - null 값 필드 제거 (sparse storage 상 필수는 아니지만 upload 거부 방지)
    - 날짜 필드 ISO DateTimeOffset 변환
    - Pydantic 검증으로 타입 안전성 확보
    """
    # Pydantic 검증
    chunk = UnifiedChunk.model_validate(d)
    out = chunk.model_dump(exclude_none=True)
    for df in _DATE_FIELDS:
        if df in out:
            out[df] = _to_iso(out[df])
    # 빈 문자열 fetched_at 은 제거 (Azure DateTimeOffset 이 빈 문자열 거부)
    if out.get("fetched_at") == "T00:00:00Z":
        out.pop("fetched_at", None)
    return out


_EMBED_CLIENT = None  # lazy-init singleton — connection pool 재사용


def _get_embed_client():
    """AzureOpenAI 클라이언트 싱글턴. 내부 httpx 에 connection limit 강제.

    macOS 는 매 요청마다 새 connection 을 열면 로컬 포트가 금방 소진됨 (Errno 49).
    단일 connection 을 유지하고 재사용하는 커스텀 httpx.Client 를 주입.
    """
    global _EMBED_CLIENT
    if _EMBED_CLIENT is not None:
        return _EMBED_CLIENT

    import httpx
    from openai import AzureOpenAI

    s = get_settings()
    limits = httpx.Limits(max_keepalive_connections=1, max_connections=1)
    custom_http = httpx.Client(timeout=60, limits=limits, http2=False)
    _EMBED_CLIENT = AzureOpenAI(
        api_key=s.azure_openai_api_key,
        api_version=s.azure_openai_api_version,
        azure_endpoint=s.azure_openai_endpoint,
        http_client=custom_http,
    )
    return _EMBED_CLIENT


def embed_texts(texts: list[str]) -> list[list[float]]:
    """배치 임베딩 호출 + ConnectError 자동 재시도."""
    import time

    s = get_settings()
    client = _get_embed_client()
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            resp = client.embeddings.create(
                model=s.azure_openai_embed_deployment,
                input=texts,
            )
            return [item.embedding for item in resp.data]
        except Exception as exc:
            last_exc = exc
            name = type(exc).__name__
            if "Connect" in name or "Errno 49" in str(exc) or "APIConnectionError" in name:
                print(f"    (embed connect error, retry {attempt + 1}/4: {name})")
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
    raise last_exc  # type: ignore[misc]


def create_index() -> None:
    import httpx

    s = get_settings()
    schema = azure_index_schema(UNIFIED_INDEX_NAME)
    headers = {
        "api-key": s.azure_search_api_key,
        "Content-Type": "application/json",
    }
    url = f"{s.azure_search_endpoint}/indexes/{UNIFIED_INDEX_NAME}?api-version=2024-07-01"
    r = httpx.put(url, headers=headers, json=schema, timeout=30)
    if r.status_code >= 400:
        print(f"  ❌ HTTP {r.status_code} from Azure Search")
        try:
            import json as _json
            err = r.json()
            print(_json.dumps(err, ensure_ascii=False, indent=2))
        except Exception:
            print(r.text)
        r.raise_for_status()
    print(f"  ✅ index created/updated: {UNIFIED_INDEX_NAME}")


def upload_documents(docs: list[dict], batch: int = 20) -> None:
    """업로드 — connection pooling 으로 로컬 포트 소진 방지.

    매 요청마다 새 httpx.post() 를 쓰면 macOS 에서 수십 건만 지나도 로컬 포트가
    TIME_WAIT 으로 소진되어 Errno 49 발생. httpx.Client context manager 로
    한 connection 을 재사용하고, 배치 사이에 짧은 대기를 둬서 안정성 확보.
    """
    import time
    import httpx
    import json as _json

    s = get_settings()
    headers = {
        "api-key": s.azure_search_api_key,
        "Content-Type": "application/json",
    }
    url = f"{s.azure_search_endpoint}/indexes/{UNIFIED_INDEX_NAME}/docs/index?api-version=2024-07-01"
    total = 0
    # transport limits — 단일 connection 재사용 강제
    limits = httpx.Limits(max_keepalive_connections=1, max_connections=1)
    with httpx.Client(headers=headers, timeout=60, limits=limits, http2=False) as client:
        for i in range(0, len(docs), batch):
            chunk = docs[i : i + batch]
            payload = {
                "value": [{"@search.action": "mergeOrUpload", **d} for d in chunk],
            }
            # 간단한 재시도 (ConnectError 대응)
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    r = client.post(url, json=payload)
                    if r.status_code >= 400:
                        print(f"  ❌ HTTP {r.status_code} on batch {i//batch + 1}")
                        try:
                            print(_json.dumps(r.json(), ensure_ascii=False, indent=2)[:2000])
                        except Exception:
                            print(r.text[:2000])
                        r.raise_for_status()
                    break
                except httpx.ConnectError as exc:
                    last_exc = exc
                    print(f"    (connect error, retry {attempt + 1}/3: {exc})")
                    time.sleep(1.5)
            else:
                raise last_exc  # type: ignore[misc]
            total += len(chunk)
            print(f"    uploaded {total}/{len(docs)}")
            # 배치 간 짧은 대기 — 포트 재사용 안정화
            time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-index", action="store_true", help="인덱스 스키마 생성/업데이트")
    parser.add_argument("--skip-embeddings", action="store_true", help="벡터 임베딩 생략 (텍스트 검색만)")
    parser.add_argument("--dry-run", action="store_true", help="Azure 호출 없이 변환만 검증")
    args = parser.parse_args()

    raw = load_unified()
    print(f"Loaded {len(raw)} unified chunks from {UNIFIED_DATA.relative_to(ROOT)}")

    # Pydantic 검증 + Azure 변환
    docs = []
    by_type = {"law": 0, "procedure": 0, "video": 0}
    for d in raw:
        try:
            prepared = _prepare_for_azure(d)
            docs.append(prepared)
            by_type[prepared["source_type"]] += 1
        except Exception as e:
            print(f"❌ invalid chunk {d.get('id')}: {e}")
            sys.exit(1)

    print(f"Validated: law={by_type['law']} procedure={by_type['procedure']} video={by_type['video']}")

    if args.dry_run:
        print("dry-run — Azure 호출 없이 검증만 완료")
        return

    s = get_settings()
    if not s.azure_ready:
        print("❌ Azure credentials not set in .env")
        sys.exit(2)

    if args.create_index:
        create_index()

    if not args.skip_embeddings:
        import time as _time

        # 1) 캐시 파일 있으면 재사용 (embed 재호출 없이 디스크 로드)
        cache_map: dict[str, list[float]] = {}
        if EMBEDDING_CACHE.exists():
            print(f"Loading embedding cache from {EMBEDDING_CACHE.relative_to(ROOT)}...")
            with EMBEDDING_CACHE.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    cache_map[rec["id"]] = rec["embedding"]
            print(f"    loaded {len(cache_map)} cached embeddings")

        # 2) 누락된 것만 임베딩 호출
        missing_docs = [d for d in docs if d["id"] not in cache_map]
        if missing_docs:
            print(f"Embedding {len(missing_docs)} new contents...")
            missing_texts = [d["content"] for d in missing_docs]
            new_embeddings: list[list[float]] = []
            # 배치 크기 64 로 늘림 — 총 connection 수 감소
            BATCH = 64
            # append-mode 로 캐시 파일 열어서 계산 즉시 디스크에 저장
            EMBEDDING_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with EMBEDDING_CACHE.open("a", encoding="utf-8") as cache_f:
                for i in range(0, len(missing_texts), BATCH):
                    batch_texts = missing_texts[i : i + BATCH]
                    batch_docs = missing_docs[i : i + BATCH]
                    batch_embs = embed_texts(batch_texts)
                    new_embeddings.extend(batch_embs)
                    # 즉시 디스크에 캐시 저장 (중간에 실패해도 보존)
                    for d_, emb_ in zip(batch_docs, batch_embs):
                        cache_map[d_["id"]] = emb_
                        cache_f.write(json.dumps({"id": d_["id"], "embedding": emb_}) + "\n")
                    cache_f.flush()
                    print(f"    embedded {i + len(batch_texts)}/{len(missing_texts)}  (cached)")
                    _time.sleep(0.05)

        # 3) docs 에 벡터 주입
        for doc in docs:
            doc["content_vector"] = cache_map[doc["id"]]

        # 4) 임베딩 ↔ 업로드 사이 대기 — macOS TIME_WAIT 포트 회복
        if missing_docs:
            wait_sec = 120
            print(f"\n⏳ Waiting {wait_sec}s for local TCP ports to recover (TIME_WAIT drain)...")
            _time.sleep(wait_sec)
            print("    ports recovered, starting upload")

    upload_documents(docs)
    print("\n✅ done")


if __name__ == "__main__":
    main()
