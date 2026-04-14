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


# ---------- 입력 필터 ----------


GREETING_WORDS = {
    "안녕", "안녕하세요", "안녕하십니까", "하이", "헬로", "반가워", "반갑",
    "hi", "hello", "hey", "ㅎㅇ",
}

THANKS_WORDS = {"고마워", "감사", "ㄱㅅ", "thanks", "thank you"}

# 이사·전월세 도메인 키워드 — 이 중 하나라도 포함돼야 RAG 검색 수행
DOMAIN_KEYWORDS = [
    # 이사 일반
    "이사", "포장이사", "짐", "이삿짐", "이사업체", "이사비", "사다리차",
    # 계약 유형
    "전세", "월세", "자가", "임대", "임차", "계약",
    # 주소·신고
    "전입", "전출", "주소", "주민", "주민등록", "등본", "초본",
    # 권리 보호
    "확정일자", "대항력", "우선변제", "임차권", "등기명령", "보증금",
    "갱신", "해지", "통지", "계약서", "특약",
    # 전세사기
    "전세사기", "깡통", "근저당", "가압류", "경매", "신탁", "등기부",
    "안심전세", "HUG", "hug", "원상회복",
    # 공과금
    "공과금", "가스", "수도", "전기", "인터넷", "TV", "명의변경", "명의변환",
    "관리비", "충당금", "예치금", "장기수선",
    # 행정
    "정부24", "주민센터", "확정", "전학", "교육청", "반려동물", "애완", "동물",
    "자동차", "차량", "외국인", "하이코리아", "출입국",
    # 퇴거
    "퇴거", "퇴실", "계량기", "점검", "점검표", "폐기물", "폐기",
    # 금융·지원
    "대출", "디딤돌", "버팀목", "월세지원", "청년", "신혼",
    # 분쟁
    "분쟁", "조정", "소송", "법률", "변호사", "하자", "수선",
    # 기본 질문 어휘
    "언제", "어떻게", "어디", "방법", "절차", "기한", "과태료",
]


def _is_greeting(question: str) -> bool:
    q = question.strip().lower().replace(" ", "")
    if len(q) > 15:
        return False
    return any(g in q for g in GREETING_WORDS)


def _is_thanks(question: str) -> bool:
    q = question.strip().lower().replace(" ", "")
    if len(q) > 15:
        return False
    return any(t in q for t in THANKS_WORDS)


def _is_in_domain(question: str) -> bool:
    """질문이 이사·전월세 도메인에 속하는지 간단 판정."""
    q = question.lower()
    return any(kw.lower() in q for kw in DOMAIN_KEYWORDS)


_NAV_NOISE_PATTERNS = [
    "현재위치 및 공유하기",
    "생활법령 내 검색",
    "페이스북",
    "트위터",
    "카카오톡",
    "전체 PDF 저장",
    "전체 EPUB 저장",
    "현재 페이지 PDF 저장",
    "본문 영역",
    "즐겨찾기",
    "인쇄체크",
]


def _clean_noise(text: str) -> str:
    """easylaw 스크랩에 섞인 네비게이션/메뉴 잔여 제거."""
    import re

    out = text
    for pat in _NAV_NOISE_PATTERNS:
        out = out.replace(pat, "")
    # 단독 줄(한두 단어)로 된 메뉴 아이템 제거
    lines = [ln.strip() for ln in out.splitlines()]
    meaningful = [
        ln for ln in lines
        if ln and not (len(ln) <= 5 and not any(c.isdigit() for c in ln))
    ]
    cleaned = "\n".join(meaningful)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _build_fallback_answer(
    question: str, law_hits: list[dict], proc_hits: list[dict], yt_hits: list[dict]
) -> str:
    """키워드 검색 결과만으로 간단한 답변 생성."""
    parts = []
    if law_hits:
        # 법률이 있으면 조문 내용을 우선 (가장 신뢰도 높음)
        top_law = law_hits[0]
        content = clean_hanja((top_law.get("content") or "")[:400])
        content = _clean_noise(content)
        law_ref = f"{top_law.get('law_name', '')} {top_law.get('article', '')}"
        parts.append(f"[{law_ref}]\n{content}")
    elif proc_hits:
        # 법률 없으면 절차 청크 (네비게이션 제거)
        top = proc_hits[0]
        content = clean_hanja((top.get("content") or "")[:400])
        content = _clean_noise(content)
        if content:
            parts.append(content)
    if not parts:
        return (
            "질문에 대한 정확한 정보를 찾지 못했습니다. "
            "'전입신고', '확정일자', '보증금 반환' 같은 키워드로 다시 물어봐 주세요. "
            "또는 대한법률구조공단 132 에 무료 상담을 받으실 수 있습니다."
        )
    answer = "\n\n".join(parts)
    answer += "\n\n더 자세한 내용은 아래 출처를 확인하세요."
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
    # 1. 인사말
    if _is_greeting(question):
        return ChatReply(
            answer=(
                "안녕하세요! 저는 이사·전월세 전문 챗봇 꽉꽉봇이에요. 🐤\n\n"
                "아래 같은 질문에 답할 수 있어요:\n"
                "• 전입신고는 언제까지 해야 해요?\n"
                "• 확정일자는 어디서 받아요?\n"
                "• 보증금 반환 못 받으면 어떻게 해요?\n"
                "• 전세사기 피하려면 뭘 확인해야 해요?\n\n"
                "궁금한 점을 구체적으로 물어봐 주세요."
            ),
            mode="fallback",
            citations=[],
            used_queries=[],
        )

    # 2. 감사 인사
    if _is_thanks(question):
        return ChatReply(
            answer="천만에요! 이사·전월세 관련해서 또 궁금한 점 있으면 언제든 물어봐 주세요. 🐤",
            mode="fallback",
            citations=[],
            used_queries=[],
        )

    # 3. 도메인 외 질문
    if not _is_in_domain(question):
        return ChatReply(
            answer=(
                "저는 이사·전월세 관련 질문만 답변할 수 있어요. 🐤\n\n"
                "예를 들어 이런 질문을 해보세요:\n"
                "• 전입신고·확정일자·대항력\n"
                "• 보증금 반환·임차권등기명령\n"
                "• 전세사기 예방·등기부등본 확인\n"
                "• 공과금 명의변경·관리비 정산\n"
                "• 계약 해지·원상회복·장기수선충당금"
            ),
            mode="fallback",
            citations=[],
            used_queries=[],
        )

    # 4. 키워드 추출
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
            timeout=15,
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
