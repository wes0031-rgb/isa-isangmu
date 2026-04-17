"""레거시 필드 제거 + easylaw 네비·푸터 노이즈 청소.

1. Index A (law):  last_updated 제거 (Azure에선 fetched_at으로 통일됨)
2. Index B (procedure): source / category_root / content_length 제거
                         + content 상단 네비게이션·하단 푸터·중간 노이즈 제거
3. Index C (video): channel_url / source_type 제거 (Azure unify 시 재설정됨)

이후 unify_indexes.py 를 다시 돌려 index_unified.jsonl 재생성 → Azure 업로드.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path("/Users/sa/Desktop/2차프로젝트/backend/data/indexes")


def clean_procedure_content(text: str) -> str:
    """easylaw 크롤링 산출물에서 네비/푸터/노이즈 제거."""
    if not text:
        return text

    lines = text.split("\n")

    # 1) 상단 네비 블록 제거 — "현재위치 및 공유하기" 로 시작하는 청크 한정
    #    "관련법령" 줄 이후부터가 실제 본문.
    if lines and lines[0].strip() == "현재위치 및 공유하기":
        cut = None
        for i, ln in enumerate(lines):
            if ln.strip() == "관련법령":
                cut = i + 1
                break
        if cut is not None:
            lines = lines[cut:]

    text = "\n".join(lines)

    # 2) 푸터 제거 — "이 정보는 YYYY년..." 또는 "생활법령정보는 법적 효력..." 이후 자르기
    for marker in ("이 정보는", "생활법령정보는 법적 효력"):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx].rstrip()
            break

    # 3) 중간 고립 노이즈 — "인쇄체크" 같은 단독 줄
    text = re.sub(r"(?m)^[ \t]*인쇄체크[ \t]*$\n?", "", text)

    # 4) 빈 줄 3+연속 → 2줄로 축약
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _iter_records(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def clean_law(path: Path) -> tuple[int, int]:
    records = list(_iter_records(path))
    removed = 0
    for d in records:
        if "last_updated" in d:
            del d["last_updated"]
            removed += 1
    _write(path, records)
    return len(records), removed


def clean_procedure(path: Path) -> tuple[int, int, int]:
    records = list(_iter_records(path))
    content_changed = 0
    field_removed = 0
    for d in records:
        before = d.get("content", "")
        after = clean_procedure_content(before)
        if after != before:
            content_changed += 1
        d["content"] = after
        for f in ("source", "category_root", "content_length"):
            if f in d:
                del d[f]
                field_removed += 1
    _write(path, records)
    return len(records), content_changed, field_removed


def clean_video(path: Path) -> tuple[int, int]:
    records = list(_iter_records(path))
    removed = 0
    for d in records:
        for f in ("channel_url", "source_type"):
            if f in d:
                del d[f]
                removed += 1
    _write(path, records)
    return len(records), removed


def main() -> None:
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("레거시 필드 + 네비 노이즈 정리")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    a = ROOT / "index_a_chunks.jsonl"
    if a.exists():
        n, rm = clean_law(a)
        print(f"[A law]        {n}건 · last_updated 제거: {rm}")

    for p in (ROOT / "index_b_chunks.jsonl", ROOT / "index_b_chunks_curated.jsonl"):
        if not p.exists():
            continue
        n, changed, rm = clean_procedure(p)
        print(f"[B {p.name:<32}] {n}건 · content 정리: {changed} · 필드 제거: {rm}")

    c = ROOT / "index_c_youtube_chunks.jsonl"
    if c.exists():
        n, rm = clean_video(c)
        print(f"[C video]      {n}건 · channel_url/source_type 제거: {rm}")

    print()
    print("✅ 원본 jsonl 정리 완료.")
    print("▶ 다음: unify_indexes.py 재실행 → index_unified.jsonl 재생성")
    print("    python3 backend/scripts/unify_indexes.py")


if __name__ == "__main__":
    main()
