"""백엔드 엔드포인트 스모크 테스트.

모든 엔드포인트에 대표 요청을 보내고 응답을 검증한다.
로컬 개발 서버가 실행 중일 때 사용.

Usage:
  python3 backend/scripts/smoke_test.py                       # localhost:8765 기본
  BACKEND_URL=https://movewise.onrender.com python3 ...        # 원격 배포 대상 검증
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import urllib.error
import urllib.request

BASE = os.environ.get("BACKEND_URL", "http://127.0.0.1:8765")
TIMEOUT = 15


class SmokeTestFailed(Exception):
    pass


def _http_get(path: str) -> dict[str, Any]:
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return {"status": r.status, "body": json.loads(r.read())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode(errors="ignore")}
    except Exception as e:
        raise SmokeTestFailed(f"GET {path}: {e}")


def _http_post(path: str, payload: dict) -> dict[str, Any]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return {"status": r.status, "body": json.loads(r.read())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode(errors="ignore")}
    except Exception as e:
        raise SmokeTestFailed(f"POST {path}: {e}")


def check(name: str, cond: bool, detail: str = "") -> bool:
    mark = "✅" if cond else "❌"
    print(f"  {mark} {name}{(' — ' + detail) if detail else ''}")
    return cond


def test_root() -> bool:
    print("\n[1/5] GET /")
    r = _http_get("/")
    ok = True
    ok &= check("200 OK", r["status"] == 200)
    if isinstance(r["body"], dict):
        ok &= check(
            "service=MoveWise",
            str(r["body"].get("service", "")).lower() == "movewise",
            f"got {r['body'].get('service')}",
        )
    return ok


def test_health() -> bool:
    print("\n[2/5] GET /health")
    r = _http_get("/health")
    ok = True
    ok &= check("200 OK", r["status"] == 200)
    return ok


def test_checklist_basic() -> bool:
    print("\n[3/5] POST /checklist (single contract)")
    payload = {
        "household": "자취",
        "contract": "월세",
        "region": "경기도 성남시 분당구",
        "move_date": "2026-05-01",
        "has_pet": False,
        "has_car": False,
        "has_children": False,
    }
    r = _http_post("/checklist", payload)
    ok = True
    ok &= check("200 OK", r["status"] == 200)
    if r["status"] == 200 and isinstance(r["body"], dict):
        items = r["body"].get("items", [])
        ok &= check(f"items >= 5 (got {len(items)})", len(items) >= 5)
        cats = {it["category"] for it in items}
        ok &= check("contains 전입신고", any("전입신고" in c for c in cats))
        ok &= check("contains 확정일자", any("확정일자" in c for c in cats))
        # citation enrichment check
        has_text = any(
            c.get("article_text")
            for it in items
            for c in it.get("citations", [])
        )
        ok &= check("has article_text in citations", has_text)
    return ok


def test_checklist_multi() -> bool:
    print("\n[4/5] POST /checklist (multi contract + 특이사항)")
    payload = {
        "household": "가족",
        "contract": "전세",
        "contracts": ["전세", "자가"],
        "region": "서울특별시 강남구",
        "move_date": "2026-06-15",
        "has_pet": True,
        "has_car": True,
        "has_children": True,
        "children_school_level": "초등",
        "special_concerns": ["보증금 반환 우려", "갱신요구권"],
    }
    r = _http_post("/checklist", payload)
    ok = True
    ok &= check("200 OK", r["status"] == 200)
    if r["status"] == 200 and isinstance(r["body"], dict):
        items = r["body"].get("items", [])
        cats = {it["category"] for it in items}
        ok &= check("has 반려동물", any("반려동물" in c for c in cats))
        ok &= check("has 자동차", any("자동차" in c for c in cats))
        ok &= check("has 자녀 전학", any("전학" in c for c in cats))
        ok &= check("has 임차권등기", any("임차권" in c for c in cats))
        ok &= check("has 갱신요구권", any("갱신" in c for c in cats))
    return ok


def test_safecontract() -> bool:
    print("\n[5/5] POST /safecontract")
    payload = {
        "text": "[갑구] 소유권보존 홍길동\n[을구] 근저당권설정 채권최고액 금 2억4천만원",
        "deposit_krw": 150_000_000,
        "expected_market_price_krw": 300_000_000,
    }
    r = _http_post("/safecontract", payload)
    ok = True
    ok &= check("200 OK", r["status"] == 200)
    if r["status"] == 200 and isinstance(r["body"], dict):
        body = r["body"]
        ok &= check("jeontse_ratio present", "jeontse_ratio" in body)
        risks = body.get("risks", [])
        ok &= check(f"risks >= 1 (got {len(risks)})", len(risks) >= 1)
        has_law_text = any(
            c.get("article_text")
            for risk in risks
            for c in risk.get("related_laws", [])
        )
        ok &= check("risks reference law article text", has_law_text)
    return ok


def main() -> int:
    print(f"🔥 MoveWise backend smoke test → {BASE}")
    start = time.time()
    results = [
        test_root(),
        test_health(),
        test_checklist_basic(),
        test_checklist_multi(),
        test_safecontract(),
    ]
    elapsed = time.time() - start
    print()
    print("=" * 50)
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"Result: {passed}/{total} passed in {elapsed:.2f}s")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
