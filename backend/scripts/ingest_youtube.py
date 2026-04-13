"""유튜브 자막 크롤링 → 청크 변환 → Index C JSONL 생성.

MoveWise 챗봇의 추가 지식 소스(Index C)를 만드는 스크립트.
youtube-transcript-api 로 무료로 공식/자동 자막을 받고,
oEmbed 로 제목·채널을 가져와서 메타데이터 부착.

Usage:
  python3 backend/scripts/ingest_youtube.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "backend" / "data" / "raw" / "youtube_transcripts"
OUT_FILE = ROOT / "backend" / "data" / "indexes" / "index_c_youtube_chunks.jsonl"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# 수집 대상 영상 ID (MoveWise 이사/전세/전세사기 관련)
VIDEO_IDS: list[str] = [
    "MIEObuovrSc",  # 이사 당일 체크 6가지
    "iY3d1JAQsKY",  # 똑똑한 정리
    "OCtjQJqtYyc",  # 이사 2달 전 체크리스트 7가지
    "dFCz_ONk86o",  # 등기부등본·전세사기 예방
    "PamLLxiCPqo",  # 이삿짐 포장·보관·방범
    "4i-e1OmEGCQ",  # 이사 비용 절감 팁
    "Gpf8slBLVe4",  # 손 없는 날·가전 처분
    "oYt9Xv3d2Wo",  # 전세 특약 5가지·깡통전세
    "BtbnY7enQMQ",  # 포장이사 전날 체크 10가지
    "Ej8MDFj37zg",  # 포장이사 전 준비팁
    "gkeglF2m_WA",  # 이사 준비물 리스트
    "aw-cvULahyA",  # 이사 비용 꿀팁
]

# 청크 당 목표 글자수 (한국어 기준 약 2~3문장)
TARGET_CHARS = 400
MAX_CHARS = 600

# 카테고리 자동 분류 키워드
CATEGORY_KEYWORDS = {
    "전세사기 예방": [
        "전세사기",
        "깡통전세",
        "등기부",
        "근저당",
        "특약",
        "보증금",
        "임차권등기",
        "대항력",
        "확정일자",
    ],
    "이사 준비": [
        "포장",
        "짐",
        "박스",
        "정리",
        "버리",
        "수거",
        "청소",
        "에어캡",
        "테이프",
        "구루마",
    ],
    "이사 비용": ["비용", "가격", "할인", "저렴", "꿀팁", "견적", "손없는날"],
    "공과금·행정": [
        "전입신고",
        "주민센터",
        "정부24",
        "공과금",
        "가스",
        "수도",
        "전기",
        "인터넷",
        "관리비",
    ],
    "이사 일반": [],  # fallback
}


def fetch_metadata(vid: str) -> dict:
    """oEmbed API 로 영상 제목·채널 메타데이터 가져오기 (무료, 인증 불필요)."""
    url = f"https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D{quote(vid)}&format=json"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return {
            "title": data.get("title", ""),
            "channel": data.get("author_name", ""),
            "channel_url": data.get("author_url", ""),
            "thumbnail": data.get("thumbnail_url", ""),
        }
    except Exception as exc:
        print(f"    ⚠️ oEmbed 실패 ({vid}): {exc}")
        return {"title": f"YouTube {vid}", "channel": "", "channel_url": "", "thumbnail": ""}


def fetch_transcript(vid: str) -> list[dict]:
    """한국어 자막 우선, 실패 시 가용 자막 아무거나."""
    api = YouTubeTranscriptApi()
    try:
        ft = api.fetch(vid, languages=["ko"])
    except Exception:
        try:
            ft = api.fetch(vid)
        except (
            NoTranscriptFound,
            TranscriptsDisabled,
            VideoUnavailable,
            Exception,
        ) as exc:
            print(f"    ❌ 자막 수집 실패: {exc}")
            return []
    return [
        {"text": s.text.strip(), "start": s.start, "duration": s.duration}
        for s in ft
    ]


def chunk_transcript(
    snippets: list[dict],
    target_chars: int = TARGET_CHARS,
    max_chars: int = MAX_CHARS,
) -> list[dict]:
    """시간순으로 snippet 을 target_chars 에 가깝게 묶어 청크 생성.

    각 청크는 start_seconds / end_seconds 를 갖고, 내용은 snippet 텍스트를
    공백으로 이어붙인 평문.
    """
    chunks: list[dict] = []
    buf: list[str] = []
    buf_start: float | None = None
    buf_end: float = 0.0
    buf_chars = 0

    for s in snippets:
        text = s["text"]
        if not text or text in ("[음악]", "[박수]"):
            continue
        if buf_start is None:
            buf_start = s["start"]
        buf.append(text)
        buf_end = s["start"] + s["duration"]
        buf_chars += len(text) + 1

        if buf_chars >= target_chars:
            # 현재 버퍼를 청크로 확정
            chunks.append(
                {
                    "start_seconds": round(buf_start, 2),
                    "end_seconds": round(buf_end, 2),
                    "content": " ".join(buf).strip(),
                }
            )
            buf = []
            buf_start = None
            buf_chars = 0

    # 남은 버퍼 처리
    if buf:
        chunks.append(
            {
                "start_seconds": round(buf_start or 0.0, 2),
                "end_seconds": round(buf_end, 2),
                "content": " ".join(buf).strip(),
            }
        )

    # max_chars 넘는 청크는 중간에서 분할
    final: list[dict] = []
    for c in chunks:
        content = c["content"]
        if len(content) <= max_chars:
            final.append(c)
            continue
        # 공백 기준 대략 분할
        pieces = []
        current = ""
        for word in content.split(" "):
            if len(current) + len(word) + 1 > max_chars:
                pieces.append(current.strip())
                current = word
            else:
                current += " " + word
        if current.strip():
            pieces.append(current.strip())
        # 시간은 원본 구간 전체로 사용 (분할 비율 계산 생략)
        for p in pieces:
            final.append(
                {
                    "start_seconds": c["start_seconds"],
                    "end_seconds": c["end_seconds"],
                    "content": p,
                }
            )
    return final


def categorize(text: str) -> list[str]:
    """키워드 기반 카테고리 자동 분류 (중복 가능)."""
    cats: list[str] = []
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if not keywords:
            continue
        for kw in keywords:
            if kw in text:
                cats.append(cat)
                break
    if not cats:
        cats = ["이사 일반"]
    return cats


def format_timecode(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def process_video(vid: str) -> list[dict]:
    print(f"▶ {vid}")
    meta = fetch_metadata(vid)
    print(f"    title: {meta['title']}")
    print(f"    channel: {meta['channel']}")

    snippets = fetch_transcript(vid)
    if not snippets:
        return []
    print(f"    snippets: {len(snippets)}")

    # raw JSON 저장 (재사용·감사용)
    raw_path = RAW_DIR / f"{vid}.json"
    raw_path.write_text(
        json.dumps(
            {
                "video_id": vid,
                "fetched_at": date.today().isoformat(),
                "metadata": meta,
                "transcript": snippets,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 청크 생성
    raw_chunks = chunk_transcript(snippets)
    print(f"    chunks: {len(raw_chunks)}")

    docs: list[dict] = []
    source_url = f"https://www.youtube.com/watch?v={vid}"
    for i, c in enumerate(raw_chunks):
        deep_link = f"{source_url}&t={int(c['start_seconds'])}s"
        docs.append(
            {
                "id": f"yt_{vid}_{i:03d}",
                "source_type": "youtube",
                "video_id": vid,
                "video_title": meta["title"],
                "channel": meta["channel"],
                "channel_url": meta["channel_url"],
                "source_url": source_url,
                "deep_link": deep_link,
                "start_seconds": c["start_seconds"],
                "end_seconds": c["end_seconds"],
                "timecode": format_timecode(c["start_seconds"]),
                "content": c["content"],
                "category": categorize(c["content"]),
                "fetched_at": date.today().isoformat(),
            }
        )
    return docs


def main() -> None:
    all_docs: list[dict] = []
    for vid in VIDEO_IDS:
        docs = process_video(vid)
        all_docs.extend(docs)
        time.sleep(0.3)  # rate limit 완화

    # JSONL 저장
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for d in all_docs:
            fp.write(json.dumps(d, ensure_ascii=False) + "\n")

    # 카테고리별 집계
    from collections import Counter

    by_video = Counter(d["video_id"] for d in all_docs)
    cat_counter: Counter[str] = Counter()
    for d in all_docs:
        for c in d["category"]:
            cat_counter[c] += 1

    print()
    print("=" * 50)
    print(f"✅ 총 {len(all_docs)} 청크 · {len(VIDEO_IDS)} 영상")
    print(f"📁 {OUT_FILE.relative_to(ROOT)}")
    print()
    print("영상별 청크 수:")
    for vid, cnt in by_video.most_common():
        print(f"  {vid}: {cnt}")
    print()
    print("카테고리 분포:")
    for cat, cnt in cat_counter.most_common():
        print(f"  {cat}: {cnt}")


if __name__ == "__main__":
    main()
