"""Local chunk search — used as fallback when Azure AI Search is not configured.

Loads `index_b_chunks_curated.jsonl` (행정 절차) and `index_a_chunks.jsonl`
(법률 조문) once, and performs simple keyword scoring. This keeps `/checklist`
and `/safecontract` functional during local development before Azure setup.

모든 데이터는 로드 시점에 한자 병기 제거(clean_hanja)를 거침.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

# ---------- 한자 제거 ----------

_HANJA_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]")
_HANJA_PARENS_RE = re.compile(
    r"\(\s*[\u3400-\u4DBF\u4E00-\u9FFF]+(?:\s*[·,、\s]\s*[\u3400-\u4DBF\u4E00-\u9FFF]+)*\s*\)"
)


def clean_hanja(text: str) -> str:
    """한국 법조문에서 한자 병기·잔여 한자 전부 제거.

    추가로 macOS/Windows 간 한글 자모 분리(NFD) 불일치를 막기 위해
    NFC 정규화를 항상 먼저 적용한다.
    """
    if not text:
        return text
    text = unicodedata.normalize("NFC", text)
    if not _HANJA_RE.search(text):
        return text
    cleaned = _HANJA_PARENS_RE.sub("", text)
    cleaned = _HANJA_RE.sub("", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r"\s+([,.·])", r"\1", cleaned)
    return cleaned.strip()


def _scrub_record(rec: dict) -> dict:
    """청크의 모든 텍스트 필드에 clean_hanja 적용."""
    TEXT_FIELDS = (
        "content", "title", "doc_title", "breadcrumb",
        "description", "method", "law_name",
    )
    out = dict(rec)
    for f in TEXT_FIELDS:
        if f in out and isinstance(out[f], str):
            out[f] = clean_hanja(out[f])
    # List-of-string 필드
    for f in ("category", "applicable_to", "contract_type",
              "deadlines", "penalties", "related_laws", "keywords"):
        if f in out and isinstance(out[f], list):
            out[f] = [clean_hanja(x) if isinstance(x, str) else x for x in out[f]]
    return out

_INDEX_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "indexes"
)
# 통합 인덱스 (Option B) — source_type 으로 구분 (영상 인덱스 제거됨, 2026-04-23)
UNIFIED_FILE = _INDEX_DIR / "index_unified.jsonl"
# 레거시 2 인덱스 (unified 가 없을 때 fallback)
CHUNKS_FILE = _INDEX_DIR / "index_b_chunks_curated.jsonl"
LAW_FILE = _INDEX_DIR / "index_a_chunks.jsonl"


# ---------- 통합 인덱스 로더 ----------


@lru_cache(maxsize=1)
def load_unified() -> list[dict]:
    """통합 인덱스 전체 로드. 파일 없으면 빈 리스트."""
    if not UNIFIED_FILE.exists():
        return []
    out = []
    with UNIFIED_FILE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                out.append(_scrub_record(json.loads(line)))
    return out


def _filter_by_source_type(chunks: list[dict], source_type: str) -> list[dict]:
    return [c for c in chunks if c.get("source_type") == source_type]


# ---------- Index B (행정 절차) ----------


@lru_cache(maxsize=1)
def load_chunks() -> list[dict]:
    """행정절차(Index B) 청크 로드.

    통합 인덱스(`index_unified.jsonl`) 가 있으면 거기서 source_type=procedure
    필터해서 반환. 없으면 레거시 `index_b_chunks_curated.jsonl` 로 fallback.
    """
    unified = load_unified()
    if unified:
        # 통합 인덱스 레코드는 unified 스키마 필드를 쓰므로 기존 scorer 가 참조하는
        # doc_title 필드를 title 로 매핑해 호환성 유지
        procs = _filter_by_source_type(unified, "procedure")
        return [{**c, "doc_title": c.get("title") or c.get("doc_title") or ""} for c in procs]
    if not CHUNKS_FILE.exists():
        return []
    out = []
    with CHUNKS_FILE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                out.append(_scrub_record(json.loads(line)))
    return out


def _tokenize(text: str) -> list[str]:
    # 한글 2자 이상 + 영문 2자 이상
    return re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}", text)


def score_chunk(chunk: dict, query_tokens: list[str]) -> float:
    haystack = " ".join(
        [
            chunk.get("doc_title") or "",
            chunk.get("breadcrumb") or "",
            chunk.get("content") or "",
            " ".join(chunk.get("category") or []),
            " ".join(chunk.get("related_laws") or []),
        ]
    )
    hay_tokens = Counter(_tokenize(haystack))
    score = 0.0
    for q in query_tokens:
        if q in hay_tokens:
            score += 1 + 0.2 * hay_tokens[q]  # saturating tf
    # bonus for deadline/penalty presence
    if chunk.get("deadlines"):
        score += 0.3
    if chunk.get("related_laws"):
        score += 0.2
    return score


def search(queries: list[str], top_k_per_query: int = 3) -> list[dict]:
    chunks = load_chunks()
    if not chunks:
        return []
    seen: set[str] = set()
    results: list[dict] = []
    for q in queries:
        q_tokens = _tokenize(q)
        if not q_tokens:
            continue
        scored = [(score_chunk(c, q_tokens), c) for c in chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        for s, c in scored[:top_k_per_query]:
            if s <= 0:
                continue
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            results.append({**c, "_local_score": round(s, 2), "_query": q})
    return results


# ---------- Index A (법률 조문) ----------


@lru_cache(maxsize=1)
def load_laws() -> list[dict]:
    """법률 조문(Index A) 로드. 통합 인덱스 우선, 레거시 fallback."""
    unified = load_unified()
    if unified:
        return _filter_by_source_type(unified, "law")
    if not LAW_FILE.exists():
        return []
    out = []
    with LAW_FILE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                out.append(_scrub_record(json.loads(line)))
    return out


@lru_cache(maxsize=1)
def _law_index() -> dict[tuple[str, str], dict]:
    """Exact-match lookup by (law_name, article)."""
    idx: dict[tuple[str, str], dict] = {}
    for c in load_laws():
        key = (
            _normalize_law_name(c.get("law_name", "")),
            _normalize_article(c.get("article", "")),
        )
        idx[key] = c
    return idx


def _normalize_law_name(name: str) -> str:
    # "주택임대차보호법 시행령" / "주택임대차보호법시행령" 양쪽 모두 허용
    return name.replace(" ", "").strip()


def _normalize_article(article: str) -> str:
    # "제16조", "제 16조", "제16조의2" 정규화
    return article.replace(" ", "").strip()


def find_law_article(law_name: str, article: str) -> dict | None:
    """단일 조문 정확 조회. 찾으면 dict, 없으면 None."""
    key = (_normalize_law_name(law_name), _normalize_article(article))
    return _law_index().get(key)


def get_article_text(law_name: str, article: str, max_chars: int = 500) -> str | None:
    """조문 내용만 반환. 길면 자른다."""
    found = find_law_article(law_name, article)
    if not found:
        return None
    text = (found.get("content") or "").strip()
    if not text:
        return None
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def score_law(chunk: dict, query_tokens: list[str]) -> float:
    haystack = " ".join(
        [
            chunk.get("law_name") or "",
            chunk.get("title") or "",
            chunk.get("content") or "",
            " ".join(chunk.get("category") or []),
        ]
    )
    hay_tokens = Counter(_tokenize(haystack))
    score = 0.0
    for q in query_tokens:
        if q in hay_tokens:
            score += 1 + 0.2 * hay_tokens[q]
    return score


def search_laws(queries: list[str], top_k_per_query: int = 2) -> list[dict]:
    """법률 전문 검색. Index B 와 함께 쓰면 체크리스트 citations 후처리에 활용 가능."""
    laws = load_laws()
    if not laws:
        return []
    seen: set[str] = set()
    results: list[dict] = []
    for q in queries:
        q_tokens = _tokenize(q)
        if not q_tokens:
            continue
        scored = [(score_law(c, q_tokens), c) for c in laws]
        scored.sort(key=lambda x: x[0], reverse=True)
        for s, c in scored[:top_k_per_query]:
            if s <= 0:
                continue
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            results.append({**c, "_local_score": round(s, 2), "_query": q})
    return results


# Index C (유튜브 자막) — 저작권 우려로 2026-04-23 제거. load_youtube/score_youtube/
# search_youtube 함수 모두 삭제. unified index 의 source_type=video 청크도 ingest
# 단계에서 제외 (video_chunks.jsonl · index_c_youtube_chunks.jsonl 도 git rm 대상).
