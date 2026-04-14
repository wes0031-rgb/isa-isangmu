"""Create Azure AI Search indexes and upload chunks.

Prereq:
  - AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY in .env
  - AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY (for embeddings)
  - Index A chunks: data/indexes/index_a_chunks.jsonl (run ingest_laws.py first)
  - Index B chunks: data/indexes/index_b_chunks_curated.jsonl (run curate_chunks.py first)

Usage:
  python3 upload_to_search.py [--create-indexes] [--skip-embeddings]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402

SCHEMA_DIR = ROOT / "backend" / "schemas"
INDEX_A_DATA = ROOT / "backend" / "data" / "indexes" / "index_a_chunks.jsonl"
INDEX_B_DATA = ROOT / "backend" / "data" / "indexes" / "index_b_chunks_curated.jsonl"

# Index A / B 스키마에 있는 필드만 남기고 나머지 잘라냄 (upload 시 거부 방지)
INDEX_A_FIELDS = {
    "id", "law_name", "article", "title", "content",
    "keywords", "category", "source_url", "last_updated", "content_vector",
}
INDEX_B_FIELDS = {
    "id", "parent_doc", "doc_title", "breadcrumb", "content",
    "category", "applicable_to", "contract_type", "region",
    "deadlines", "penalties", "related_laws", "source_url",
    "fetched_at", "content_vector",
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _to_iso_datetime(value: str | None) -> str | None:
    """'2026-04-13' → '2026-04-13T00:00:00Z' (Azure DateTimeOffset)."""
    if not value:
        return None
    if "T" in value:
        return value
    return f"{value}T00:00:00Z"


def _normalize_chunk(d: dict, allowed_fields: set[str], date_fields: tuple[str, ...]) -> dict:
    """스키마 필드만 남기고 날짜는 ISO로 변환."""
    out = {k: v for k, v in d.items() if k in allowed_fields}
    for df in date_fields:
        if df in out:
            out[df] = _to_iso_datetime(out[df])
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


def create_index(schema_path: Path) -> None:
    s = get_settings()
    schema = json.loads(schema_path.read_text())
    # Raw REST 직접 호출 — Azure SDK 대신 httpx 사용 (더 단순)
    import httpx

    headers = {
        "api-key": s.azure_search_api_key,
        "Content-Type": "application/json",
    }
    url = f"{s.azure_search_endpoint}/indexes/{schema['name']}?api-version=2024-07-01"
    r = httpx.put(url, headers=headers, json=schema, timeout=30)
    r.raise_for_status()
    print(f"  ✅ index created/updated: {schema['name']}")


def upload_documents(index_name: str, docs: list[dict], batch: int = 50) -> None:
    import httpx

    s = get_settings()
    headers = {
        "api-key": s.azure_search_api_key,
        "Content-Type": "application/json",
    }
    url = f"{s.azure_search_endpoint}/indexes/{index_name}/docs/index?api-version=2024-07-01"
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
    parser.add_argument("--create-indexes", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()

    s = get_settings()
    if not s.azure_ready:
        print("❌ Azure credentials not set in .env")
        sys.exit(2)

    if args.create_indexes:
        create_index(SCHEMA_DIR / "index_a_law.json")
        create_index(SCHEMA_DIR / "index_b_procedure.json")

    # Index A (법률 조문)
    raw_a = load_jsonl(INDEX_A_DATA)
    if raw_a:
        print(f"Index A: {len(raw_a)} law articles")
        # id 는 영/한 혼용이라 Azure Search key 규칙(영숫자·_·-·=) 에 맞게 변환
        index_a_docs = []
        for d in raw_a:
            safe_id = "law_" + str(hash(d["id"]) & 0xFFFFFFFFFFFFFFFF)
            d["id"] = safe_id
            index_a_docs.append(_normalize_chunk(d, INDEX_A_FIELDS, ("last_updated",)))
        if not args.skip_embeddings:
            texts = [d["content"] for d in index_a_docs]
            embeddings = []
            for i in range(0, len(texts), 16):
                batch = texts[i : i + 16]
                embeddings.extend(embed_texts(batch))
                print(f"    embedded {i + len(batch)}/{len(texts)}")
            for doc, emb in zip(index_a_docs, embeddings):
                doc["content_vector"] = emb
        upload_documents(s.azure_search_law_index, index_a_docs)

    # Index B (행정 절차)
    raw_b = load_jsonl(INDEX_B_DATA)
    if raw_b:
        print(f"Index B: {len(raw_b)} procedure chunks")
        index_b_docs = []
        for d in raw_b:
            # region 필드가 list 면 단일 문자열로
            if isinstance(d.get("region"), list):
                d["region"] = d["region"][0] if d["region"] else "전국"
            safe_id = "proc_" + str(hash(d["id"]) & 0xFFFFFFFFFFFFFFFF)
            d["id"] = safe_id
            index_b_docs.append(_normalize_chunk(d, INDEX_B_FIELDS, ("fetched_at",)))
        if not args.skip_embeddings:
            texts = [d["content"] for d in index_b_docs]
            embeddings = []
            for i in range(0, len(texts), 16):
                batch = texts[i : i + 16]
                embeddings.extend(embed_texts(batch))
                print(f"    embedded {i + len(batch)}/{len(texts)}")
            for doc, emb in zip(index_b_docs, embeddings):
                doc["content_vector"] = emb
        upload_documents(s.azure_search_procedure_index, index_b_docs)

    print()
    print("✅ done")


if __name__ == "__main__":
    main()
