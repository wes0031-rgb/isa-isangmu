"""Fetch law texts from law.go.kr DRF API using LAW_OC.

Saves each law as JSON (articles list) under backend/data/laws/
then chunks them into Azure AI Search index A format.

Usage:
  1) .env 의 LAW_OC 를 채운다
  2) python3 ingest_laws.py
"""
from __future__ import annotations

import json
import os
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


def extract_keywords(text: str) -> list[str]:
    # 간단한 키워드 추출: 반복 등장하는 명사
    candidates = re.findall(r"[가-힣]{2,}", text)
    from collections import Counter
    top = [w for w, c in Counter(candidates).most_common() if c >= 2 and len(w) >= 2]
    return top[:8]


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

    # Index A chunks: one per article
    chunks = []
    for a in articles:
        content = a["content"]
        chunk_id = f"{name}__{a['article']}".replace(" ", "")
        chunks.append({
            "id": chunk_id,
            "law_name": name,
            "article": a["article"],
            "title": a["title"] or a["article"],
            "content": content,
            "keywords": extract_keywords(content),
            "category": [note],
            "source_url": doc["source_url"],
            "last_updated": doc["fetched_at"],
        })
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
