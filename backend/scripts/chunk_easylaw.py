"""Split easylaw JSON docs into RAG-ready chunks with metadata.

Input : backend/data/procedures/easylaw/easylaw-*.json  (53개)
Output: backend/data/indexes/index_b_chunks.jsonl       (JSONL, 1 chunk/line)
        backend/data/indexes/index_b_summary.json       (통계)

Chunking strategy:
- 문단 단위로 1차 분할 → MAX_SIZE 초과 시 문장 단위 재분할
- MIN_SIZE 이하면 인접 문단과 병합
- 청크마다 deadline / penalty / related_law / category 메타 추출

변경사항 (2026-04-19):
- Mac 하드코딩 경로 제거 → ROOT 기반 크로스플랫폼 (ingest_easylaw.py 와 동일 패턴)
- Windows 호환 encoding="utf-8" 명시 유지
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # 2차프로젝트
IN_DIR = ROOT / "backend" / "data" / "procedures" / "easylaw"
OUT_DIR = ROOT / "backend" / "data" / "indexes"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_SIZE = 700  # chars
MIN_SIZE = 250
MAX_SIZE = 1100


CATEGORY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"전입신고"), "전입신고"),
    (re.compile(r"확정일자|대항력|우선변제권"), "확정일자/임차권"),
    (re.compile(r"전학|학교"), "자녀 전학"),
    (re.compile(r"반려동물|동물등록|애완"), "반려동물 주소변경"),
    (re.compile(r"자동차\s*변경등록|자동차 주소"), "자동차 주소변경"),
    (re.compile(r"전기|한전"), "공과금-전기"),
    (re.compile(r"수도|상수도"), "공과금-수도"),
    (re.compile(r"도시가스|가스\s*명의|LPG"), "공과금-가스"),
    (re.compile(r"관리비예치금|장기수선충당금|관리비"), "공과금-관리비"),
    (re.compile(r"우편|우체국"), "우편물 전환"),
    (re.compile(r"인터넷\s*이전|통신사|TV 이전"), "통신사 이전"),
    (re.compile(r"이사업체|이삿짐|포장이사"), "이사업체"),
    (re.compile(r"계약서|임대차 계약|중개보수"), "계약서"),
    (re.compile(r"등기|소유권 이전"), "등기"),
    (re.compile(r"분양|청약|경매"), "집 구하기-분양경매"),
    (re.compile(r"대출|자금"), "집 구하기-자금"),
    (re.compile(r"집 구하기|주변조사|주변\s*조사"), "집 구하기-일반"),
    (re.compile(r"집 내놓기|매매|양도"), "집 내놓기"),
    (re.compile(r"주택 수리|하자"), "주택 수리"),
    (re.compile(r"세금|세액공제|취득세|양도소득세"), "세금"),
    (re.compile(r"분쟁|조정|소송"), "분쟁 해결"),
    (re.compile(r"보증금|월세|전세"), "보증금/임대차 일반"),
]

DEADLINE_RE = re.compile(r"(\d+)\s*(일|개월|월|년)\s*이내")
PENALTY_RE = re.compile(r"(\d+)\s*만원(?:\s*이하)?\s*(?:의\s*)?과태료")
CITATION_RE = re.compile(
    r"「\s*([^」]+?법(?:\s*시행(?:령|규칙))?)\s*」"
    r"\s*제\s*(\d+)\s*조(?:의\s*(\d+))?"
    r"(?:\s*제\s*(\d+)\s*항)?"
)


def classify_category(breadcrumb: str, title: str, content: str) -> list[str]:
    haystack = f"{breadcrumb} {title} {content[:500]}"
    matched = []
    for pattern, label in CATEGORY_RULES:
        if pattern.search(haystack):
            matched.append(label)
    return matched or ["일반"]


def extract_deadlines(text: str) -> list[str]:
    return sorted({f"{n}{unit}" for n, unit in DEADLINE_RE.findall(text)})


def extract_penalties(text: str) -> list[str]:
    return sorted({f"{m}만원 이하 과태료" for m in PENALTY_RE.findall(text)})


def extract_citations(text: str) -> list[str]:
    found: list[str] = []
    for law, art, art_sub, para in CITATION_RE.findall(text):
        law_clean = re.sub(r"\s+", "", law)
        cite = f"{law_clean} 제{art}조"
        if art_sub:
            cite += f"의{art_sub}"
        if para:
            cite += f" 제{para}항"
        found.append(cite)
    return sorted(set(found))


def split_paragraphs(text: str) -> list[str]:
    # easylaw 본문은 개행으로 섹션 구분이 잘 되어 있음
    paras = [p.strip() for p in re.split(r"\n{2,}|\n(?=[가-힣])", text)]
    return [p for p in paras if p]


def pack_chunks(paragraphs: list[str]) -> list[str]:
    """Greedy merging of short paragraphs, splitting of long ones."""
    chunks: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf.strip():
            chunks.append(buf.strip())
        buf = ""

    for p in paragraphs:
        if len(p) > MAX_SIZE:
            flush()
            # split on sentence boundaries
            sentences = re.split(r"(?<=[.?!。])\s+", p)
            sub = ""
            for s in sentences:
                if len(sub) + len(s) + 1 > TARGET_SIZE and len(sub) >= MIN_SIZE:
                    chunks.append(sub.strip())
                    sub = s
                else:
                    sub = f"{sub} {s}".strip()
            if sub.strip():
                chunks.append(sub.strip())
            continue

        if len(buf) + len(p) + 1 > TARGET_SIZE:
            if len(buf) >= MIN_SIZE:
                flush()
                buf = p
            else:
                buf = f"{buf}\n{p}".strip()
                if len(buf) >= TARGET_SIZE:
                    flush()
        else:
            buf = f"{buf}\n{p}".strip()

    flush()
    return chunks


def process_doc(doc: dict) -> list[dict]:
    paragraphs = split_paragraphs(doc["content"])
    chunks = pack_chunks(paragraphs)
    result = []
    doc_categories = classify_category(
        doc.get("breadcrumb", ""), doc.get("title", ""), doc["content"]
    )

    for idx, chunk_text in enumerate(chunks):
        chunk_cats = classify_category(
            doc.get("breadcrumb", ""), doc.get("title", ""), chunk_text
        )
        # 청크가 자체 키워드 없으면 문서 전체 카테고리 사용
        if chunk_cats == ["일반"]:
            chunk_cats = doc_categories

        record = {
            "id": f"{doc['id']}__chunk-{idx:02d}",
            "parent_doc": doc["id"],
            "source": doc["source"],
            "source_url": doc["url"],
            "category_root": doc.get("category_root"),
            "breadcrumb": doc.get("breadcrumb"),
            "doc_title": doc.get("title"),
            "category": chunk_cats,
            "content": chunk_text,
            "content_length": len(chunk_text),
            "deadlines": extract_deadlines(chunk_text),
            "penalties": extract_penalties(chunk_text),
            "related_laws": extract_citations(chunk_text),
            "applicable_to": ["자취", "신혼", "가족"],  # 기본값, Phase 2 에서 LLM 분류
            "contract_type": ["전세", "월세"],          # 기본값
            "region": "전국",                              # 기본값
            "fetched_at": doc.get("fetched_at"),
            "chunk_index": idx,
            "chunk_total": len(chunks),
        }
        result.append(record)
    return result


def main() -> None:
    files = sorted(IN_DIR.glob("easylaw-*.json"))
    print(f"loading {len(files)} docs from {IN_DIR.relative_to(ROOT)} ...")
    if not files:
        print(f"❌ {IN_DIR} 에 easylaw-*.json 파일이 없습니다. ingest_easylaw.py 먼저 실행하세요.")
        return

    all_chunks: list[dict] = []
    per_doc_counts: dict[str, int] = {}

    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        chunks = process_doc(doc)
        per_doc_counts[doc["id"]] = len(chunks)
        all_chunks.extend(chunks)

    out_jsonl = OUT_DIR / "index_b_chunks.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as fp:
        for rec in all_chunks:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # stats
    cat_counter: Counter[str] = Counter()
    for c in all_chunks:
        for cat in c["category"]:
            cat_counter[cat] += 1

    with_deadline = sum(1 for c in all_chunks if c["deadlines"])
    with_penalty = sum(1 for c in all_chunks if c["penalties"])
    with_law = sum(1 for c in all_chunks if c["related_laws"])
    avg_len = sum(c["content_length"] for c in all_chunks) / len(all_chunks) if all_chunks else 0

    summary = {
        "generated_at": date.today().isoformat(),
        "source_docs": len(files),
        "total_chunks": len(all_chunks),
        "avg_chunk_length": round(avg_len, 1),
        "chunks_with_deadline": with_deadline,
        "chunks_with_penalty": with_penalty,
        "chunks_with_law_citation": with_law,
        "category_distribution": dict(cat_counter.most_common()),
        "per_doc_chunk_count": per_doc_counts,
    }
    (OUT_DIR / "index_b_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print(f"✅ {len(all_chunks)} chunks saved → {out_jsonl.relative_to(ROOT)}")
    print(f"   avg chunk size: {summary['avg_chunk_length']} chars")
    print(f"   with deadline : {with_deadline}")
    print(f"   with penalty  : {with_penalty}")
    print(f"   with law cite : {with_law}")
    print()
    print("   category distribution:")
    for cat, cnt in cat_counter.most_common():
        print(f"     {cat:25s} {cnt:3d}")


if __name__ == "__main__":
    main()