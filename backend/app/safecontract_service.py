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


def _parse_region_from_address(address: Optional[str]) -> Optional[str]:
    """추출된 주소 문자열에서 '시/도 + 시/군/구' 부분 추출.

    PDF layout 의 raw text(헤더·표 메타가 앞에 있음)에도 적용 가능하도록
    re.search 사용. 첫 매칭 우선.

    예: '...등기사항전부증명서...서울특별시 강남구 역삼동 123-45 ...'
        → '서울특별시 강남구'
    """
    if not address:
        return None
    text = re.sub(r"\s+", " ", address).strip()
    # 시/도 + 시/군/구 패턴 — 광역시·특별시·도, 자치도 포함
    m = re.search(
        r"(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|"
        r"세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충청남도|"
        r"전북특별자치도|전라북도|전라남도|경상북도|경상남도|제주특별자치도)"
        r"\s+([가-힣]+시\s+[가-힣]+구|[가-힣]+구|[가-힣]+시|[가-힣]+군)",
        text,
    )
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return None


def analyze_safecontract_pdf(
    file_bytes: bytes,
    deposit_krw: int,
    expected_market_price_krw: int,
    region: Optional[str] = None,
) -> SafeContractResponse:
    """PDF 업로드 → Document Intelligence → 기존 분석 파이프라인.

    기획서 3.5.2 P1 목표 — Azure Document Intelligence 연결 시 활성화.

    region 이 None 이면 추출된 주소에서 자동 파싱 (사용자가 시세 몰라도 자동 조회).
    """
    text = extract_text_from_pdf(file_bytes)
    if not text:
        raise ValueError("PDF 에서 텍스트를 추출하지 못했습니다. 스캔 품질을 확인하세요.")

    # region 자동 유도: (1) 사용자 명시 > (2) 레이아웃 텍스트에서 직접 정규식 파싱
    # LLM 두 번 호출 피하려고 raw text 에서 먼저 시/도+시군구 패턴 찾음
    effective_region = region or _parse_region_from_address(text)

    req = SafeContractRequest(
        text=text,
        deposit_krw=deposit_krw,
        expected_market_price_krw=expected_market_price_krw,
        region=effective_region,
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

EXTRACT_SYSTEM = """당신은 한국 부동산 등기사항전부증명서(등기부등본) 파싱 전문가입니다.
주어진 등기부등본 텍스트(표제부·갑구·을구·주요 등기사항 요약)를 읽고 지정된 JSON 스키마로 추출하세요.

**부동산 식별 정보 (사용자 표시용)**
- property_id: "고유번호" 옆의 값 (예: 1102-2015-003456)
- address: 표제부 "소재지번, 건물명칭 및 번호" 칸의 주소 전체 — 시·도·구·동·번지·건물명·호수를 한 줄로 연결
- area_m2: 표제부 "건물 내역" 칸의 면적 숫자 (m² 제외)
- building_use: 표제부 "건물 내역" 칸의 "용도" 값 (예: "아파트", "다세대주택", "단독주택", "오피스텔")
- owner_name: 갑구 최신 소유권 레코드 또는 "주요 등기사항 요약 - 소유지분현황" 의 등기명의인 (첫 번째)
- owner_registration_front: 등기명의인 주민등록번호 앞 6자리 (예: "800101"). 뒷자리 "1******" 은 제외. 없으면 null
- co_owner_name: 공유 소유자 2명 이상일 때 두 번째 등기명의인 (단독소유면 null)
- ownership_type: "주요 등기사항 요약" 의 "최종지분" 칸 값 ("단독소유" / "공유 1/2" 등)
- mortgage_creditor: 을구 근저당권자. 다건이면 ", " 로 연결. 없으면 null
- seizure_text: 갑구에 가압류 기재 있으면 채권자·금액 한 줄 요약 (예: "○○은행 3천만원"), 없으면 null
- special_note: 특이사항 한 줄 요약. 신탁등기·임의경매·가압류·소유권 이전 이력 복잡 등 주목할 점. 복수면 ", " 로 연결. 해당 없으면 null. (예: "임의경매 진행 중, 가압류 1건")

**위험 분석 수치**
- owner_change_within_2_years: 갑구에서 최근 2년 내 "소유권이전" 건수
- mortgage_total_krw: 근저당 실 부채 추정 = 채권최고액 × 0.83 (다건이면 합계)
- mortgage_claim_amount_krw: 채권최고액 합계 (원)
- seizure_count: 가압류·압류 레코드 개수
- seizure_total_krw: 가압류 청구금액 합계
- trust_registration: "신탁" 등기목적 존재 여부
- auction_in_progress: "임의경매개시결정" 등기 존재 여부
- raw_notes: 기타 특이사항 1~5건 (각 문장 완결)

**규칙**
- 찾지 못한 수치는 0, boolean 은 false, 문자열/숫자 필드는 null
- 본문에 없는 정보는 절대 지어내지 말 것 (특히 주소·소유자 이름)
- 금액은 정수(원 단위)로 변환: "3억" → 300000000, "1억 8천만" → 180000000"""

EXPLAIN_SYSTEM = """당신은 부동산 등기부등본 해석 도우미입니다.
추출된 수치와 주택임대차보호법 검색 결과를 바탕으로:
1. 각 위험 항목별로 쉬운 말로 설명 (explanation_plain)
2. severity는 green/yellow/red 중 하나
3. 관련 법 조항 citations 첨부 (검색 결과에 있는 것만)

**summary 작성 절대 규칙 (매우 중요)**
- auction_in_progress=true 이면 summary 앞에 반드시 "🔴 경매 진행 중"
- trust_registration=true 이면 "🔴 신탁 등기"
- seizure_count > 0 이면 "🔴 가압류 N건"
- 위 셋 중 하나라도 있으면 전세가율이 낮아도 **절대 "안전 범위" 라고 쓰지 말 것**
- 치명 상태가 없고 전세가율 < 0.8 + 근저당비율 < 0.5 일 때만 "🟢 안전 범위" 가능

출력은 JSON: {"summary": "...", "risks": [{...}]}"""


def _extract_with_llm(text: str) -> RegistryExtraction:
    """GPT-4o + Structured Output (json_schema strict 모드) 로 등기부 파싱.

    스키마 100% 준수 보장 — 필드 누락/타입 오류 없이 RegistryExtraction 반환.
    실패 시 rule-based regex 폴백.
    """
    client = get_openai_client()
    if client is None:
        return _extract_rule_based(text)
    settings = get_settings()

    # json_schema strict 모드 — additionalProperties: false 필수
    schema = RegistryExtraction.model_json_schema()
    schema["additionalProperties"] = False
    # 모든 필드를 required 로 (strict 모드 요구사항, Optional 은 null 허용)
    if "properties" in schema:
        schema["required"] = list(schema["properties"].keys())

    try:
        resp = client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=0,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "RegistryExtraction",
                    "schema": schema,
                    "strict": True,
                },
            },
            timeout=20,
        )
        raw = resp.choices[0].message.content or "{}"
        return RegistryExtraction(**json.loads(raw))
    except Exception as exc:
        import logging
        logging.getLogger("movewise").warning(
            f"_extract_with_llm (json_schema) 실패: {type(exc).__name__}: {exc} — json_object 모드로 재시도"
        )
        # json_schema 미지원 시 json_object 로 폴백
        try:
            resp = client.chat.completions.create(
                model=settings.azure_openai_deployment_name,
                temperature=0,
                messages=[
                    {"role": "system", "content": EXTRACT_SYSTEM},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
                timeout=20,
            )
            raw = resp.choices[0].message.content or "{}"
            return RegistryExtraction(**json.loads(raw))
        except Exception:
            return _extract_rule_based(text)


def _extract_rule_based(text: str) -> RegistryExtraction:
    """Very rough fallback — development only."""
    claim = 0
    seizure = 0
    seizure_total = 0
    for m in re.finditer(r"근저당권\s*설정[^\n]*?금\s*([\d,억만천원\s]+)", text):
        raw = re.sub(r"[^\d억만천]", "", m.group(1))
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


def _compute_ratios(
    extraction: RegistryExtraction, deposit: int, market: int
) -> tuple[float, float, str]:
    """전세가율·근저당비율·위험도 계산.

    Returns:
        (jeontse_ratio, mortgage_ratio, risk_level)
        - jeontse_ratio: 보증금 / 시세 (정식 전세가율, 보통 <1.0)
        - mortgage_ratio: 근저당 실 추정액 / 시세
        - risk_level: "red" | "yellow" | "green"
          * 두 비율 합이 1.0 이상 → red (근저당+보증금 시세 초과)
          * 전세가율 단독으로 >= 0.8 → yellow (전세가율 경계)
          * 그 외 → green
    """
    if market <= 0:
        return 0.0, 0.0, "green"
    jeontse = round(deposit / market, 3)
    mortgage = round(extraction.mortgage_total_krw / market, 3)
    combined = jeontse + mortgage

    if combined >= 1.0 or extraction.seizure_count > 0 or extraction.trust_registration or extraction.auction_in_progress:
        level = "red"
    elif jeontse >= 0.8 or mortgage >= 0.5:
        level = "yellow"
    else:
        level = "green"
    return jeontse, mortgage, level


def _explain_with_llm(
    extraction: RegistryExtraction,
    jeontse_ratio: float,
    mortgage_ratio: float,
    law_hits: list[dict],
) -> tuple[str, list[RiskItem]]:
    client = get_openai_client()
    if client is None:
        return _explain_rule_based(extraction, jeontse_ratio, mortgage_ratio)

    settings = get_settings()
    context = "\n---\n".join(
        f"[{h.get('law_name')} {h.get('article')}] {h.get('content','')[:400]}"
        for h in law_hits
    )
    payload = {
        "extraction": extraction.model_dump(),
        "jeontse_ratio": jeontse_ratio,
        "mortgage_ratio": mortgage_ratio,
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
        return _explain_rule_based(extraction, jeontse_ratio, mortgage_ratio)


def _explain_rule_based(
    extraction: RegistryExtraction,
    jeontse_ratio: float,
    mortgage_ratio: float,
) -> tuple[str, list[RiskItem]]:
    risks: list[RiskItem] = []
    summary_parts = []

    jeontse_pct = min(int(round(jeontse_ratio * 100)), 999)
    mortgage_pct = min(int(round(mortgage_ratio * 100)), 999)
    combined = jeontse_ratio + mortgage_ratio

    # 0) 치명적 상태 먼저 체크 (경매·신탁·가압류) — 전세가율이 낮아도 RED
    critical_flags: list[str] = []
    if extraction.auction_in_progress:
        critical_flags.append("경매 진행 중")
    if extraction.trust_registration:
        critical_flags.append("신탁 등기")
    if extraction.seizure_count > 0:
        critical_flags.append(f"가압류 {extraction.seizure_count}건")

    # 1) 근저당+보증금이 시세를 초과 → RED (깡통전세)
    if combined >= 1.0:
        label = (
            "근저당이 시세를 초과" if mortgage_ratio >= 1.0
            else f"근저당+보증금이 시세 초과 (전세가율 {jeontse_pct}% · 근저당비율 {mortgage_pct}%)"
        )
        risks.append(RiskItem(
            severity="red",
            label=label,
            explanation_plain=(
                "근저당과 보증금의 합이 시세를 넘습니다. "
                "집이 경매에 넘어가면 낙찰가가 대출을 먼저 갚느라 보증금을 돌려받지 못할 위험이 있습니다. "
                "주택임대차보호법의 우선변제권으로도 보증금 전액을 돌려받지 못할 수 있어요."
            ),
            related_laws=[
                _cite("주택임대차보호법", "제3조의2"),
                _cite("주택임대차보호법", "제8조"),
            ],
        ))
        if critical_flags:
            summary_parts.append(f"🔴 {' · '.join(critical_flags)} · 깡통전세 위험 (전세가율 {jeontse_pct}%)")
        else:
            summary_parts.append(f"🔴 깡통전세 위험 · 전세가율 {jeontse_pct}%")
    elif critical_flags:
        # 전세가율은 낮아도 경매/신탁/가압류 있으면 무조건 RED
        summary_parts.append(f"🔴 {' · '.join(critical_flags)} · 계약 주의 (전세가율 {jeontse_pct}%)")
    elif jeontse_ratio >= 0.8 or mortgage_ratio >= 0.5:
        risks.append(RiskItem(
            severity="yellow",
            label=f"전세가율 {jeontse_pct}% · 근저당비율 {mortgage_pct}%",
            explanation_plain=(
                "안전 범위를 약간 벗어났습니다. HUG 보증보험 가입 여부를 확인해보세요. "
                "전입신고+확정일자로 대항력·우선변제권을 확보해두는 것이 필수입니다."
            ),
            related_laws=[_cite("주택임대차보호법", "제3조의2")],
        ))
        summary_parts.append(f"🟡 전세가율 {jeontse_pct}% 주의")
    else:
        summary_parts.append(f"🟢 전세가율 {jeontse_pct}% · 안전 범위")
        risks.append(RiskItem(
            severity="green",
            label=f"전세가율 {jeontse_pct}% · 근저당비율 {mortgage_pct}%",
            explanation_plain=(
                "전세가율과 근저당비율 모두 안전 범위입니다. 그래도 전입신고+확정일자로 "
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
            icon="🛡",
            name="SGI 서울보증보험 전세보증",
            url="https://www.sgic.co.kr",
            description="HUG 가입 거부 시 대안. 임대인 동의 불요",
        ),
        ServiceReferral(
            icon="⚠",
            name="HUG 보증금 미반환 임대인 조회",
            url="https://www.khug.or.kr/hug/web/ig/dg/igdg000001.jsp",
            description="상습 미반환 임대인 공개 DB (본인 인증 필요)",
        ),
        ServiceReferral(
            icon="🆔",
            name="주민등록증 진위확인 (ARS 1382)",
            url="https://www.gov.kr",
            description="계약 전 임대인 신분증 진위 · 등기부 소유자명 일치 체크",
        ),
        ServiceReferral(
            icon="📋",
            name="대법원 인터넷등기소",
            url="https://www.iros.go.kr",
            description="등기부등본 원본 발급 (700원~1,000원)",
        ),
        ServiceReferral(
            icon="🏗",
            name="정부24 건축물대장 발급",
            url="https://www.gov.kr/portal/rcvfvrSvc/dtlEx/13100000036",
            description="불법·위반 건축물 여부 확인 (무료, 보증보험 가입 전 필수)",
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

    # region 우선순위: (1) 사용자 명시 (2) LLM 이 추출한 address 에서 파싱 (3) raw text 파싱
    # LLM 이 address 를 정제해서 주니까 정규식 매칭 훨씬 안정적
    effective_region = (
        req.region
        or _parse_region_from_address(extraction.address)
        or _parse_region_from_address(req.text)
    )
    market = _fetch_market_estimate(effective_region)
    effective_market_price = req.expected_market_price_krw
    if effective_market_price <= 0 and market and market.median_price_krw:
        # 건물 용도별 시세 보정 — 국토부 API 는 아파트 기준
        # 다세대·빌라·단독주택은 같은 지역 아파트보다 저렴하므로 보정계수 적용
        # (실거래 통계 기반 경험치, 발표 후 연립·다세대 API 직접 호출로 개선 예정)
        use = (extraction.building_use or "").lower()
        if any(k in use for k in ("다세대", "빌라", "연립")):
            correction = 0.5  # 아파트 대비 50% 수준
        elif any(k in use for k in ("단독", "다가구")):
            correction = 0.6
        elif "오피스텔" in use:
            correction = 0.7
        else:  # 아파트 or 미상
            correction = 1.0
        effective_market_price = int(market.median_price_krw * correction)
        # market_estimate 에 보정 사실 기록 (프론트 표시용)
        if correction < 1.0 and market:
            market.error = (
                f"⚠ {extraction.building_use} 는 아파트 실거래가보다 저렴함. "
                f"보정계수 {correction:.0%} 적용. 실제 시세 확인 권장."
            )

    jeontse_ratio, mortgage_ratio, risk_level = _compute_ratios(
        extraction, req.deposit_krw, effective_market_price
    )
    law_hits = _search_law_context(extraction)
    summary, risks = _explain_with_llm(extraction, jeontse_ratio, mortgage_ratio, law_hits)

    return SafeContractResponse(
        extraction=extraction,
        jeontse_ratio=jeontse_ratio,
        mortgage_ratio=mortgage_ratio,
        risk_level=risk_level,
        summary=summary,
        risks=risks,
        referrals=_build_referrals(),
        disclaimer=(
            "이 서비스는 법률 자문이 아닌 참고용 사전 검토 도구입니다. "
            "정확한 판단을 위해 전문가 상담을 권합니다."
        ),
        market_estimate=market,
    )
