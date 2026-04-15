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


def embed_texts(texts: list[str]) -> list[list[float]]:
    from openai import AzureOpenAI

    s = get_settings()
    client = AzureOpenAI(
        api_key=s.azure_openai_api_key,
        api_version=s.azure_openai_api_version,
        azure_endpoint=s.azure_openai_endpoint,
    )
    resp = client.embeddings.create(
        model=s.azure_openai_embed_deployment,
        input=texts,
    )
    return [item.embedding for item in resp.data]


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
    r.raise_for_status()
    print(f"  ✅ index created/updated: {UNIFIED_INDEX_NAME}")


def upload_documents(docs: list[dict], batch: int = 50) -> None:
    import httpx

    s = get_settings()
    headers = {
        "api-key": s.azure_search_api_key,
        "Content-Type": "application/json",
    }
    url = f"{s.azure_search_endpoint}/indexes/{UNIFIED_INDEX_NAME}/docs/index?api-version=2024-07-01"
    total = 0
    for i in range(0, len(docs), batch):
        chunk = docs[i : i + batch]
        payload = {
            "value": [{"@search.action": "mergeOrUpload", **d} for d in chunk],
        }
        r = httpx.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        total += len(chunk)
        print(f"    uploaded {total}/{len(docs)}")


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
        print("Embedding contents...")
        texts = [d["content"] for d in docs]
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), 16):
            batch_texts = texts[i : i + 16]
            embeddings.extend(embed_texts(batch_texts))
            print(f"    embedded {i + len(batch_texts)}/{len(texts)}")
        for doc, emb in zip(docs, embeddings):
            doc["content_vector"] = emb

    upload_documents(docs)
    print("\n✅ done")


if __name__ == "__main__":
    main()
