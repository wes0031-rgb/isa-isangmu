"""Scrape 한국도시가스협회 citygas.or.kr 회원사 매핑.

Parses situation.jsp to extract region → company mapping.
Saves:
  - backend/data/mapping/gas_region_company.json  (매핑 테이블; 유니크 회사명은 entries에서 파생)
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from annotate_sources import get_source_metadata

URL = "http://www.citygas.or.kr/company/situation.jsp"
HEADERS = {"User-Agent": "Mozilla/5.0 (isa-isangmu RAG collector)"}

ROOT = Path(__file__).resolve().parent.parent.parent
MAPPING_OUT = ROOT / "backend" / "data" / "mapping" / "gas_region_company.json"
MAPPING_OUT.parent.mkdir(parents=True, exist_ok=True)

_SOURCE_METADATA = get_source_metadata("mapping/gas_region_company.json")


def clean(name: str) -> str:
    return re.sub(r"\s+", "", name.strip())


def main() -> None:
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")

    region_map: list[dict] = []  # 각 항목: {region, company, class}
    all_companies: set[str] = set()

    # map_name 영역의 dl 리스트만 타겟
    map_area = soup.find("div", class_="map_name")
    if map_area is None:
        print("map_name div not found")
        return

    for dl in map_area.find_all("dl"):
        dt = dl.find("dt")
        if dt is None:
            continue
        region = clean(dt.get_text())
        for dd in dl.find_all("dd"):
            a = dd.find("a")
            if a is None:
                continue
            company = clean(a.get_text())
            css_class = " ".join(a.get("class") or [])
            region_map.append({
                "region": region,
                "company": company,
                "class_hint": css_class,
            })
            all_companies.add(company)

    mapping_doc = {
        "source": URL,
        "fetched_at": date.today().isoformat(),
        "category": "도시가스 공급사",
        "coverage": "전국",
        "note": (
            "각 공급사별 명의변경 절차는 개별 웹사이트 또는 고객센터 문의 필요. "
            "본 데이터는 지역 ↔ 공급사 매핑 용도로 사용."
        ),
        "total_entries": len(region_map),
        "unique_companies": len(all_companies),
        "entries": region_map,
        "_source_metadata": _SOURCE_METADATA,
    }

    MAPPING_OUT.write_text(
        json.dumps(mapping_doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✅ 매핑 {len(region_map)}건 / 고유 회사 {len(all_companies)}개 → {MAPPING_OUT.relative_to(ROOT)}")
    # 권역별 개수
    by_region: dict[str, int] = {}
    for e in region_map:
        by_region[e["region"]] = by_region.get(e["region"], 0) + 1
    for region, cnt in sorted(by_region.items(), key=lambda x: -x[1]):
        print(f"  {region}: {cnt}개")


if __name__ == "__main__":
    main()
