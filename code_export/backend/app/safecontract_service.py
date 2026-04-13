"""POST /safecontract business logic — 등기부등본 해석."""
from __future__ import annotations

import json
import re

from .azure_clients import get_openai_client, get_search_client_law
from .config import get_settings
from .models import (
    ChecklistCitation,
    RegistryExtraction,
    RiskItem,
    SafeContractRequest,
    SafeContractResponse,
    ServiceReferral,
)

EXTRACT_SYSTEM = """당신은 한국 부동산 등기부등본 분석 도우미입니다.
사용자가 붙여넣은 등기부등본 텍스트(갑구/을구)를 읽고 다음 JSON 스키마로 추출하세요.

{
  "owner_change_within_2_years": int,     // 최근 2년 내 소유자 변동 횟수
  "mortgage_total_krw": int,               // 근저당 전체 금액(원)
  "mortgage_claim_amount_krw": int,        // 채권최고액 총합(원)
  "seizure_count": int,                    // 가압류/압류 건수
  "seizure_total_krw": int,                // 가압류 총액(원)
  "trust_registration": bool,              // 신탁등기 존재 여부
  "auction_in_progress": bool,             // 임의경매개시결정 존재 여부
  "raw_notes": [str]                       // 기타 주목할 만한 사항 (1~5건)
}

찾지 못한 값은 0 또는 false로. 본문에 없는 정보를 지어내지 말 것."""

EXPLAIN_SYSTEM = """당신은 부동산 등기부등본 해석 도우미입니다.
추출된 수치와 주택임대차보호법 검색 결과를 바탕으로:
1. 각 위험 항목별로 쉬운 말로 설명 (explanation_plain)
2. severity는 green/yellow/red 중 하나
3. 관련 법 조항 citations 첨부 (검색 결과에 있는 것만)
출력은 JSON: {"summary": "...", "risks": [{...}]}"""


def _extract_with_llm(text: str) -> RegistryExtraction:
    client = get_openai_client()
    if client is None:
        return _extract_rule_based(text)
    settings = get_settings()
    resp = client.chat.completions.create(
        model=settings.azure_openai_deployment_name,
        temperature=0,
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return RegistryExtraction(**json.loads(raw))
    except Exception:
        return _extract_rule_based(text)


def _extract_rule_based(text: str) -> RegistryExtraction:
    """Very rough fallback — development only."""
    mortgage = 0
    claim = 0
    seizure = 0
    seizure_total = 0
    for m in re.finditer(r"근저당권\s*설정[^\n]*?금\s*([\d,억만원\s]+)", text):
        raw = re.sub(r"[^\d억만]", "", m.group(1))
        claim += _parse_korean_amount(raw)
    for _ in re.finditer(r"가압류", text):
        seizure += 1
    trust = "신탁" in text
    auction = "임의경매" in text or "경매개시결정" in text
    return RegistryExtraction(
        mortgage_total_krw=int(claim * 0.83),  # 채권최고액의 약 83%를 실 부채로 추정
        mortgage_claim_amount_krw=claim,
        seizure_count=seizure,
        seizure_total_krw=seizure_total,
        trust_registration=trust,
        auction_in_progress=auction,
    )


def _parse_korean_amount(s: str) -> int:
    """'2억4천만' → 240000000 대략 파싱."""
    eok = 0
    if "억" in s:
        head, s = s.split("억", 1)
        eok = int(re.sub(r"\D", "", head) or 0)
    cheon = 0
    if "천" in s:
        head, s = s.split("천", 1)
        cheon = int(re.sub(r"\D", "", head) or 0) * 1000
    man = int(re.sub(r"\D", "", s) or 0)
    return eok * 100_000_000 + (cheon + man) * 10_000


def _search_law_context(extraction: RegistryExtraction) -> list[dict]:
    client = get_search_client_law()
    if client is None:
        return []
    queries = []
    if extraction.mortgage_total_krw > 0:
        queries.append("근저당 대항력 우선변제")
    if extraction.seizure_count > 0:
        queries.append("가압류 임차권")
    if extraction.trust_registration:
        queries.append("신탁등기 임차인")
    if extraction.auction_in_progress:
        queries.append("임의경매 배당 순위")

    hits = []
    for q in queries:
        for h in client.search(search_text=q, top=2):
            hits.append(dict(h))
    return hits


def _compute_jeontse_ratio(extraction: RegistryExtraction, deposit: int, market: int) -> float:
    if market <= 0:
        return 0.0
    return round((extraction.mortgage_total_krw + deposit) / market, 3)


def _explain_with_llm(
    extraction: RegistryExtraction,
    ratio: float,
    law_hits: list[dict],
) -> tuple[str, list[RiskItem]]:
    client = get_openai_client()
    if client is None:
        return _explain_rule_based(extraction, ratio)

    settings = get_settings()
    context = "\n---\n".join(
        f"[{h.get('law_name')} {h.get('article')}] {h.get('content','')[:400]}"
        for h in law_hits
    )
    payload = {
        "extraction": extraction.model_dump(),
        "jeontse_ratio": ratio,
        "law_context": context,
    }
    resp = client.chat.completions.create(
        model=settings.azure_openai_deployment_name,
        temperature=0,
        messages=[
            {"role": "system", "content": EXPLAIN_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
        summary = data.get("summary", "")
        risks = [RiskItem(**r) for r in data.get("risks", [])]
        return summary, risks
    except Exception:
        return _explain_rule_based(extraction, ratio)


def _explain_rule_based(extraction: RegistryExtraction, ratio: float) -> tuple[str, list[RiskItem]]:
    risks: list[RiskItem] = []
    summary_parts = []

    if ratio >= 1.0:
        risks.append(RiskItem(
            severity="red",
            label=f"깡통전세 비율 {ratio * 100:.0f}%",
            explanation_plain=(
                "근저당과 보증금의 합이 시세를 넘습니다. "
                "집이 경매에 넘어가면 보증금을 돌려받지 못할 위험이 있습니다."
            ),
            related_laws=[ChecklistCitation(law_name="주택임대차보호법", article="제3조의2")],
        ))
        summary_parts.append("🔴 깡통전세 위험")
    elif ratio >= 0.8:
        risks.append(RiskItem(
            severity="yellow",
            label=f"부채비율 {ratio * 100:.0f}%",
            explanation_plain="안전 범위를 약간 벗어났습니다. HUG 보증보험 가입 여부를 확인해보세요.",
        ))
        summary_parts.append("🟡 부채비율 주의")
    else:
        summary_parts.append("🟢 부채비율은 안전 범위")

    if extraction.seizure_count > 0:
        risks.append(RiskItem(
            severity="red",
            label=f"가압류 {extraction.seizure_count}건",
            explanation_plain="가압류는 채권자가 집주인 재산을 묶어둔 것. 집주인에게 돈 문제가 있다는 신호입니다.",
        ))
    if extraction.trust_registration:
        risks.append(RiskItem(
            severity="red",
            label="신탁등기 존재",
            explanation_plain="신탁등기된 주택은 실제 소유권이 신탁회사에 있어 계약 주체 확인이 필수입니다.",
        ))
    if extraction.auction_in_progress:
        risks.append(RiskItem(
            severity="red",
            label="임의경매 진행 중",
            explanation_plain="이 주택은 경매가 개시되었습니다. 계약하면 안 됩니다.",
        ))

    summary = " · ".join(summary_parts) or "분석 완료"
    return summary, risks


def analyze_safecontract(req: SafeContractRequest) -> SafeContractResponse:
    if not req.text:
        raise ValueError("text is required (PDF 업로드는 /safecontract/upload 참고)")

    extraction = _extract_with_llm(req.text)
    ratio = _compute_jeontse_ratio(extraction, req.deposit_krw, req.expected_market_price_krw)
    law_hits = _search_law_context(extraction)
    summary, risks = _explain_with_llm(extraction, ratio, law_hits)

    referrals = [
        ServiceReferral(
            icon="🏛️",
            name="HUG 안심전세 앱",
            url="https://www.khug.or.kr",
            description="보증보험 가입 가능 여부 확인",
        ),
        ServiceReferral(
            icon="📋",
            name="인터넷등기소",
            url="https://www.iros.go.kr",
            description="등기부등본 원본 직접 열람 (700원)",
        ),
        ServiceReferral(
            icon="💰",
            name="국토교통부 실거래가",
            url="https://rt.molit.go.kr",
            description="주변 시세 비교",
        ),
    ]

    return SafeContractResponse(
        extraction=extraction,
        jeontse_ratio=ratio,
        summary=summary,
        risks=risks,
        referrals=referrals,
        disclaimer=(
            "이 서비스는 법률 자문이 아닌 참고용 사전 검토 도구입니다. "
            "정확한 판단을 위해 전문가 상담을 권합니다."
        ),
    )
