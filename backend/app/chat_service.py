"""챗봇 서비스 — fallback 키워드 RAG + Azure OpenAI 승격 지원.

Azure 연결 전:
  사용자 질문 → 토큰화 → Index A(법률) + Index B(절차) + Index C(유튜브) 검색 →
  상위 청크로 구조화된 답변 + citation 생성

Azure 연결 후:
  같은 검색 결과를 GPT-4o 에 context 로 전달해서 자연어 답변 생성
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .azure_clients import get_openai_client
from .config import get_settings
from .local_search import (
    clean_hanja,
    search as search_procedures,
    search_laws,
    search_youtube,
)

logger = logging.getLogger("movewise")


@dataclass
class ChatCitation:
    source_type: str  # "law" | "procedure" | "youtube"
    title: str
    content_snippet: str
    url: Optional[str] = None
    meta: dict = field(default_factory=dict)


@dataclass
class ChatReply:
    answer: str
    mode: str  # "fallback" | "azure"
    citations: list[ChatCitation] = field(default_factory=list)
    used_queries: list[str] = field(default_factory=list)


CHAT_SYSTEM_PROMPT = """당신은 한국 이사·전월세 절차 전문 도우미입니다.
사용자 질문에 대해 반드시 주어진 '검색 결과' 에 있는 내용만 사용하여 답변하세요.

규칙:
1. 답변은 한국어로 2~4문장, 쉬운 말로 작성
2. 법 조항을 인용할 때는 [주민등록법 제16조] 형식으로 표기
3. 검색 결과에 없는 내용은 절대 지어내지 말 것
4. 답변 끝에 "더 자세한 내용은 관련 기관에 확인하세요" 한 줄 추가
5. 구체적 절차·연락처가 검색 결과에 있으면 포함
"""


# 프리셋 질문 (UI 에서 선택할 수 있게)
PRESET_QUESTIONS = [
    "전입신고는 언제까지 해야 해요?",
    "확정일자는 어디서 받아요?",
    "보증금 반환 못 받으면 뭘 해야 해요?",
    "전세사기 피하려면 뭘 확인해야 해요?",
    "반려동물 주소변경은 어떻게 해요?",
    "장기수선충당금 돌려받을 수 있어요?",
    "이사 비용 줄이는 꿀팁 알려주세요",
    "원상회복 범위는 어디까지예요?",
]


def _extract_query_keywords(question: str) -> list[str]:
    """질문에서 검색 쿼리로 사용할 구문 추출."""
    # 조사·어미 제거 후 2글자 이상 한글/영문
    import re

    tokens = re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", question)
    # 의미 없는 한글 토큰 제거
    stop = {
        "언제", "어디", "어떻게", "뭐", "무엇", "왜", "까지", "에서", "합니까",
        "해야", "하나요", "있어요", "이에요", "인가요", "이나요", "되나요",
        "알려", "주세요", "그게", "이게", "저게", "그런", "이런", "그거",
    }
    return [t for t in tokens if t not in stop][:10]


def _build_fallback_answer(
    question: str, law_hits: list[dict], proc_hits: list[dict], yt_hits: list[dict]
) -> str:
    """키워드 검색 결과만으로 간단한 답변 생성."""
    parts = []
    if proc_hits:
        # 가장 점수 높은 절차 청크의 내용 요약
        top = proc_hits[0]
        content = clean_hanja((top.get("content") or "")[:300])
        parts.append(content)
    if law_hits:
        top_law = law_hits[0]
        law_ref = f"{top_law.get('law_name', '')} {top_law.get('article', '')}"
        parts.append(f"(관련 법률: {law_ref})")
    if not parts:
        return (
            "질문에 대한 정확한 정보를 찾지 못했습니다. "
            "'전입신고', '확정일자', '보증금 반환' 같은 키워드로 다시 물어봐 주세요. "
            "또는 대한법률구조공단 132 에 무료 상담을 받으실 수 있습니다."
        )
    answer = " ".join(parts)
    answer += "\n\n더 자세한 내용은 관련 기관에 확인하세요."
    return answer


def _build_citations(
    law_hits: list[dict], proc_hits: list[dict], yt_hits: list[dict]
) -> list[ChatCitation]:
    cits: list[ChatCitation] = []
    for h in law_hits[:3]:
        cits.append(
            ChatCitation(
                source_type="law",
                title=f"{h.get('law_name', '')} {h.get('article', '')}",
                content_snippet=clean_hanja((h.get("content") or "")[:200]),
                url=h.get("source_url"),
                meta={"article_title": h.get("title", "")},
            )
        )
    for h in proc_hits[:3]:
        cits.append(
            ChatCitation(
                source_type="procedure",
                title=clean_hanja(h.get("doc_title") or h.get("breadcrumb") or "행정 절차"),
                content_snippet=clean_hanja((h.get("content") or "")[:200]),
                url=h.get("source_url"),
            )
        )
    for h in yt_hits[:3]:
        cits.append(
            ChatCitation(
                source_type="youtube",
                title=f"{h.get('channel', '')}: {h.get('video_title', '')}",
                content_snippet=clean_hanja((h.get("content") or "")[:200]),
                url=h.get("deep_link") or h.get("source_url"),
                meta={"timecode": h.get("timecode", "")},
            )
        )
    return cits


def generate_chat_reply(question: str) -> ChatReply:
    """챗봇 응답 생성. Azure 있으면 LLM, 없으면 키워드 답변."""
    keywords = _extract_query_keywords(question)
    if not keywords:
        return ChatReply(
            answer="질문이 너무 짧거나 의미를 파악할 수 없습니다. 좀 더 구체적으로 물어봐 주세요.",
            mode="fallback",
            used_queries=[],
        )

    # 세 인덱스 모두 검색
    query_joined = " ".join(keywords)
    law_hits = search_laws([query_joined], top_k_per_query=3)
    proc_hits = search_procedures([query_joined], top_k_per_query=3)
    yt_hits = search_youtube([query_joined], top_k_per_query=3)

    citations = _build_citations(law_hits, proc_hits, yt_hits)

    client = get_openai_client()
    if client is None:
        # Fallback 모드
        answer = _build_fallback_answer(question, law_hits, proc_hits, yt_hits)
        return ChatReply(
            answer=answer,
            mode="fallback",
            citations=citations,
            used_queries=[query_joined],
        )

    # Azure 모드 — LLM 에 컨텍스트 전달
    settings = get_settings()
    context_parts = []
    for h in law_hits[:5]:
        context_parts.append(
            f"[법률] {h.get('law_name')} {h.get('article')}: "
            f"{clean_hanja((h.get('content') or '')[:400])}"
        )
    for h in proc_hits[:5]:
        context_parts.append(
            f"[절차] {clean_hanja(h.get('doc_title') or '')}: "
            f"{clean_hanja((h.get('content') or '')[:400])}"
        )
    for h in yt_hits[:3]:
        context_parts.append(
            f"[유튜브] {h.get('channel')} - {h.get('video_title')}: "
            f"{clean_hanja((h.get('content') or '')[:300])}"
        )
    context = "\n\n".join(context_parts)

    try:
        resp = client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=0.3,
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"질문: {question}\n\n검색 결과:\n{context}",
                },
            ],
            timeout=30,
        )
        answer = (resp.choices[0].message.content or "").strip()
        if not answer:
            answer = _build_fallback_answer(question, law_hits, proc_hits, yt_hits)
        return ChatReply(
            answer=answer,
            mode="azure",
            citations=citations,
            used_queries=[query_joined],
        )
    except Exception as exc:
        logger.warning(f"chat LLM failed ({type(exc).__name__}): {exc} — fallback")
        return ChatReply(
            answer=_build_fallback_answer(question, law_hits, proc_hits, yt_hits),
            mode="fallback",
            citations=citations,
            used_queries=[query_joined],
        )


def get_preset_questions() -> list[str]:
    return PRESET_QUESTIONS
