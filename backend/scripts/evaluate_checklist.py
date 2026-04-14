"""Run golden queries against the checklist service and measure quality.

Metrics:
  - recall@expected    : 생성된 item의 category가 expected_items를 얼마나 커버했는가
  - must_not_violations: must_not_include 카테고리가 생성된 횟수 (적을수록 좋음)
  - citation_coverage  : citation_hint 가 실제 citation에 등장한 비율
  - deadline_accuracy  : expected deadline_days 와 실제 일치한 비율

Usage:
  python3 evaluate_checklist.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.checklist_service import generate_checklist  # noqa: E402
from backend.app.models import ChecklistRequest  # noqa: E402

GOLDEN = ROOT / "backend" / "data" / "indexes" / "golden_queries.json"
REPORT = ROOT / "backend" / "data" / "indexes" / "evaluation_report.json"


import re as _re  # noqa: E402

NOISE_TOKENS = {
    "방법", "절차", "안내", "관련", "신청", "등록", "하기",
    "사항", "정보", "확인", "주소변경", "변경등록",
}


def extract_tokens(text: str) -> set[str]:
    """Extract meaningful Korean/English tokens from a category label."""
    raw = _re.findall(r"[가-힣A-Za-z]{2,}", text or "")
    # Break compound Korean tokens on common separators too
    pieces: list[str] = []
    for r in raw:
        for part in _re.split(r"[·\-/]", r):
            if part:
                pieces.append(part)
    return set(pieces)


def match_category(expected: str, actuals: list[str]) -> bool:
    exp_tokens = extract_tokens(expected) - NOISE_TOKENS
    if not exp_tokens:
        exp_tokens = extract_tokens(expected)
    for a in actuals:
        a_tokens = extract_tokens(a) - NOISE_TOKENS
        if not a_tokens:
            a_tokens = extract_tokens(a)
        # Exact overlap
        if exp_tokens & a_tokens:
            return True
        # Substring (partial match for multi-character Korean terms)
        for e in exp_tokens:
            for ac in a_tokens:
                if len(e) >= 3 and (e in ac or ac in e):
                    return True
    return False


def build_request(user_input: dict) -> ChecklistRequest:
    data = {
        "household": user_input.get("household", "자취"),
        "contract": user_input.get("contract", "월세"),
        "region": user_input.get("region", "서울특별시 강남구"),
        "move_date": user_input.get("move_date", "2026-05-01"),
        "has_pet": user_input.get("has_pet", False),
        "has_car": user_input.get("has_car", False),
        "car_count": user_input.get("car_count", 1),
        "has_children": user_input.get("has_children", False),
        "children_count": user_input.get("children_count", 0),
        "children_school_level": user_input.get("children_school_level"),
        "is_foreigner": user_input.get("is_foreigner", False),
        "deposit_krw": user_input.get("deposit_krw"),
        "monthly_rent_krw": user_input.get("monthly_rent_krw"),
        "special_concerns": user_input.get("special_concerns", []),
    }
    return ChecklistRequest(**data)


def evaluate_query(query: dict) -> dict:
    req = build_request(query["user_input"])
    resp = generate_checklist(req)
    actual_categories = [it.category for it in resp.items]
    actual_citations = [f"{c.law_name} {c.article}" for it in resp.items for c in it.citations]
    actual_deadlines = {it.category: it.deadline_days for it in resp.items if it.deadline_days}

    expected_items = query.get("expected_items", [])
    must_appear = [e for e in expected_items if e.get("must_appear")]
    must_not = query.get("must_not_include", [])

    # recall @ must-appear
    matched = 0
    missing = []
    for exp in must_appear:
        if match_category(exp["category"], actual_categories):
            matched += 1
        else:
            missing.append(exp["category"])

    # must-not violations
    violations = []
    for mn in must_not:
        if match_category(mn, actual_categories):
            violations.append(mn)

    # citation coverage
    cit_hints = [e.get("citation_hint") for e in expected_items if e.get("citation_hint")]
    cit_hits = 0
    for hint in cit_hints:
        if any(hint.replace(" ", "") in c.replace(" ", "") for c in actual_citations):
            cit_hits += 1

    # deadline accuracy
    dl_correct = 0
    dl_total = 0
    for exp in expected_items:
        exp_days = exp.get("deadline_days")
        if exp_days is None:
            continue
        dl_total += 1
        for cat, days in actual_deadlines.items():
            if match_category(exp["category"], [cat]) and days == exp_days:
                dl_correct += 1
                break

    return {
        "query_id": query["query_id"],
        "scenario": query["scenario"],
        "total_items_generated": len(actual_categories),
        "must_appear_total": len(must_appear),
        "must_appear_matched": matched,
        "recall": round(matched / len(must_appear), 3) if must_appear else 1.0,
        "missing_categories": missing,
        "must_not_violations": violations,
        "citation_hits": cit_hits,
        "citation_total": len(cit_hints),
        "citation_coverage": round(cit_hits / len(cit_hints), 3) if cit_hints else 1.0,
        "deadline_correct": dl_correct,
        "deadline_total": dl_total,
        "deadline_accuracy": round(dl_correct / dl_total, 3) if dl_total else 1.0,
    }


def main() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    queries = data["queries"]
    print(f"Running {len(queries)} golden queries...")
    print()

    results = []
    for q in queries:
        r = evaluate_query(q)
        results.append(r)
        status = "✅" if r["recall"] >= 0.8 and not r["must_not_violations"] else "⚠️"
        print(
            f"{status} {r['query_id']} recall={r['recall']:.2f} "
            f"cit={r['citation_coverage']:.2f} "
            f"dl={r['deadline_accuracy']:.2f} "
            f"items={r['total_items_generated']} "
            f"miss={len(r['missing_categories'])} violate={len(r['must_not_violations'])}"
        )
        if r["missing_categories"]:
            print(f"     ✗ missing: {', '.join(r['missing_categories'])}")
        if r["must_not_violations"]:
            print(f"     ⚠ violations: {', '.join(r['must_not_violations'])}")

    # Aggregates
    mean_recall = sum(r["recall"] for r in results) / len(results)
    mean_cit = sum(r["citation_coverage"] for r in results) / len(results)
    mean_dl = sum(r["deadline_accuracy"] for r in results) / len(results)
    total_violations = sum(len(r["must_not_violations"]) for r in results)
    perfect = sum(1 for r in results if r["recall"] == 1.0 and not r["must_not_violations"])

    print()
    print("=" * 60)
    print(f"Overall metrics ({len(results)} queries)")
    print("=" * 60)
    print(f"  mean recall              : {mean_recall:.3f}")
    print(f"  mean citation coverage   : {mean_cit:.3f}")
    print(f"  mean deadline accuracy   : {mean_dl:.3f}")
    print(f"  total must-not violations: {total_violations}")
    print(f"  perfect queries          : {perfect}/{len(results)}")

    report = {
        "summary": {
            "total_queries": len(results),
            "mean_recall": round(mean_recall, 4),
            "mean_citation_coverage": round(mean_cit, 4),
            "mean_deadline_accuracy": round(mean_dl, 4),
            "total_violations": total_violations,
            "perfect_queries": perfect,
        },
        "per_query": results,
        "system": {
            "mode": "rule-based fallback + local keyword search",
            "chunks_source": "index_b_chunks_curated.jsonl (200 chunks)",
            "azure_openai": "not configured",
            "azure_search": "not configured",
        },
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"📊 report saved → {REPORT}")


if __name__ == "__main__":
    main()
