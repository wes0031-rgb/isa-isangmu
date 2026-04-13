"""Local chunk search — used as fallback when Azure AI Search is not configured.

Loads `index_b_chunks_curated.jsonl` (행정 절차) and `index_a_chunks.jsonl`
(법률 조문) once, and performs simple keyword scoring. This keeps `/checklist`
and `/safecontract` functional during local development before Azure setup.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

_INDEX_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "indexes"
)
CHUNKS_FILE = _INDEX_DIR / "index_b_chunks_curated.jsonl"
LAW_FILE = _INDEX_DIR / "index_a_chunks.jsonl"


# ---------- Index B (행정 절차) ----------


@lru_cache(maxsize=1)
def load_chunks() -> list[dict]:
    if not CHUNKS_FILE.exists():
        return []
    out = []
    with CHUNKS_FILE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                out.append(json.loads(line))
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
    if not LAW_FILE.exists():
        return []
    out = []
    with LAW_FILE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                out.append(json.loads(line))
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
