"""3개 독립 인덱스(A 법률 / B 행정절차 / C 유튜브) → 단일 통합 인덱스 변환.

입력:
  backend/data/indexes/index_a_chunks.jsonl
  backend/data/indexes/index_b_chunks_curated.jsonl
  backend/data/indexes/index_c_youtube_chunks.jsonl

출력:
  backend/data/indexes/index_unified.jsonl
  backend/data/indexes/index_unified_summary.json

변환 규칙 (source_type 별):
  - law       → A 필드 매핑 + title 보존 (조문제목), law_name/article 채움
  - procedure → B 필드 그대로, doc_title → title
  - video     → C 필드 매핑, video_title → title, deep_link/timecode 보존

크로스 링크:
  - 원본 jsonl 의 related_procedures/related_videos 는 원본 ID 기반 →
    unified ID (safe hash) 로 재매핑해서 깨지지 않게 유지

Usage:
  python3 backend/scripts/unify_indexes.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.schemas.unified_index import UnifiedChunk, make_safe_id  # noqa: E402

INDEX_DIR = ROOT / "backend" / "data" / "indexes"
SRC_A = INDEX_DIR / "index_a_chunks.jsonl"
SRC_B = INDEX_DIR / "index_b_chunks_curated.jsonl"
SRC_C = INDEX_DIR / "index_c_youtube_chunks.jsonl"
OUT = INDEX_DIR / "index_unified.jsonl"
SUMMARY = INDEX_DIR / "index_unified_summary.json"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _law_to_unified(d: dict) -> UnifiedChunk:
    source_id = d["id"]
    return UnifiedChunk(
        id=make_safe_id("law", source_id),
        source_id=source_id,
        source_type="law",
        title=d.get("title") or d.get("article", ""),
        content=d["content"],
        source_url=d.get("source_url", ""),
        keywords=d.get("keywords", []),
        category=d.get("category", []),
        fetched_at=d.get("last_updated", ""),
        # 법률은 모든 가구/계약 유형에 기본 적용
        applicable_to=["자취", "신혼", "가족"],
        contract_type=["전세", "월세", "자가"],
        region="전국",
        deadlines=d.get("deadlines", []),
        # 크로스 링크: 원본 ID → 안전 ID 변환
        related_procedures=[make_safe_id("proc", p) for p in d.get("related_procedures", [])],
        related_videos=[make_safe_id("yt", v) for v in d.get("related_videos", [])],
        # 타입 특화
        law_name=d.get("law_name"),
        article=d.get("article"),
    )


def _procedure_to_unified(d: dict) -> UnifiedChunk:
    source_id = d["id"]
    return UnifiedChunk(
        id=make_safe_id("proc", source_id),
        source_id=source_id,
        source_type="procedure",
        title=d.get("doc_title") or "",
        content=d.get("content", ""),
        source_url=d.get("source_url", ""),
        keywords=[],  # B 원본에는 keywords 없음 — title 기반으로 채울 수 있지만 일단 빈 배열
        category=d.get("category", []),
        fetched_at=d.get("fetched_at", ""),
        applicable_to=d.get("applicable_to", []) or ["자취", "신혼", "가족"],
        contract_type=d.get("contract_type", []) or ["전세", "월세", "자가"],
        region=d.get("region", "전국") if isinstance(d.get("region"), str) else "전국",
        deadlines=d.get("deadlines", []),
        related_laws=d.get("related_laws", []),
        parent_doc=d.get("parent_doc"),
        breadcrumb=d.get("breadcrumb"),
        chunk_index=d.get("chunk_index"),
        chunk_total=d.get("chunk_total"),
    )


def _video_to_unified(d: dict) -> UnifiedChunk:
    source_id = d["id"]
    return UnifiedChunk(
        id=make_safe_id("yt", source_id),
        source_id=source_id,
        source_type="video",
        title=d.get("video_title", ""),
        content=d.get("content", ""),
        source_url=d.get("source_url", ""),
        deep_link=d.get("deep_link"),
        keywords=[],
        category=d.get("category", []),
        fetched_at=d.get("fetched_at", ""),
        applicable_to=d.get("applicable_to", []) or ["자취", "신혼", "가족"],
        contract_type=d.get("contract_type", []) or ["전세", "월세", "자가"],
        region=d.get("region", "전국"),
        related_laws=d.get("related_laws", []),
        video_id=d.get("video_id"),
        channel=d.get("channel"),
        start_seconds=d.get("start_seconds"),
        end_seconds=d.get("end_seconds"),
        timecode=d.get("timecode"),
    )


def main() -> None:
    raw_a = _load_jsonl(SRC_A)
    raw_b = _load_jsonl(SRC_B)
    raw_c = _load_jsonl(SRC_C)

    print(f"Source counts: A={len(raw_a)}  B={len(raw_b)}  C={len(raw_c)}")

    unified: list[UnifiedChunk] = []
    for d in raw_a:
        unified.append(_law_to_unified(d))
    for d in raw_b:
        unified.append(_procedure_to_unified(d))
    for d in raw_c:
        unified.append(_video_to_unified(d))

    # ID 충돌 검증
    ids = [u.id for u in unified]
    dup = {x for x in ids if ids.count(x) > 1}
    if dup:
        print(f"⚠️  ID 충돌 감지: {len(dup)}건 — {list(dup)[:5]}", file=sys.stderr)
        sys.exit(1)

    # jsonl 저장
    with OUT.open("w", encoding="utf-8") as f:
        for u in unified:
            f.write(json.dumps(u.model_dump(), ensure_ascii=False) + "\n")

    # 요약 저장
    by_type = {"law": 0, "procedure": 0, "video": 0}
    by_law = {}
    for u in unified:
        by_type[u.source_type] += 1
        if u.source_type == "law" and u.law_name:
            by_law[u.law_name] = by_law.get(u.law_name, 0) + 1

    summary = {
        "total": len(unified),
        "by_source_type": by_type,
        "by_law_name": dict(sorted(by_law.items(), key=lambda x: -x[1])),
        "output_file": str(OUT.relative_to(ROOT)),
        "fields": list(UnifiedChunk.model_fields.keys()),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 통합 완료: {len(unified)} chunks → {OUT.relative_to(ROOT)}")
    print(f"   law:       {by_type['law']}")
    print(f"   procedure: {by_type['procedure']}")
    print(f"   video:     {by_type['video']}")
    print(f"\n요약: {SUMMARY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
