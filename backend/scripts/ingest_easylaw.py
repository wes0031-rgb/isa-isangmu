"""Scrape easylaw.go.kr "이사" + "주택임대차" categories.

Unified version (2026-04-19):
- Merges ingest_easylaw.py + ingest_easylaw_lease.py
- Fixes hardcoded Mac path → cross-platform ROOT-relative
- Adds --only flag for single-category scraping
- IMPROVED CONTENT EXTRACTION:
  * Target #ovDiv instead of whole #contents
  * Strip SNS/save/search/tab UI elements
  * Remove accessibility labels (인쇄체크, 즐겨찾기에추가 등)
  * Clean link title attributes (새창으로 열림)

Output schema unchanged (10 fields):
  id, source, category_root, breadcrumb, title,
  url, content, content_length, law_citations, fetched_at

Usage:
  python scripts/ingest_easylaw.py             # both categories
  python scripts/ingest_easylaw.py --only 666  # 이사 only
  python scripts/ingest_easylaw.py --only 629  # 주택임대차 only
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "backend" / "data" / "procedures" / "easylaw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://easylaw.go.kr/CSP/CnpClsMain.laf"
HEADERS = {"User-Agent": "Mozilla/5.0 (isa-isangmu RAG data collector)"}


# 카테고리별 수집 설정
CATEGORIES: dict[int, dict] = {
    666: {
        "name": "이사",
        "targets": [
            (1, 1, 1), (1, 1, 2), (1, 1, 3), (1, 2, 1), (1, 3, 1),
            (2, 1, 1), (2, 1, 2), (2, 1, 3),
            (2, 2, 1), (2, 2, 2), (2, 2, 3), (2, 2, 4), (2, 2, 5),
            (2, 3, 1), (2, 3, 2),
            (3, 1, 1), (3, 2, 1), (3, 2, 2), (3, 3, 1), (3, 3, 2),
            (4, 1, 1), (4, 2, 1),
        ],
    },
    629: {
        "name": "주택임대차",
        "targets": [
            (1, 1, 1), (1, 2, 1),
            (2, 1, 1), (2, 2, 1), (2, 2, 2), (2, 2, 3), (2, 2, 4), (2, 2, 5),
            (2, 3, 1), (2, 3, 2),
            (3, 1, 1), (3, 2, 1),
            (4, 1, 1), (4, 1, 2), (4, 2, 1), (4, 2, 2),
            (4, 3, 1), (4, 3, 2), (4, 3, 3), (4, 3, 4), (4, 4, 1),
            (5, 1, 1),
            (5, 2, 1), (5, 2, 2), (5, 2, 3), (5, 2, 4), (5, 2, 5), (5, 2, 6),
            (5, 3, 1), (5, 3, 2), (5, 3, 3),
        ],
    },
}


def build_url(csm_seq: int, ccf: int, cci: int, cnp: int) -> str:
    return f"{BASE}?popMenu=ov&csmSeq={csm_seq}&ccfNo={ccf}&cciNo={cci}&cnpClsNo={cnp}"


def extract_breadcrumb(soup: BeautifulSoup) -> str:
    """현재위치(location > fL) div에서 breadcrumb 추출.

    구조:
      <div class="location">
        <div class="fL">홈 > 책자형 > 주택임대차</div>
        <div class="fR">...검색/공유/저장 UI...</div>
      </div>
    """
    loc = soup.select_one("div.location div.fL")
    if loc is None:
        # fallback
        loc = soup.find("div", class_="location")
    if loc is None:
        return ""
    text = loc.get_text(" ", strip=True)
    # 아이콘·이미지 alt 텍스트 정리
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200]

def extract_title(soup: BeautifulSoup, breadcrumb: str) -> str:
    """페이지 타이틀 추출.
    
    <title> 태그 예시:
      "주택임대차 > ... > 「주택임대차보호법」의 적용 (본문) |  찾기쉬운 생활법령정보"
    
    파싱:
      1. " | " 앞까지만 (사이트명 제거)
      2. " > "로 split 후 마지막 segment
      3. "(본문)" suffix 제거
    """
    title_tag = soup.find("title")
    if title_tag:
        t = title_tag.get_text(strip=True)
        # 사이트명 제거: "... | 찾기쉬운 생활법령정보" → "..."
        if "|" in t:
            t = t.split("|")[0].strip()
        # "(본문)" suffix 제거
        t = re.sub(r"\s*\(본문\)\s*$", "", t).strip()
        # breadcrumb 구조면 마지막 segment만
        if ">" in t:
            segs = [s.strip() for s in t.split(">") if s.strip()]
            if segs:
                return segs[-1]
        # 구조 없으면 그대로 반환
        if t:
            return t
    
    # fallback: breadcrumb 마지막 segment
    if breadcrumb:
        segs = [s.strip() for s in breadcrumb.split(">") if s.strip()]
        for seg in reversed(segs):
            if any(skip in seg for skip in ("검색", "공유", "저장", "인쇄", "즐겨찾기")):
                continue
            if seg and len(seg) < 80:
                return seg
    
    return "제목 없음"


# 제거 대상 selector — UI 요소, 공유/저장 버튼, 접근성 라벨 등
NOISE_SELECTORS = [
    # 문서 구조 관련
    "nav", "footer", "header", "script", "style", "noscript",
    # 사이드바/메뉴
    ".lnb", ".gnb", ".sub_menu", ".lnb_wrap", ".nav_wrap", ".allMenu",
    ".quickmenu_wrap", ".topLnb", ".top_header_srchBox",
    # 공유/저장/인쇄 UI
    ".sns_pop", ".save_pop", ".srch_box", ".share_area",
    ".btn_area", ".foot_cont", ".print_area", ".btns",
    ".pop_article",
    # 페이지 메타 영역
    ".location", ".tab_menu",
    # 접근성/스크린리더용 숨김 요소
    ".labelnone", "#skipnav",
    # 하단 안내 (법적 기준일·설문 등)
    ".info_box", ".copy_bot",
    # iframe/이미지만 있는 영역
    ".view_banner_area", ".box_but2",
]


def extract_main_text(soup: BeautifulSoup) -> str:
    """본문 영역 엄격 추출.

    #ovDiv .ovDivbox가 진짜 본문. 없으면 #contents fallback.
    """
    # 1순위: 가장 타이트한 본문 컨테이너
    container = soup.select_one("#ovDiv .ovDivbox")
    if container is None:
        # fallback: #ovDiv 자체
        container = soup.find(id="ovDiv")
    if container is None:
        # 최후 fallback: #contents (기존 방식)
        container = soup.find(id="contents") or soup.find(id="maincontent")
    if container is None:
        return ""

    # 복사본 만들어서 원본 훼손 방지
    container = BeautifulSoup(str(container), "html.parser")

    # 노이즈 제거
    for selector in NOISE_SELECTORS:
        for el in container.select(selector):
            el.decompose()

    # h2 태그 중 섹션 라벨 제거 ("본문 영역", "하단 영역", "바로가기" 등)
    for h2 in container.find_all("h2"):
        text = h2.get_text(strip=True)
        if text in ("바로가기", "본문 영역", "하단 영역", "현재위치 및 공유하기"):
            h2.decompose()

    # <a> 태그의 title 속성(접근성용 텍스트) 제거
    for a in container.find_all("a"):
        if a.has_attr("title"):
            del a["title"]

    # 이미지 alt 텍스트 중 화살표 아이콘 제거 (본문 흐름 방해)
    for img in container.find_all("img"):
        src = img.get("src", "")
        if "icon_arrow" in src or "btn_" in src:
            img.decompose()

    # 텍스트 추출
    text = container.get_text("\n", strip=True)

    # "인쇄체크" 같은 접근성 라벨 제거
    text = re.sub(r"인쇄체크\s*", "", text)
    # "주소복사", "즐겨찾기에추가", "새창으로 열림" 등 제거
    text = re.sub(r"(주소복사|즐겨찾기에추가|새창으로 열림|새창열림)\s*", "", text)
    # 과도한 줄바꿈 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 양끝 공백 정리
    text = text.strip()

    return text


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


def scrape_one(csm_seq: int, category_name: str, ccf: int, cci: int, cnp: int) -> dict | None:
    url = build_url(csm_seq, ccf, cci, cnp)
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
        "id": f"easylaw-{csm_seq}-{ccf}-{cci}-{cnp}",
        "source": "easylaw.go.kr",
        "category_root": category_name,
        "breadcrumb": breadcrumb,
        "title": extract_title(soup, breadcrumb),
        "url": url,
        "content": text,
        "content_length": len(text),
        "law_citations": extract_law_citations(text),
        "fetched_at": date.today().isoformat(),
    }


def process_category(csm_seq: int, config: dict) -> list[dict]:
    name = config["name"]
    targets = config["targets"]
    print(f"\n===== {name} (csmSeq={csm_seq}) — {len(targets)} pages =====")
    results = []
    for ccf, cci, cnp in targets:
        print(f"  ▶ {ccf}-{cci}-{cnp} ...", end=" ")
        doc = scrape_one(csm_seq, name, ccf, cci, cnp)
        if doc is None:
            print("none")
            continue
        if "error" in doc:
            print(f"ERR {doc['error']}")
            results.append({"status": "error", "csm_seq": csm_seq, **doc})
            continue
        path = OUT_DIR / f"{doc['id']}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK len={doc['content_length']} laws={len(doc['law_citations'])}")
        results.append({
            "status": "ok",
            "csm_seq": csm_seq,
            "id": doc["id"],
            "length": doc["content_length"],
            "laws": len(doc["law_citations"]),
        })
        time.sleep(0.6)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        type=int,
        choices=list(CATEGORIES.keys()),
        help="한 카테고리만 수집 (666=이사, 629=주택임대차)",
    )
    args = parser.parse_args()

    categories_to_process = (
        {args.only: CATEGORIES[args.only]} if args.only else CATEGORIES
    )

    all_results: list[dict] = []
    for csm_seq, config in categories_to_process.items():
        results = process_category(csm_seq, config)
        all_results.extend(results)

    summary = {
        "total": len(all_results),
        "ok": sum(1 for r in all_results if r["status"] == "ok"),
        "errors": sum(1 for r in all_results if r["status"] == "error"),
        "by_category": {
            str(k): {"name": v["name"], "targets": len(v["targets"])}
            for k, v in categories_to_process.items()
        },
        "results": all_results,
    }
    (OUT_DIR / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print(f"✅ {summary['ok']}/{summary['total']} pages saved to {OUT_DIR}")
    print(f"❌ errors: {summary['errors']}")


if __name__ == "__main__":
    main()