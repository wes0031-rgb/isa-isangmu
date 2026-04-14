"""Apply curation filter to index_b_chunks.jsonl.

Excludes documents that are out of 이사이상무 scope (집 구하기, 계약서, 경매, 세금 등)
and produces the final curated chunks file for Azure AI Search.
"""
from __future__ import annotations

import json
from pathlib import Path

IN_FILE = Path("/Users/sa/Desktop/2차프로젝트/backend/data/indexes/index_b_chunks.jsonl")
OUT_FILE = Path("/Users/sa/Desktop/2차프로젝트/backend/data/indexes/index_b_chunks_curated.jsonl")
SUMMARY_FILE = Path("/Users/sa/Desktop/2차프로젝트/backend/data/indexes/index_b_curated_summary.json")

# 🔴 Out of scope (계약 전 ~ 계약 시점, 매매, 자금 등)
EXCLUDE_DOCS = {
    # easylaw-666 (이사 카테고리)의 집 구하기 / 계약 / 세금 / 등기
    "easylaw-666-1-1-1",  # 집 구하기
    "easylaw-666-1-1-2",  # 분양 및 경매하기
    "easylaw-666-1-1-3",  # 이사할 곳 주변 조사하기
    "easylaw-666-1-2-1",  # 대출알아보기
    "easylaw-666-1-3-1",  # 집 내놓기 및 비용회수하기
    "easylaw-666-2-1-1",  # 중개보수 등 확인하기
    "easylaw-666-2-1-2",  # 계약서 작성하기
    "easylaw-666-2-1-3",  # 임대차 권리·의무 확인 (계약 시점)
    "easylaw-666-2-2-1",  # 잔금정산하기
    "easylaw-666-2-2-2",  # 부동산 거래 신고
    "easylaw-666-2-2-3",  # 등기하기
    "easylaw-666-2-2-4",  # 매매 세금
    "easylaw-666-2-2-5",  # 임대 세금
    "easylaw-666-2-3-1",  # 주택 수리하기

    # easylaw-629 (주택임대차 카테고리) 중 out
    "easylaw-629-2-2-2",  # 임대차계약서 작성 (계약서 제외 원칙)
    "easylaw-629-2-2-3",  # 부동산 개업공인중개사 책임
    "easylaw-629-2-2-4",  # 전월세자금 대출
    "easylaw-629-5-2-3",  # 집행권원 확보
    "easylaw-629-5-2-4",  # 강제경매 신청
    "easylaw-629-5-2-5",  # 배당요구
}


def main() -> None:
    kept = []
    excluded = []
    excluded_doc_ids: set[str] = set()

    with IN_FILE.open(encoding="utf-8") as fp:
        for line in fp:
            rec = json.loads(line)
            parent = rec["parent_doc"]
            if parent in EXCLUDE_DOCS:
                excluded.append(rec)
                excluded_doc_ids.add(parent)
            else:
                kept.append(rec)

    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for rec in kept:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Summary
    kept_docs = {r["parent_doc"] for r in kept}
    from collections import Counter

    cats = Counter()
    for r in kept:
        for c in r["category"]:
            cats[c] += 1

    summary = {
        "input_chunks": len(kept) + len(excluded),
        "kept_chunks": len(kept),
        "excluded_chunks": len(excluded),
        "input_docs": len(kept_docs) + len(excluded_doc_ids),
        "kept_docs": len(kept_docs),
        "excluded_docs": sorted(excluded_doc_ids),
        "chunks_with_deadline": sum(1 for r in kept if r["deadlines"]),
        "chunks_with_penalty": sum(1 for r in kept if r["penalties"]),
        "chunks_with_law": sum(1 for r in kept if r["related_laws"]),
        "category_distribution": dict(cats.most_common()),
    }
    SUMMARY_FILE.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✅ kept {len(kept)} / {len(kept) + len(excluded)} chunks "
          f"(excluded {len(excluded)})")
    print(f"   kept docs   : {len(kept_docs)}")
    print(f"   excluded docs: {len(excluded_doc_ids)}")
    print(f"   → {OUT_FILE}")
    print()
    print("   top categories after curation:")
    for cat, cnt in cats.most_common(10):
        print(f"     {cat:25s} {cnt:3d}")


if __name__ == "__main__":
    main()
