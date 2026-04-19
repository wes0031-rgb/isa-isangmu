"""Fetch law texts from law.go.kr DRF API using LAW_OC.

Saves each law as JSON (articles list) under backend/data/laws/
then chunks them into Azure AI Search index A format.

Changes in v2 (2026-04-17):
- English slug for filename & chunk ID (ASCII-safe for Azure Search)
- Article ID normalization: '제3조의2' → 'art3_2'
- Removed penalties field (team decision, commit bb59244)
- related_videos: hardcoded law-level mapping
- related_procedures: empty list (Phase 2 will populate)
- Unified 'fetched_at' field name (was 'last_updated' in chunks)

Changes in v3 (2026-04-19):
- Re-added `keywords` field per team meeting decision (검색 부스팅 효과)
  · 규칙 기반 추출: 조문 제목 괄호 + 도메인 화이트리스트 + 법 이름
  · 의존성 0 (konlpy 등 JVM NLP 미사용 → 팀원 Windows 온보딩 부담 ↓)
  · 정밀도 우선: Azure Semantic Search keywords 필드는 부스팅 용도라
    재현율보다 정밀도 중요 (noise 는 검색 품질 저하)

Usage:
  1) .env 의 LAW_OC 를 채운다
  2) python3 ingest_laws.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
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

# 수집할 법률 (한글명 → slug → MST → 카테고리)
# MST는 law.go.kr DRF의 법령 마스터 키. 확인 방법:
#   1) https://www.law.go.kr/법령/주택임대차보호법 접속
#   2) 페이지 하단 "공유" → "open API" 버튼 URL에서 MST=xxxx 확인
# slug는 영문 snake_case — 파일명/청크 ID에 사용 (ASCII only).
# 아래 값은 2026-04 기준. 변경되면 재확인 필요.
LAWS: list[tuple[str, str, int, str]] = [
    # (한글명,                  slug,                           MST,     카테고리)
    ("주택임대차보호법",          "housing_lease_protection",      276291, "임대차 대항력·확정일자·우선변제권"),
    ("주택임대차보호법 시행령",   "housing_lease_enforcement",     280995, "임대차 시행 기준"),
    ("주민등록법",               "resident_registration",         268555, "전입신고 의무·과태료"),
    ("주민등록법 시행령",         "resident_registration_enf",     266731, "신고 기한 상세"),
    ("동물보호법",               "animal_protection",             267325, "반려동물 주소변경 30일"),
    ("부동산등기법",              "real_estate_registration",      265377, "갑구·을구 구조"),
    ("민법",                    "civil_code",                    284415, "임대차 조항(제618조~)"),
    ("공동주택관리법",            "apartment_management",          280069, "관리비·장기수선충당금"),
]


# 법별 관련 영상 매핑 (수동 큐레이션)
# 기존 데이터 분석 결과 복원 — 법 단위로 동일 영상 세트 적용.
# 조문 단위 세분화 매핑은 Phase 2에서 vector similarity로 생성 예정.
LAW_TO_VIDEOS: dict[str, list[str]] = {
    "주택임대차보호법":         ["yt_4i-e1OmEGCQ_001", "yt_4i-e1OmEGCQ_003", "yt_4i-e1OmEGCQ_004"],
    "주택임대차보호법 시행령":  ["yt_4i-e1OmEGCQ_001", "yt_4i-e1OmEGCQ_003", "yt_4i-e1OmEGCQ_004"],
    "주민등록법":              ["yt_4i-e1OmEGCQ_001", "yt_4i-e1OmEGCQ_003", "yt_4i-e1OmEGCQ_004"],
    "주민등록법 시행령":        ["yt_4i-e1OmEGCQ_001", "yt_4i-e1OmEGCQ_003", "yt_4i-e1OmEGCQ_004"],
    "민법":                   ["yt_MIEObuovrSc_004", "yt_dFCz_ONk86o_000", "yt_dFCz_ONk86o_001"],
    "부동산등기법":             ["yt_MIEObuovrSc_004", "yt_dFCz_ONk86o_000", "yt_dFCz_ONk86o_001"],
    "공동주택관리법":           ["yt_4i-e1OmEGCQ_000", "yt_4i-e1OmEGCQ_001", "yt_4i-e1OmEGCQ_002"],
    "동물보호법":              [],  # 반려동물 영상 없음
}


def load_env_oc() -> str:
    if not ENV_PATH.exists():
        raise RuntimeError(f".env not found: {ENV_PATH}")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("LAW_OC="):
            return line.split("=", 1)[1].strip()
    return ""


def fetch_law(oc: str, mst: int) -> ET.Element | None:
    url = "https://www.law.go.kr/DRF/lawService.do"
    params = {"OC": oc, "target": "law", "type": "XML", "MST": mst}
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}")
        return None
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as exc:
        print(f"    parse error: {exc}")
        return None
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


def article_to_ascii(article: str) -> str:
    """'제3조의2' → 'art3_2', '제10조' → 'art10'.

    ASCII-safe conversion for Azure Search document keys.
    """
    m = re.match(r"제(\d+)조(?:의(\d+))?", article)
    if not m:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", article) or "unknown"
    main, sub = m.group(1), m.group(2)
    return f"art{main}_{sub}" if sub else f"art{main}"


# ===== RAG 품질 필터 =====
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
    """Deprecated — use should_skip_article. 하위 호환용."""
    c = (content or "").strip()
    return bool(_DELETED_ARTICLE_RE.match(c))


# ===== 카테고리 =====
def minbeop_subcategory(article: str) -> str:
    """민법 조문 번호 → 편별 서브카테고리."""
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
    if law_name == "민법":
        return minbeop_subcategory(article)
    return fallback


# ===== 기한 자동 추출 =====
_DEADLINE_PATTERNS = [
    re.compile(r"(\d+)\s*일\s*이내"),
    re.compile(r"(\d+)\s*주\s*이내"),
    re.compile(r"(\d+)\s*개월\s*이내"),
    re.compile(r"(\d+)\s*년\s*이내"),
]


def extract_deadlines(text: str) -> list[str]:
    found: set[str] = set()
    for pat in _DEADLINE_PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group(0).strip())
    return sorted(found)


# ===== 키워드 자동 추출 =====
# 도메인 화이트리스트 — 법률·이사 도메인 핵심 용어.
# 팀원이 직접 편집 가능. 새 법령 추가 시 해당 도메인 용어 여기에 반영.
# 원칙: 정밀도 우선 (noise 가 검색 품질 더 해침).
DOMAIN_KEYWORDS: frozenset[str] = frozenset({
    # 임대차 권리 (주택임대차보호법 중심)
    "대항력", "확정일자", "우선변제권", "최우선변제권",
    "임차권등기", "임차권등기명령", "전세권", "주택임차권", "상가임차권",
    # 계약
    "임대차", "임차인", "임대인", "보증금", "전세", "월세", "차임",
    "보증금반환", "계약갱신요구권", "묵시적갱신", "계약해지", "계약해제",
    "중개보수", "부동산중개",
    # 등기 · 담보권 (부동산등기법·민법 물권)
    "근저당권", "저당권", "가압류", "가처분", "압류",
    "소유권이전등기", "등기부등본", "신탁등기",
    # 경매 · 매매
    "경매", "공매", "매매", "낙찰",
    # 행정 신고 (주민등록법·동물보호법)
    "전입신고", "주민등록", "전출신고", "주소이전", "변동신고", "변경신고", "정정신고",
    # 반려동물
    "동물등록", "반려동물", "맹견",
    # 공동주택 관리 (공동주택관리법)
    "관리비", "장기수선충당금", "관리비예치금", "입주자대표회의",
    # 벌칙 · 제재
    "과태료", "벌금", "벌칙",
    # 민법 기본 개념
    "채권자", "채무자", "선의", "악의",
})

# 조문 제목 괄호 추출: "제3조(대항력 등)" → "대항력 등"
# 전각/반각 괄호 모두 대응
_BRACKET_RE = re.compile(r"[(（]([^)（）]+)[)）]")
_KW_SPLIT_RE = re.compile(r"[\s·,/]+")
_KW_STOPWORDS: frozenset[str] = frozenset({
    "등", "기타", "및", "또는", "경우", "관한", "관하여", "대한",
    "에", "의", "을", "를", "이", "가", "은", "는",
})
# 한국어 조사 후치 제거 (긴 조사부터 시도)
_POSTPOSITIONS_LONG: tuple[str, ...] = ("으로", "에서", "부터", "까지", "에게", "에는", "에도")
_POSTPOSITIONS_SHORT: tuple[str, ...] = ("의", "을", "를", "이", "가", "은", "는", "에", "과", "와", "도", "만", "로")
_MAX_KEYWORDS = 12


def _strip_postposition(word: str) -> str:
    """한국어 조사 후치 제거. 결과가 2자 이상일 때만 제거.

    예: '등록대상동물의' → '등록대상동물',  '보증금을' → '보증금',  '주택' → '주택' (변화 없음)
    """
    for pp in _POSTPOSITIONS_LONG:
        if word.endswith(pp) and len(word) - len(pp) >= 2:
            return word[:-len(pp)]
    for pp in _POSTPOSITIONS_SHORT:
        if word.endswith(pp) and len(word) - len(pp) >= 2:
            return word[:-len(pp)]
    return word


def extract_keywords(title: str, content: str, law_name: str) -> list[str]:
    """조문 제목 + 본문에서 검색 부스팅용 키워드 추출.

    전략 (정밀도 우선):
      1. 조문 제목 파싱
         · 괄호 있으면 괄호 안 내용 + 밖 내용 둘 다 처리
         · 괄호 없으면 제목 전체 토큰화 (DRF API 는 괄호 없이 반환)
         · 공백/중점/쉼표로 split → 조사 후치 제거 → stopwords 필터
      2. DOMAIN_KEYWORDS 화이트리스트와 본문 매칭
         · 짧은 조문 (< 200자): 1회 등장으로 충분
         · 긴 조문: 2회 이상 (우연 일치 필터)
      3. 법 이름 (공백 제거) 1개 추가

    Returns:
        정렬된 키워드 리스트, 최대 _MAX_KEYWORDS 개.
    """
    keywords: set[str] = set()

    # 1. 조문 제목 — 괄호 유무 무관하게 전체 파싱
    title_str = title or ""
    parts_to_split: list[str] = []
    bracket_matches = _BRACKET_RE.findall(title_str)
    if bracket_matches:
        parts_to_split.extend(bracket_matches)
    # 괄호 바깥 텍스트 (괄호 없으면 전체 = 제목 그대로)
    outside = _BRACKET_RE.sub(" ", title_str)
    parts_to_split.append(outside)

    for chunk in parts_to_split:
        for raw in _KW_SPLIT_RE.split(chunk):
            p = _strip_postposition(raw.strip())
            if len(p) >= 2 and p not in _KW_STOPWORDS:
                keywords.add(p)

    # 2. 도메인 사전 매칭
    threshold = 1 if len(content) < 200 else 2
    for term in DOMAIN_KEYWORDS:
        if content.count(term) >= threshold:
            keywords.add(term)

    # 3. 법 이름 (공백 제거 — Azure ko.microsoft 분석기가 형태 처리)
    keywords.add(law_name.replace(" ", ""))

    # 4. 정렬 + 상한
    return sorted(keywords)[:_MAX_KEYWORDS]


# ===== 청크 생성 =====
def process_law(name: str, slug: str, mst: int, note: str, oc: str) -> list[dict]:
    print(f"  ▶ {name} [{slug}] (MST={mst}) ...", end=" ")
    root = fetch_law(oc, mst)
    if root is None:
        print("SKIP")
        return []
    articles = parse_articles(root)
    doc = {
        "law_name": name,
        "law_slug": slug,
        "mst": mst,
        "category_note": note,
        "source_url": f"https://www.law.go.kr/DRF/lawService.do?OC={oc}&target=law&type=XML&MST={mst}",
        "fetched_at": date.today().isoformat(),
        "article_count": len(articles),
        "articles": articles,
    }
    # 파일명: 영문 slug 사용 (ASCII only)
    out_file = LAWS_DIR / f"{slug}.json"
    out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {len(articles)} articles → {out_file.name}")

    # Index A chunks
    related_videos = LAW_TO_VIDEOS.get(name, [])
    chunks = []
    skipped = 0
    for a in articles:
        content = a["content"]
        if should_skip_article(content):
            skipped += 1
            continue
        chunk_id = f"law_{slug}_{article_to_ascii(a['article'])}"
        chunks.append({
            "id": chunk_id,
            "law_name": name,              # 한글 유지 (검색/표시용)
            "article": a["article"],       # 한글 유지 (표시용)
            "title": a["title"] or a["article"],
            "content": content,
            "category": [resolve_category(name, a["article"], note)],
            "keywords": extract_keywords(a["title"], content, name),  # 4/19 팀 결정 반영
            "deadlines": extract_deadlines(content),
            "related_procedures": [],      # Phase 2: vector similarity로 채움
            "related_videos": related_videos,  # 법별 하드코딩 매핑
            "source_url": doc["source_url"],
            "fetched_at": doc["fetched_at"],
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
    for name, slug, mst, note in LAWS:
        chunks = process_law(name, slug, mst, note, oc)
        all_chunks.extend(chunks)
        time.sleep(0.5)

    with INDEX_A_PATH.open("w", encoding="utf-8") as fp:
        for c in all_chunks:
            fp.write(json.dumps(c, ensure_ascii=False) + "\n")

    print()
    print(f"✅ 총 {len(all_chunks)} 청크 (Index A) → {INDEX_A_PATH.relative_to(ROOT)}")
    by_law = Counter(c["law_name"] for c in all_chunks)
    for law, cnt in by_law.most_common():
        print(f"  {law}: {cnt}")

    # keywords 통계
    kw_counts = [len(c["keywords"]) for c in all_chunks]
    with_kw = sum(1 for n in kw_counts if n > 0)
    avg_kw = sum(kw_counts) / len(kw_counts) if kw_counts else 0
    print()
    print(f"  keywords: 평균 {avg_kw:.1f}개/청크, {with_kw}/{len(all_chunks)} 청크에 키워드 있음")


if __name__ == "__main__":
    main()