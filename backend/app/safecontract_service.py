"""POST /safecontract business logic — 등기부등본 해석."""
from __future__ import annotations

import json
import re
from typing import Optional

from .azure_clients import get_docintel_client, get_openai_client, get_search_client_law
from .config import get_settings
from .local_search import clean_hanja, find_law_article
from .models import (
    ChecklistCitation,
    MarketEstimate,
    RegistryExtraction,
    RiskItem,
    SafeContractRequest,
    SafeContractResponse,
    ServiceReferral,
)
from .realty_price import get_region_price_summary


# ---------- PDF / 이미지 → 텍스트 (Azure Document Intelligence) ----------


class DocumentIntelligenceNotConfigured(RuntimeError):
    """AZURE_DOCINTEL_* 환경변수 미설정 시 발생."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Azure Document Intelligence 의 `prebuilt-layout` 모델로 PDF → 텍스트 변환.

    등기부등본은 갑구/을구가 표 구조라 layout 모델이 가장 적합.
    테이블 셀도 content 에 순서대로 포함되므로 평문으로 반환.

    Raises:
        DocumentIntelligenceNotConfigured: Azure 키 미설정 시
    """
    client = get_docintel_client()
    if client is None:
        raise DocumentIntelligenceNotConfigured(
            "Azure Document Intelligence 가 설정되지 않았습니다. "
            ".env 의 AZURE_DOCINTEL_ENDPOINT 와 AZURE_DOCINTEL_API_KEY 를 입력하세요."
        )

    # SDK v1.0 은 analyze_document 에 AnalyzeDocumentRequest(bytes_source=...) 전달
    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

    poller = client.begin_analyze_document(
        "prebuilt-layout",
        AnalyzeDocumentRequest(bytes_source=file_bytes),
    )
    result = poller.result()

    # 페이지 순서대로 line/content 합침
    parts: list[str] = []
    if getattr(result, "content", None):
        parts.append(result.content)
    # fallback: 페이지별 라인 직접 수집
    elif getattr(result, "pages", None):
        for page in result.pages:
            for line in page.lines or []:
                parts.append(line.content)

    text = "\n".join(parts).strip()
    return clean_hanja(text)  # 한자 병기 제거


def analyze_safecontract_pdf(
    file_bytes: bytes, deposit_krw: int, expected_market_price_krw: int
) -> SafeContractResponse:
    """PDF 업로드 → Document Intelligence → 기존 분석 파이프라인.

    기획서 3.5.2 P1 목표 — Azure Document Intelligence 연결 시 활성화.
    """
    text = extract_text_from_pdf(file_bytes)
    if not text:
        raise ValueError("PDF 에서 텍스트를 추출하지 못했습니다. 스캔 품질을 확인하세요.")
    req = SafeContractRequest(
        text=text,
        deposit_krw=deposit_krw,
        expected_market_price_krw=expected_market_price_krw,
    )
    return analyze_safecontract(req)


def _cite(law_name: str, article: str) -> ChecklistCitation:
    """법령·조문 → 원문 자동 첨부된 Citation. 한자는 로드 시점에 이미 제거됨."""
    base = ChecklistCitation(law_name=law_name, article=article)
    found = find_law_article(law_name, article)
    if not found:
        return base
    content = (found.get("content") or "").strip()
    title = (found.get("title") or "").strip()
    if content:
        base.article_text = content[:500] + ("…" if len(content) > 500 else "")
    if title:
        base.article_title = title
    if found.get("source_url"):
        base.source_url = found["source_url"]
    return base

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
                "집이 경매에 넘어가면 보증금을 돌려받지 못할 위험이 있습니다. "
                "주택임대차보호법의 우선변제권으로도 보증금 전액을 돌려받지 못할 수 있어요."
            ),
            related_laws=[
                _cite("주택임대차보호법", "제3조의2"),
                _cite("주택임대차보호법", "제8조"),
            ],
        ))
        summary_parts.append("🔴 깡통전세 위험")
    elif ratio >= 0.8:
        risks.append(RiskItem(
            severity="yellow",
            label=f"부채비율 {ratio * 100:.0f}%",
            explanation_plain=(
                "안전 범위를 약간 벗어났습니다. HUG 보증보험 가입 여부를 확인해보세요. "
                "전입신고+확정일자로 대항력·우선변제권을 확보해두는 것이 필수입니다."
            ),
            related_laws=[_cite("주택임대차보호법", "제3조의2")],
        ))
        summary_parts.append("🟡 부채비율 주의")
    else:
        summary_parts.append("🟢 부채비율은 안전 범위")
        risks.append(RiskItem(
            severity="green",
            label=f"부채비율 {ratio * 100:.0f}%",
            explanation_plain=(
                "부채비율은 안전 범위입니다. 그래도 전입신고+확정일자로 "
                "대항력을 확보해두세요."
            ),
            related_laws=[_cite("주택임대차보호법", "제3조의2")],
        ))

    if extraction.seizure_count > 0:
        risks.append(RiskItem(
            severity="red",
            label=f"가압류 {extraction.seizure_count}건",
            explanation_plain=(
                "가압류는 채권자가 집주인 재산을 묶어둔 것. "
                "집주인에게 돈 문제가 있다는 신호이며, 계약 시 보증금 회수가 어려울 수 있습니다."
            ),
            related_laws=[_cite("주택임대차보호법", "제3조의3")],
        ))
    if extraction.trust_registration:
        risks.append(RiskItem(
            severity="red",
            label="신탁등기 존재",
            explanation_plain=(
                "신탁등기된 주택은 실제 소유권이 신탁회사에 있어, "
                "집주인과 계약해도 신탁회사의 동의가 없으면 대항력이 없습니다. "
                "계약 주체 확인이 필수입니다."
            ),
        ))
    if extraction.auction_in_progress:
        risks.append(RiskItem(
            severity="red",
            label="임의경매 진행 중",
            explanation_plain=(
                "이 주택은 경매가 개시되었습니다. 계약하면 안 됩니다. "
                "이미 경매 중인 부동산은 낙찰 후 소유권이 바뀌므로 임차인 권리 주장이 매우 어렵습니다."
            ),
            related_laws=[_cite("주택임대차보호법", "제3조의5")],
        ))

    # 기본 안내: 임차권등기명령은 계약 후 반환 문제 대비
    risks.append(RiskItem(
        severity="green",
        label="임차권등기명령 안내",
        explanation_plain=(
            "만약 계약 종료 후 보증금을 돌려받지 못하는 경우, "
            "임차권등기명령을 신청하여 대항력·우선변제권을 유지할 수 있습니다."
        ),
        related_laws=[_cite("주택임대차보호법", "제3조의3")],
    ))

    summary = " · ".join(summary_parts) or "분석 완료"
    return summary, risks


def _build_referrals() -> list[ServiceReferral]:
    """확장된 referrals — 기획서 3.5.5 기반 12개."""
    return [
        ServiceReferral(
            icon="🏛",
            name="HUG 안심전세 앱",
            url="https://www.khug.or.kr",
            description="보증보험 가입 가능 여부 + 깡통전세 자동 진단",
        ),
        ServiceReferral(
            icon="⚠",
            name="HUG 보증금 미반환 임대인 조회",
            url="https://www.khug.or.kr/hug/web/ig/dg/igdg000001.jsp",
            description="상습 미반환 임대인 공개 DB (본인 인증 필요)",
        ),
        ServiceReferral(
            icon="📋",
            name="대법원 인터넷등기소",
            url="https://www.iros.go.kr",
            description="등기부등본 원본 발급 (700원~1,000원)",
        ),
        ServiceReferral(
            icon="💰",
            name="국토교통부 실거래가",
            url="https://rt.molit.go.kr",
            description="주변 시세 비교 (매매·전월세)",
        ),
        ServiceReferral(
            icon="⚖",
            name="주택임대차분쟁조정위원회",
            url="https://www.hldcc.or.kr",
            description="보증금 반환 분쟁 조정 (60일 내 해결, 수천원~5만원)",
        ),
        ServiceReferral(
            icon="🆘",
            name="전세피해지원센터 1533-8119",
            url="https://jeonse119.molit.go.kr",
            description="국토부 산하 전세사기 피해자 종합 지원 (무료)",
        ),
        ServiceReferral(
            icon="📞",
            name="대한법률구조공단 132",
            url="https://www.klac.or.kr",
            description="무료 법률 상담 (임대차 분쟁 1순위)",
        ),
        ServiceReferral(
            icon="📄",
            name="법무부 표준임대차계약서",
            url="https://www.moj.go.kr/moj/215/subview.do",
            description="법적 분쟁 시 임차인 보호에 유리한 공식 양식",
        ),
    ]


def _fetch_market_estimate(region: Optional[str]) -> Optional[MarketEstimate]:
    """사용자 지역으로 실거래가 API 자동 조회."""
    if not region:
        return None
    try:
        s = get_region_price_summary(region)
    except Exception as exc:
        return MarketEstimate(
            source="국토교통부 아파트 매매 실거래가 API",
            region=region,
            query_ym="",
            error=f"조회 실패: {exc}",
        )
    return MarketEstimate(
        source="국토교통부 아파트 매매 실거래가 API (공공데이터포털)",
        region=s.region,
        lawd_cd=s.lawd_cd,
        query_ym=s.query_ym,
        total_count=s.total_count,
        median_price_krw=s.median_price_krw,
        min_price_krw=s.min_price_krw,
        max_price_krw=s.max_price_krw,
        recent_deals=[
            {
                "apt_name": d.apt_name,
                "deal_amount_krw": d.deal_amount_krw,
                "deal_date": f"{d.deal_year}-{d.deal_month:02d}-{d.deal_day:02d}",
                "area_m2": d.area_m2,
                "floor": d.floor,
                "dong": d.dong,
            }
            for d in s.recent_deals[:5]
        ],
        error=s.error,
    )


def analyze_safecontract(req: SafeContractRequest) -> SafeContractResponse:
    if not req.text:
        raise ValueError("text is required (PDF 업로드는 /safecontract/upload 참고)")

    extraction = _extract_with_llm(req.text)

    # region 주어지고 expected_market_price_krw 가 0 또는 없으면 실거래가로 자동 추정
    market = _fetch_market_estimate(req.region)
    effective_market_price = req.expected_market_price_krw
    if effective_market_price <= 0 and market and market.median_price_krw:
        effective_market_price = market.median_price_krw

    ratio = _compute_jeontse_ratio(extraction, req.deposit_krw, effective_market_price)
    law_hits = _search_law_context(extraction)
    summary, risks = _explain_with_llm(extraction, ratio, law_hits)

    return SafeContractResponse(
        extraction=extraction,
        jeontse_ratio=ratio,
        summary=summary,
        risks=risks,
        referrals=_build_referrals(),
        disclaimer=(
            "이 서비스는 법률 자문이 아닌 참고용 사전 검토 도구입니다. "
            "정확한 판단을 위해 전문가 상담을 권합니다."
        ),
        market_estimate=market,
    )
