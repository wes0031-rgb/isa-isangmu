"""Fetch law texts from law.go.kr DRF API using LAW_OC.

Saves each law as JSON (articles list) under backend/data/laws/
then chunks them into Azure AI Search index A format.

Usage:
  1) .env 의 LAW_OC 를 채운다
  2) python3 ingest_laws.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parent.parent.parent  # 2차프로젝트
ENV_PATH = ROOT / ".env"
LAWS_DIR = ROOT / "backend" / "data" / "laws"
INDEX_A_PATH = ROOT / "backend" / "data" / "indexes" / "index_a_chunks.jsonl"
LAWS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_A_PATH.parent.mkdir(parents=True, exist_ok=True)

# 수집할 법률 (이름 → MST ID)
# MST는 law.go.kr DRF의 법령 마스터 키. 확인 방법:
#   1) https://www.law.go.kr/법령/주택임대차보호법 접속
#   2) 페이지 하단 "공유" → "open API" 버튼 URL에서 MST=xxxx 확인
# 아래 값은 2026-04 기준. 변경되면 재확인 필요.
LAWS: list[tuple[str, int, str]] = [
    ("주택임대차보호법", 276291, "임대차 대항력·확정일자·우선변제권"),
    ("주택임대차보호법 시행령", 280995, "임대차 시행 기준"),
    ("주민등록법", 268555, "전입신고 의무·과태료"),
    ("주민등록법 시행령", 266731, "신고 기한 상세"),
    ("동물보호법", 267325, "반려동물 주소변경 30일"),
    ("부동산등기법", 265377, "갑구·을구 구조"),
    ("민법", 284415, "임대차 조항(제618조~)"),
    ("공동주택관리법", 280069, "관리비·장기수선충당금"),
]


def load_env_oc() -> str:
    if not ENV_PATH.exists():
        raise RuntimeError(f".env not found: {ENV_PATH}")
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("LAW_OC="):
            v = line.split("=", 1)[1].strip()
            return v
    return ""


def fetch_law(oc: str, mst: int) -> ET.Element | None:
    url = "https://www.law.go.kr/DRF/lawService.do"
    params = {
        "OC": oc,
        "target": "law",
        "type": "XML",
        "MST": mst,
    }
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}")
        return None
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as exc:
        print(f"    parse error: {exc}")
        return None
    # 에러 응답 체크
    err = root.find(".//result")
    if err is not None and err.text and "실패" in err.text:
        print(f"    API err: {err.text}")
        return None
    return root


def parse_articles(root: ET.Element) -> list[dict]:
    """법령 XML → 조문 리스트 변환."""
    articles = []
    for jo in root.iter("조문단위"):
        article_no = (jo.findtext("조문번호") or "").strip()
        article_sub = (jo.findtext("조문가지번호") or "").strip()
        article_title = (jo.findtext("조문제목") or "").strip()
        article_text = (jo.findtext("조문내용") or "").strip()

        # 항 단위 추가
        hang_texts: list[str] = []
        for hang in jo.iter("항"):
            h_text = (hang.findtext("항내용") or "").strip()
            if h_text:
                hang_texts.append(h_text)
        full_text = article_text
        if hang_texts:
            full_text += "\n" + "\n".join(hang_texts)

        if not full_text:
            continue
        article_label = f"제{article_no}조"
        if article_sub and article_sub != "0":
            article_label += f"의{article_sub}"

        articles.append({
            "article": article_label,
            "title": article_title,
            "content": full_text,
        })
    return articles


# ===== 키워드 추출 =====
# 법률 용어 사전 — 이사이상무 도메인에서 검색 빈도가 높은 핵심 용어
# 조문 본문에 등장하면 키워드로 즉시 채택 (빈도 무관)
LEGAL_TERMS = frozenset([
    # 임대차 핵심
    "대항력", "우선변제권", "확정일자", "임차권등기명령", "전입신고",
    "보증금", "임대차", "임대인", "임차인", "전세금", "월세",
    "임대차기간", "존속기간", "갱신요구권", "묵시적갱신", "해지통고",
    # 물권·담보·경매
    "근저당권", "저당권", "가압류", "임의경매", "경매개시결정",
    "배당순위", "최우선변제", "소액임차인", "신탁등기",
    # 계약·채권
    "계약해지", "계약갱신", "채무불이행", "원상회복", "손해배상",
    "중도해지", "동시이행", "유치권",
    # 등기·주민등록
    "등기부", "주민등록", "주민등록번호", "말소", "전출", "전입",
    "관할", "시장", "군수", "구청장",
    # 행정·벌칙
    "과태료", "벌금", "시행", "위반", "공고",
    # 건축·관리
    "공동주택", "관리비", "장기수선충당금", "관리비예치금", "위반건축물",
    # 동물·가족
    "반려동물", "소유자", "동물등록", "변경신고",
])


def extract_keywords(text: str, title: str = "") -> list[str]:
    """법률 조문용 키워드 추출 — 3단계 병합.

    1. title 에서 ( ) 안의 괄호 주제어 추출 (예: "제3조(대항력 등)" → "대항력")
    2. 본문에서 LEGAL_TERMS 사전 매칭 (빈도 무관, 있으면 바로 채택)
    3. 2회 이상 등장한 한글 2자+ 단어
    4. fallback: 3자 이상 한글 단어 1회 등장 (짧은 조문용)

    Args:
        text: 조문 본문
        title: 조문 제목 (예: "대항력 등"). 선택.

    Returns:
        중복 제거된 키워드 최대 10개
    """
    from collections import Counter
    result: list[str] = []
    seen: set[str] = set()

    def _add(word: str) -> None:
        if word and word not in seen and len(result) < 10:
            seen.add(word)
            result.append(word)

    # 1. title 파싱 — ( 안) 괄호 주제어 + 공백 분리 토큰
    if title:
        # 괄호 안 추출
        for m in re.finditer(r"[(\(]([^)\)]+)[)\)]", title):
            for w in re.findall(r"[가-힣]{2,}", m.group(1)):
                _add(w)
        # 괄호 밖 전체 토큰 (괄호 제거 후)
        bare = re.sub(r"[(\(][^)\)]*[)\)]", " ", title)
        for w in re.findall(r"[가-힣]{2,}", bare):
            _add(w)

    if not text:
        return result

    # 2. 법률 용어 사전 매칭
    for term in LEGAL_TERMS:
        if term in text:
            _add(term)

    # 3. 빈도 2회 이상
    tokens = re.findall(r"[가-힣]{2,}", text)
    counts = Counter(tokens)
    for w, c in counts.most_common():
        if c >= 2 and len(w) >= 2:
            _add(w)
        if len(result) >= 10:
            break

    # 4. fallback: 3자 이상 단어 1회 등장 (총 키워드 < 3 일 때만)
    if len(result) < 3:
        for w in tokens:
            if len(w) >= 3:
                _add(w)
            if len(result) >= 5:
                break

    return result


# RAG 품질 필터 — 아래 유형은 Index A 에서 제외:
#   1) 폐지된 조문 ("제5조 삭제 <1989.12.30>", "제36조의2 삭제 <2020.6.9>")
#   2) 장·절·관·편 헤더 ("제1장 총칙", "제2절 동물의 보호 등")
#   3) 40자 미만의 의미 없는 토막 (제목만 있는 stub)
_DELETED_ARTICLE_RE = re.compile(r"^제\d+조(?:의\d+)?\s*삭제\s*<")
_STRUCTURAL_HEADER_RE = re.compile(r"^제\d+\s*[편장절관]\s")
_MIN_CONTENT_LEN = 40


def should_skip_article(content: str) -> bool:
    """RAG 품질 저해 청크 (폐지·헤더·stub) 판별."""
    c = (content or "").strip()
    if not c:
        return True
    if _DELETED_ARTICLE_RE.match(c):
        return True
    if _STRUCTURAL_HEADER_RE.match(c):
        return True
    if len(c) < _MIN_CONTENT_LEN:
        return True
    return False


def is_deleted_article(content: str) -> bool:
    """Deprecated — use should_skip_article. 호환성을 위해 유지."""
    return bool(_DELETED_ARTICLE_RE.match((content or "").strip()))


def minbeop_subcategory(article: str) -> str:
    """민법 조문 번호 → 편별 서브카테고리 (한국 민법 구조).

    §1-§184 총칙 / §185-§372 물권 / §373-§617 채권 총칙 /
    §618-§654 임대차 / §655-§766 기타 전형계약 / §767-§996 친족 / §997-§1118 상속
    """
    m = re.match(r"제(\d+)조", article)
    if not m:
        return "민법 기타"
    n = int(m.group(1))
    if n <= 184: return "민법 총칙"
    if n <= 372: return "민법 물권"
    if n <= 617: return "민법 채권 총칙"
    if n <= 654: return "민법 채권 — 임대차"
    if n <= 766: return "민법 채권 — 기타 전형계약"
    if n <= 996: return "민법 친족"
    return "민법 상속"


def resolve_category(law_name: str, article: str, fallback: str) -> str:
    """법령별 카테고리 결정. 민법은 편별로 세분, 나머지는 ingest 설정의 fallback 사용."""
    if law_name == "민법":
        return minbeop_subcategory(article)
    return fallback


# ===== 과태료·기한 자동 추출 =====
_PENALTY_PATTERNS = [
    (re.compile(r"(\d+(?:,\d{3})*(?:만|억)?원?)\s*이하의?\s*과태료"), "과태료"),
    (re.compile(r"과태료[^다]{0,15}?(\d+(?:,\d{3})*(?:만|억)?원?)"), "과태료"),
    (re.compile(r"(\d+(?:,\d{3})*(?:만|억)?원?)\s*이하의?\s*벌금"), "벌금"),
    (re.compile(r"벌금[^다]{0,15}?(\d+(?:,\d{3})*(?:만|억)?원?)"), "벌금"),
    (re.compile(r"(\d+)년\s*이하의?\s*징역"), "징역"),
]
_DEADLINE_PATTERNS = [
    re.compile(r"(\d+)\s*일\s*이내"),
    re.compile(r"(\d+)\s*주\s*이내"),
    re.compile(r"(\d+)\s*개월\s*이내"),
    re.compile(r"(\d+)\s*년\s*이내"),
]


def extract_penalties(text: str) -> list[str]:
    """본문에서 과태료·벌금·징역 금액 자동 추출."""
    found: set[str] = set()
    for pat, label in _PENALTY_PATTERNS:
        for m in pat.finditer(text):
            amount = m.group(1) if m.groups() else ""
            found.add(f"{label} {amount}".strip())
    return sorted(found)


def extract_deadlines(text: str) -> list[str]:
    """본문에서 '~일 이내', '~개월 이내' 같은 기한 표현 자동 추출."""
    found: set[str] = set()
    for pat in _DEADLINE_PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group(0).strip())
    return sorted(found)


def process_law(name: str, mst: int, note: str, oc: str) -> list[dict]:
    print(f"  ▶ {name} (MST={mst}) ...", end=" ")
    root = fetch_law(oc, mst)
    if root is None:
        print("SKIP")
        return []
    articles = parse_articles(root)
    doc = {
        "law_name": name,
        "mst": mst,
        "category_note": note,
        "source_url": f"https://www.law.go.kr/DRF/lawService.do?OC={oc}&target=law&type=XML&MST={mst}",
        "fetched_at": date.today().isoformat(),
        "article_count": len(articles),
        "articles": articles,
    }
    out_file = LAWS_DIR / f"{name}.json"
    out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {len(articles)} articles")

    # Index A chunks: one per article. RAG 품질 저해 청크 제외
    # (폐지 조문 / 장·절 헤더 / 40자 미만 stub)
    chunks = []
    skipped = 0
    for a in articles:
        content = a["content"]
        if should_skip_article(content):
            skipped += 1
            continue
        chunk_id = f"{name}__{a['article']}".replace(" ", "")
        chunks.append({
            "id": chunk_id,
            "law_name": name,
            "article": a["article"],
            "title": a["title"] or a["article"],
            "content": content,
            "keywords": extract_keywords(content, a.get("title", "")),
            "category": [resolve_category(name, a["article"], note)],
            "penalties": extract_penalties(content),
            "deadlines": extract_deadlines(content),
            "source_url": doc["source_url"],
            "last_updated": doc["fetched_at"],
        })
    if skipped:
        print(f"    (RAG 품질 필터 {skipped} 건 제외)")
    return chunks


def main() -> None:
    oc = load_env_oc()
    if not oc:
        print("❌ LAW_OC 미설정.")
        print()
        print("발급 절차:")
        print("  1) https://open.law.go.kr 로그인")
        print("  2) 마이페이지 → 신청내역에서 OC 값 확인")
        print("  3) .env 파일 LAW_OC= 에 입력")
        print("  4) 이 스크립트 재실행")
        sys.exit(2)

    print(f"OC confirmed: {oc[:3]}***")
    print()

    all_chunks: list[dict] = []
    for name, mst, note in LAWS:
        chunks = process_law(name, mst, note, oc)
        all_chunks.extend(chunks)
        time.sleep(0.5)

    # Write JSONL for Azure AI Search ingestion
    with INDEX_A_PATH.open("w", encoding="utf-8") as fp:
        for c in all_chunks:
            fp.write(json.dumps(c, ensure_ascii=False) + "\n")

    print()
    print(f"✅ 총 {len(all_chunks)} 청크 (Index A) → {INDEX_A_PATH}")
    # per-law summary
    from collections import Counter
    by_law = Counter(c["law_name"] for c in all_chunks)
    for law, cnt in by_law.most_common():
        print(f"  {law}: {cnt}")


if __name__ == "__main__":
    main()
