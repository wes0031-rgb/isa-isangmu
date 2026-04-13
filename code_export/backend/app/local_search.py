"""Local chunk search — used as fallback when Azure AI Search is not configured.

Loads `index_b_chunks_curated.jsonl` once and performs simple keyword scoring.
This keeps `/checklist` functional during local development before Azure setup.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

CHUNKS_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "indexes"
    / "index_b_chunks_curated.jsonl"
)


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
