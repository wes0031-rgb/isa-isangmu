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

from annotate_sources import get_source_metadata

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "backend" / "data" / "guide"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://easylaw.go.kr/CSP/CnpClsMain.laf"
HEADERS = {"User-Agent": "Mozilla/5.0 (isa-isangmu RAG data collector)"}
OUT_DIR = Path("/Users/sa/Desktop/2차프로젝트/backend/data/procedures/easylaw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 단일 출처: annotate_sources.SOURCES ["guide/*.json" 엔트리]
_SOURCE_METADATA = get_source_metadata("guide/*.json")


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
        "_source_metadata": _SOURCE_METADATA,
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
