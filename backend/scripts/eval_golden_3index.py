"""3-index /checklist 품질 평가 — golden_queries.json 기반.

각 쿼리에 대해 generate_checklist() 를 호출하고 expected_items / must_not_include
대비 recall · citation coverage · deadline accuracy · 환각 위반 수를 집계.

Usage:
    python3 backend/scripts/eval_golden_3index.py [N]   # default N=30
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.checklist_service import generate_checklist  # noqa: E402
from backend.app.models import ChecklistRequest  # noqa: E402

GOLDEN_PATH = ROOT / "backend" / "data" / "indexes" / "golden_queries.json"
OUT_PATH = ROOT / "backend" / "data" / "indexes" / "evaluation_report_3index.json"


def match_category(expected_cat: str, items: list) -> object | None:
    for it in items:
        if expected_cat == (it.category or "") or expected_cat in (it.category or ""):
            return it
        if expected_cat in (it.title or ""):
            return it
    return None


def check_must_not_violation(must_not: list[str], items: list) -> list[str]:
    violated = []
    for bad in must_not:
        for it in items:
            if bad in (it.category or "") or bad in (it.title or ""):
                violated.append(bad)
                break
    return violated


def check_citation_hint(hint: str, item) -> bool:
    """hint 예: '주민등록법 제16조' → item.citations 에서 law_name+article 매칭."""
    for c in item.citations or []:
        if not c.law_name or not c.article:
            continue
        if c.law_name in hint and c.article in hint:
            return True
    return False


def main(n: int = 30):
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        gq = json.load(f)
    queries = gq["queries"][:n]
    print(f"평가 대상: {len(queries)}개 쿼리 · 시스템: 3-index (law+guide+video)")
    print("=" * 70)

    per_query = []
    sum_recall = 0.0
    sum_citation = 0.0
    sum_deadline = 0.0
    total_violations = 0
    total_runs = 0
    errors = 0
    total_elapsed = 0.0

    for idx, q in enumerate(queries, 1):
        qid = q["query_id"]
        user_input = dict(q["user_input"])
        user_input["move_date"] = date.fromisoformat(user_input["move_date"])
        try:
            req = ChecklistRequest(**user_input)
        except Exception as e:
            print(f"[{idx:2d}/{len(queries)}] {qid} ❌ validation: {e}")
            errors += 1
            continue

        t0 = time.time()
        try:
            resp = generate_checklist(req)
        except Exception as e:
            print(f"[{idx:2d}/{len(queries)}] {qid} ❌ generate: {type(e).__name__}: {e}")
            errors += 1
            continue
        elapsed = time.time() - t0
        total_elapsed += elapsed

        expected = q.get("expected_items", [])
        must_not = q.get("must_not_include", [])

        matched = 0
        total_must = 0
        citation_matched = 0
        citation_total = 0
        deadline_matched = 0
        deadline_total = 0
        missing_items: list[str] = []

        for exp in expected:
            if not exp.get("must_appear"):
                continue
            total_must += 1
            it = match_category(exp["category"], resp.items)
            if it is not None:
                matched += 1
                if "citation_hint" in exp and exp["citation_hint"]:
                    citation_total += 1
                    if check_citation_hint(exp["citation_hint"], it):
                        citation_matched += 1
                if exp.get("deadline_days") is not None:
                    deadline_total += 1
                    if it.deadline_days == exp["deadline_days"]:
                        deadline_matched += 1
            else:
                missing_items.append(exp["category"])

        violations = check_must_not_violation(must_not, resp.items)

        recall = matched / total_must if total_must else 1.0
        cit_cov = citation_matched / citation_total if citation_total else 1.0
        dl_acc = deadline_matched / deadline_total if deadline_total else 1.0

        total_runs += 1
        sum_recall += recall
        sum_citation += cit_cov
        sum_deadline += dl_acc
        total_violations += len(violations)

        per_query.append({
            "query_id": qid,
            "scenario": q.get("scenario", ""),
            "items_returned": len(resp.items),
            "recall": round(recall, 3),
            "matched": matched,
            "total_must": total_must,
            "missing_items": missing_items,
            "citation_coverage": round(cit_cov, 3),
            "citation_matched": citation_matched,
            "citation_total": citation_total,
            "deadline_accuracy": round(dl_acc, 3),
            "must_not_violations": violations,
            "warning": resp.warning,
            "elapsed_sec": round(elapsed, 2),
        })

        v_mark = f"⚠️ {len(violations)}" if violations else "✓"
        print(
            f"[{idx:2d}/{len(queries)}] {qid}  "
            f"r={recall:.2f} ({matched}/{total_must})  "
            f"c={cit_cov:.2f}  d={dl_acc:.2f}  viol={v_mark}  "
            f"items={len(resp.items)}  ({elapsed:.1f}s)"
        )

    summary = {
        "total_queries": len(queries),
        "successful_runs": total_runs,
        "errors": errors,
        "mean_recall": round(sum_recall / max(total_runs, 1), 3),
        "mean_citation_coverage": round(sum_citation / max(total_runs, 1), 3),
        "mean_deadline_accuracy": round(sum_deadline / max(total_runs, 1), 3),
        "total_must_not_violations": total_violations,
        "mean_elapsed_sec": round(total_elapsed / max(total_runs, 1), 2),
    }
    report = {
        "summary": summary,
        "per_query": per_query,
        "system": "3-index (law-index + guide-index + video-index) · hybrid semantic+vector",
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 70)
    print(f"SUMMARY (n={total_runs}):")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\n→ saved: {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    main(n)
