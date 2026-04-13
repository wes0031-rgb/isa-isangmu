"""Scrape easylaw.go.kr "이사" category (csmSeq=666).

Fetches all discovered 이사 category pages and saves each as a JSON
document under backend/data/procedures/easylaw/.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://easylaw.go.kr/CSP/CnpClsMain.laf"
HEADERS = {"User-Agent": "Mozilla/5.0 (MoveWise RAG data collector)"}
OUT_DIR = Path("/Users/sa/Desktop/2차프로젝트/backend/data/procedures/easylaw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# csmSeq=666 = 이사 카테고리. ccfNo/cciNo/cnpClsNo는 소분류 계층 식별자.
TARGETS = [
    (1, 1, 1),  # 집 구하기 > 집 구하기 > 집 구하기
    (1, 1, 2),
    (1, 1, 3),
    (1, 2, 1),
    (1, 3, 1),
    (2, 1, 1),  # 집 계약하기 > 계약서
    (2, 1, 2),
    (2, 1, 3),
    (2, 2, 1),  # 잔금정산·등기
    (2, 2, 2),
    (2, 2, 3),
    (2, 2, 4),
    (2, 2, 5),
    (2, 3, 1),
    (2, 3, 2),
    (3, 1, 1),  # 이사하기 > 체크리스트
    (3, 2, 1),  # 이사업체
    (3, 2, 2),
    (3, 3, 1),  # 요금 정산
    (3, 3, 2),
    (4, 1, 1),  # 이사 후 > 전입신고
    (4, 2, 1),  # 이사 후 > 아이 전학
]


def build_url(ccf: int, cci: int, cnp: int) -> str:
    return f"{BASE}?popMenu=ov&csmSeq=666&ccfNo={ccf}&cciNo={cci}&cnpClsNo={cnp}"


def extract_breadcrumb(soup: BeautifulSoup) -> str:
    # 첫 줄이 보통 "이사 > ... > 본문" 형태
    text = soup.get_text(" ", strip=True)
    first = text.split("|")[0]
    first = first.replace("(본문)", "").strip()
    return first[:150]


def extract_title(soup: BeautifulSoup, breadcrumb: str) -> str:
    # 우선 breadcrumb 마지막 세그먼트 사용
    segs = [s.strip() for s in breadcrumb.split(">") if s.strip()]
    if segs:
        last = segs[-1]
        if last and len(last) < 80 and "공유" not in last and "본문" not in last:
            return last
    # fallback: title 태그
    title_tag = soup.find("title")
    if title_tag:
        t = title_tag.get_text(strip=True)
        t = t.split("|")[0].strip()
        return t or "제목 없음"
    return "제목 없음"


def extract_main_text(soup: BeautifulSoup) -> str:
    container = soup.find(id="contents") or soup.find(id="maincontent")
    if container is None:
        return ""
    # 네비게이션/푸터로 쓰이는 ul·nav 제거
    for junk in container.select(
        "nav, footer, script, style, .lnb, .gnb, .sub_menu, "
        ".pop_article, .btn_area, .foot_cont, .print_area, .share_area"
    ):
        junk.decompose()
    text = container.get_text("\n", strip=True)
    # 과도한 줄바꿈 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


CITATION_RE = re.compile(
    r"「\s*([^」]+?법(?:\s*시행(?:령|규칙))?)\s*」"
    r"\s*제\s*(\d+)\s*조(?:의\s*(\d+))?"
    r"(?:\s*제\s*(\d+)\s*항)?"
)


def extract_law_citations(text: str) -> list[str]:
    found = []
    for match in CITATION_RE.finditer(text):
        law, art, art_sub, para = match.groups()
        law_clean = re.sub(r"\s+", "", law)
        cite = f"{law_clean} 제{art}조"
        if art_sub:
            cite += f"의{art_sub}"
        if para:
            cite += f" 제{para}항"
        found.append(cite)
    return sorted(set(found))


def scrape_one(ccf: int, cci: int, cnp: int) -> dict | None:
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
        return {"error": "main text too short (maybe redirected)", "url": url, "length": len(text)}

    breadcrumb = extract_breadcrumb(soup)
    return {
        "id": f"easylaw-666-{ccf}-{cci}-{cnp}",
        "source": "easylaw.go.kr",
        "category_root": "이사",
        "breadcrumb": breadcrumb,
        "title": extract_title(soup, breadcrumb),
        "url": url,
        "content": text,
        "content_length": len(text),
        "law_citations": extract_law_citations(text),
        "fetched_at": date.today().isoformat(),
    }


def main() -> None:
    results = []
    for ccf, cci, cnp in TARGETS:
        print(f"  ▶ {ccf}-{cci}-{cnp} ...", end=" ")
        doc = scrape_one(ccf, cci, cnp)
        if doc is None:
            print("none")
            continue
        if "error" in doc:
            print(f"ERR {doc['error']}")
            results.append({"status": "error", **doc})
            continue
        path = OUT_DIR / f"{doc['id']}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK len={doc['content_length']} laws={len(doc['law_citations'])}")
        results.append({"status": "ok", "id": doc["id"], "length": doc["content_length"], "laws": len(doc["law_citations"])})
        time.sleep(0.6)  # rate limit 배려

    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }
    (OUT_DIR / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print()
    print(f"✅ {summary['ok']}/{summary['total']} pages saved to {OUT_DIR}")
    print(f"❌ errors: {summary['errors']}")


if __name__ == "__main__":
    main()
