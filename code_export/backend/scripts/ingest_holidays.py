"""Fetch Korean public holidays from data.go.kr SpcdeInfoService.

Saves 2026 holidays as JSON for D-day calculation (법정 기한이 공휴일에
걸리면 다음 평일로 자동 밀리는 로직에 사용).
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import requests
import xml.etree.ElementTree as ET

SERVICE_KEY = "60eebc92ee90c63e051fd34bcf3349799825d7ba846b01b8b468b0f60aaa6ebc"
URL = "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
OUT = Path("/Users/sa/Desktop/2차프로젝트/backend/data/raw/holidays_2026.json")
OUT.parent.mkdir(parents=True, exist_ok=True)


def fetch_month(year: int, month: int) -> list[dict]:
    params = {
        "serviceKey": SERVICE_KEY,
        "solYear": year,
        "solMonth": f"{month:02d}",
        "numOfRows": 50,
    }
    r = requests.get(URL, params=params, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    items = []
    for item in root.iter("item"):
        rec: dict = {}
        for child in item:
            rec[child.tag] = child.text
        items.append(rec)
    return items


def main() -> None:
    year = 2026
    all_holidays: list[dict] = []
    for m in range(1, 13):
        items = fetch_month(year, m)
        all_holidays.extend(items)
        print(f"  {year}-{m:02d}: {len(items)}건")

    # Normalize
    normalized = []
    for h in all_holidays:
        loc = h.get("locdate", "")
        normalized.append({
            "date": f"{loc[:4]}-{loc[4:6]}-{loc[6:8]}" if len(loc) == 8 else loc,
            "name": h.get("dateName"),
            "is_holiday": h.get("isHoliday") == "Y",
        })
    normalized.sort(key=lambda x: x["date"])

    OUT.write_text(json.dumps({
        "source": "apis.data.go.kr (한국천문연구원 특일정보)",
        "year": year,
        "total": len(normalized),
        "holidays": normalized,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 총 {len(normalized)}건 저장 → {OUT}")


if __name__ == "__main__":
    main()
