"""Scrape easylaw.go.kr "주택임대차" category (csmSeq=629).

Reuses the core scraper from ingest_easylaw.py.
"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent))
from ingest_easylaw import (  # type: ignore
    HEADERS,
    extract_breadcrumb,
    extract_main_text,
    extract_title,
    extract_law_citations,
)
import requests
from bs4 import BeautifulSoup

BASE = "https://easylaw.go.kr/CSP/CnpClsMain.laf"
OUT_DIR = Path("/Users/sa/Desktop/2차프로젝트/backend/data/procedures/easylaw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# csmSeq=629 = 주택임대차 카테고리
TARGETS = [
    (1, 1, 1), (1, 2, 1),
    (2, 1, 1), (2, 2, 1), (2, 2, 2), (2, 2, 3), (2, 2, 4), (2, 2, 5),
    (2, 3, 1), (2, 3, 2),
    (3, 1, 1), (3, 2, 1),
    (4, 1, 1), (4, 1, 2), (4, 2, 1), (4, 2, 2),
    (4, 3, 1), (4, 3, 2), (4, 3, 3), (4, 3, 4), (4, 4, 1),
    (5, 1, 1),
    (5, 2, 1), (5, 2, 2), (5, 2, 3), (5, 2, 4), (5, 2, 5), (5, 2, 6),
    (5, 3, 1), (5, 3, 2), (5, 3, 3),
]

CSM_SEQ = 629


def build_url(ccf: int, cci: int, cnp: int) -> str:
    return f"{BASE}?popMenu=ov&csmSeq={CSM_SEQ}&ccfNo={ccf}&cciNo={cci}&cnpClsNo={cnp}"


def scrape_one(ccf: int, cci: int, cnp: int) -> dict:
    url = build_url(ccf, cci, cnp)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as exc:
        return {"error": f"request failed: {exc}", "url": url}
    if r.status_code != 200:
        return {"error": f"http {r.status_code}", "url": url}

    soup = BeautifulSoup(r.text, "html.parser")
    text = extract_main_text(soup)
    if len(text) < 200:
        return {"error": "main text too short", "url": url, "length": len(text)}

    breadcrumb = extract_breadcrumb(soup)
    return {
        "id": f"easylaw-{CSM_SEQ}-{ccf}-{cci}-{cnp}",
        "source": "easylaw.go.kr",
        "category_root": "주택임대차",
        "breadcrumb": breadcrumb,
        "title": extract_title(soup, breadcrumb),
        "url": url,
        "content": text,
        "content_length": len(text),
        "law_citations": extract_law_citations(text),
        "fetched_at": date.today().isoformat(),
    }


def main() -> None:
    ok = 0
    err = 0
    for ccf, cci, cnp in TARGETS:
        print(f"  ▶ {ccf}-{cci}-{cnp} ...", end=" ")
        doc = scrape_one(ccf, cci, cnp)
        if "error" in doc:
            print(f"ERR {doc['error']}")
            err += 1
            continue
        path = OUT_DIR / f"{doc['id']}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK len={doc['content_length']} laws={len(doc['law_citations'])}")
        ok += 1
        time.sleep(0.6)
    print()
    print(f"✅ 주택임대차: {ok}/{len(TARGETS)} saved, ❌ errors: {err}")


if __name__ == "__main__":
    main()
