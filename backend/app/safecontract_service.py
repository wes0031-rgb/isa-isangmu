"""POST /safecontract business logic — 등기부등본 해석."""
from __future__ import annotations

import json
import re
from typing import Optional

from .azure_clients import get_docintel_client, get_openai_client, get_search_client_law
from .config import get_settings
from .local_search import clean_hanja, find_law_article
from .search_service import embed_query, hybrid_search
from .models import (
    ChecklistCitation,
    MarketEstimate,
    RegistryExtraction,
    RiskItem,
    SafeContractRequest,
    SafeContractResponse,
    ServiceReferral,
)
from .realty_price import (
    RealtyApiNotAuthorized,
    get_region_price_summary,
)


# ---------- PDF / 이미지 → 텍스트 (Azure Document Intelligence) ----------


class DocumentIntelligenceNotConfigured(RuntimeError):
    """AZURE_DOCINTEL_* 환경변수 미설정 시 발생."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Azure Document Intelligence 로 PDF → 텍스트 변환.

    모델 ID는 .env 의 AZURE_DOCINTEL_MODEL_ID 로 주입.
    - prebuilt-layout: 범용 레이아웃 추출 (원래 기본값)
    - 커스텀 추출 모델: Studio에서 학습한 등기부 전용 모델
    """
    client = get_docintel_client()
    if client is None:
        raise DocumentIntelligenceNotConfigured(
            "Azure Document Intelligence 가 설정되지 않았습니다. "
            ".env 의 AZURE_DOCINTEL_ENDPOINT 와 AZURE_DOCINTEL_API_KEY 를 입력하세요."
        )
    
    # SDK v1.0 은 analyze_document 에 AnalyzeDocumentRequest(bytes_source=...) 전달
    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

    settings = get_settings()

    poller = client.begin_analyze_document(
        settings.azure_docintel_model_id,
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
    # ReDoS 방어 — 과도한 길이 입력 시 regex 백트래킹 폭발 방지. PDF 전체 텍스트가
    # 들어올 수 있으므로 앞 20KB 만 검사 (주소는 보통 상단 표제부에 있음).
    MAX_SCAN = 20_000
    if len(address) > MAX_SCAN:
        address = address[:MAX_SCAN]
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
    # layout (평문 추출) 과 Custom Neural (구조화 필드) 은 독립 호출이라 병렬.
    # DocIntel 2번 분량 → 순차 15s 에서 병렬 8~10s 로 단축.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        text_future = pool.submit(extract_text_from_pdf, file_bytes)
        custom_future = pool.submit(_extract_custom_fields, file_bytes)
        text = text_future.result()
        custom_fields = custom_future.result()

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
    return analyze_safecontract(req, custom_fields=custom_fields)


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
- co_owner_name: [deprecated] co_owners 대신 사용. 호환용으로 두 번째 소유자만 넣으면 됨
- co_owners: 공유 소유자 전체 이름 리스트 (owner_name 제외). 단독이면 빈 배열 []. 3명 이상 상속·가족 등기 대응.
- ownership_type: "주요 등기사항 요약" 의 "최종지분" 칸 값 ("단독소유" / "공유 1/2" 등)
- mortgage_creditor: 을구 근저당권자. 다건이면 ", " 로 연결. 없으면 null
- seizure_text: 갑구에 가압류 기재 있으면 채권자·금액 한 줄 요약 (예: "○○은행 3천만원"), 없으면 null
- special_note: 특이사항 한 줄 요약. 복수면 ", " 로 연결. 해당 없으면 null.

**위험·주의 플래그 추출**
- injunction_registered: 갑구에 "가처분" 등기목적 있으면 true (소송 중 · RED)
- provisional_registration: "가등기" 기재 있으면 true (본등기 시 소유권 이전 가능 · YELLOW)
- jeonse_right_registered: 을구에 "전세권설정" 있으면 true (선순위 전세권자 존재 · YELLOW)
- non_residential_use: 표제부 "용도" 에 "근린생활시설·상가·사무실" 등 비주거 용어 있으면 true (주거 계약 위법 소지 · RED). 단 **"오피스텔"** 은 건축법상 업무시설로 등재되지만 주거용 사용이 합법이고 주택임대차보호법 적용 대상이므로 **false** 로 둘 것 ("업무시설" 키워드만 보지 말고 "오피스텔" 표기 우선 확인)

**caution_notes 작성 규칙**
YELLOW 단계 주의사항 문자열 리스트. 계약 자체를 피할 필요는 없지만 확인·조치가 필요한 경우:
- co_owners 비어있지 않으면: "공유자 전원의 동의서·인감 필수 (민법 제265조)"
- provisional_registration=true 이면: "가등기 해제 여부 확인 권장 (본등기 시 소유권 이전 가능)"
- jeonse_right_registered=true 이면: "선순위 전세권자 존재 — 배당 순위 확인"
- owner_change_within_2_years >= 2 이면: "최근 2년 내 소유권 이전 N회 — 투자용 매물 가능성"
- building_use 가 "다세대주택·빌라·오피스텔" 이면: "아파트보다 실거래가 낮음 — 시세 직접 확인 권장"
- building_use 에 "오피스텔" 포함되면 추가로: "오피스텔은 주거·업무 양용 가능 — 주거 목적이면 임대인 동의·전입신고 가능 여부 확인"

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
- payload 의 `pre_computed_risk_level` 이 "red" → summary 첫 글자는 반드시 "🔴"
- "yellow" → summary 첫 글자는 반드시 "🟡"
- "green" → summary 첫 글자는 반드시 "🟢"
- (추가) auction_in_progress=true 이면 "🔴 경매 진행 중", trust_registration=true 이면 "🔴 신탁 등기", seizure_count > 0 이면 "🔴 가압류 N건" 키워드를 summary 에 명시
- 위 셋 중 하나라도 있으면 전세가율이 낮아도 **절대 "안전 범위" 라고 쓰지 말 것**
- pre_computed_risk_level == "green" 일 때만 "안전 범위" 표현 사용 가능

출력은 JSON: {"summary": "...", "risks": [{...}]}"""


# ==================================================================
# Custom Neural 등기부 파싱 (Azure DocIntel isa-jengbu-neural02)
# ==================================================================
# - layout+LLM 경로는 그대로 두고 (평문 → RegistryExtraction), Custom 은 "보강"
# - 분기 규칙 (2026-04-17 팀 결정):
#   · 식별/수치 필드: confidence > 0.8 이면 Custom 값으로 덮어씀
#   · 위험 플래그 (신탁/임의경매/가처분/가등기/전세권): 값 존재 시 OR 머지
#   · 추론 필드 (special_note, caution_notes): LLM 전용 (Custom 은 학습 안 됨)

# Custom 필드명(Studio isa-jengbu-neural02 24-필드 스키마) → RegistryExtraction 필드명
# Studio fields.json 기준 실 필드명으로 동기화 (2026-04-20 검증)
_CUSTOM_TO_STR_FIELD: dict[str, str] = {
    "고유번호": "property_id",
    "건물주소": "address",
    "용도": "building_use",
    "소유자_이름": "owner_name",
    "소유자_등록번호_앞": "owner_registration_front",
    "근저당_채권자": "mortgage_creditor",
}

# 근저당 채권자 복수 — Custom 모델이 채권자2 까지 학습 → mortgage_creditor 에 append
_CUSTOM_EXTRA_CREDITOR_KEYS = ("근저당_채권자2",)

# 근저당 채권최고액 (금액 한글 표기 — "금 3억5천만원" 같은 raw string)
_CUSTOM_MORTGAGE_AMOUNT_KEYS = ("근저당_채권최고액", "근저당_채권최고액2")

# 가압류 — 값이 존재하면 seizure_text 채우고 seizure_count 최소 1 보장
_CUSTOM_SEIZURE_KEY = "가압류"

# Custom → float 변환 (숫자·단위 제거 후 float)
_CUSTOM_TO_FLOAT_FIELD: dict[str, str] = {
    "면적_m2": "area_m2",
}

# Custom 필드가 값 존재 시 True 로 설정하는 위험 플래그
_CUSTOM_FLAG_MAP: dict[str, str] = {
    "신탁": "trust_registration",
    "임의경매개시결정": "auction_in_progress",
    "가처분": "injunction_registered",
    "가등기": "provisional_registration",
    "전세권": "jeonse_right_registered",
}

# 공유자 이름 취합 (owner_name 제외한 나머지 → co_owners)
# Studio 스키마상 본인=소유자_이름, 공유자=소유자_이름2~4
_CUSTOM_COOWNER_KEYS = ("소유자_이름2", "소유자_이름3", "소유자_이름4")

# 대지권 미등기 → raw_notes 에 누적 (RegistryExtraction 에 전용 필드 없음)
_CUSTOM_LAND_RIGHTS_UNREGISTERED_KEY = "대지권 미등기"

_CUSTOM_CONF_THRESHOLD_STR = 0.8  # 식별 필드: 높은 신뢰만 덮어쓰기
_CUSTOM_CONF_THRESHOLD_FLAG = 0.5  # 위험 플래그: 값 자체의 존재가 중요 → threshold 완화


def _extract_custom_fields(file_bytes: bytes) -> dict[str, tuple[str, float]]:
    """Custom Neural 모델로 등기부 구조화 필드 추출.

    반환: {field_name: (value, confidence)} — Custom 미설정·호출 실패 시 빈 dict.
    실패해도 raise 하지 않음: 호출자는 LLM-only 경로로 graceful fallback.
    """
    settings = get_settings()
    model_id = settings.azure_docintel_custom_model_id.strip()
    if not model_id:
        return {}
    client = get_docintel_client()
    if client is None:
        return {}

    import logging as _log
    _logger = _log.getLogger("movewise")
    try:
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        poller = client.begin_analyze_document(
            model_id,
            AnalyzeDocumentRequest(bytes_source=file_bytes),
        )
        result = poller.result()
    except Exception as exc:
        _logger.warning(
            f"_extract_custom_fields ({model_id}) 실패 ({type(exc).__name__}): {exc} "
            f"— layout+LLM 경로로 fallback"
        )
        return {}

    fields: dict[str, tuple[str, float]] = {}
    for doc in getattr(result, "documents", None) or []:
        for name, field in (getattr(doc, "fields", None) or {}).items():
            # SDK v1 DocumentField — value_string / content / value 중 채워진 것
            value = (
                getattr(field, "value_string", None)
                or getattr(field, "content", None)
                or getattr(field, "value", None)
            )
            if value is None:
                continue
            conf = getattr(field, "confidence", None)
            fields[name] = (str(value).strip(), float(conf if conf is not None else 0.0))

    _logger.info(
        f"_extract_custom_fields: {len(fields)} fields extracted "
        f"(model={model_id}, threshold_str={_CUSTOM_CONF_THRESHOLD_STR})"
    )
    return fields


def _merge_custom_into_extraction(
    extraction: RegistryExtraction,
    custom: dict[str, tuple[str, float]],
) -> RegistryExtraction:
    """Custom Neural 결과를 LLM 기반 RegistryExtraction 에 덮어씀.

    빈 custom dict 이면 extraction 그대로 반환. 부분적으로라도 custom 값이 있으면
    신뢰도 게이트 후 식별 필드 덮어쓰기 + 위험 플래그 OR 머지.
    """
    if not custom:
        return extraction

    # 1) 문자열 식별 필드
    # address 는 LLM 이 정제한 값이 Custom 의 raw OCR (띄어쓰기 혼잡) 보다 품질 좋을 때가 많음.
    # → LLM 값이 이미 있으면 Custom 으로 덮지 않고 유지. None/빈 문자열일 때만 Custom 사용.
    for ck, sk in _CUSTOM_TO_STR_FIELD.items():
        if ck not in custom:
            continue
        value, conf = custom[ck]
        if conf < _CUSTOM_CONF_THRESHOLD_STR or not value:
            continue
        if sk == "address" and getattr(extraction, sk, None):
            continue
        setattr(extraction, sk, value)

    # 2) float 필드 (면적 등)
    for ck, sk in _CUSTOM_TO_FLOAT_FIELD.items():
        if ck not in custom:
            continue
        value, conf = custom[ck]
        if conf < _CUSTOM_CONF_THRESHOLD_STR or not value:
            continue
        # "84.97 m²" / "84.97m²" → 84.97
        clean = re.sub(r"[^\d.]", "", value)
        try:
            setattr(extraction, sk, float(clean))
        except (ValueError, TypeError):
            pass

    # 3) 위험 플래그 — 값 존재 = True (OR 머지, 기존 True 는 그대로 유지)
    for ck, sk in _CUSTOM_FLAG_MAP.items():
        if ck not in custom:
            continue
        value, conf = custom[ck]
        if conf < _CUSTOM_CONF_THRESHOLD_FLAG or not value:
            continue
        if not getattr(extraction, sk, False):
            setattr(extraction, sk, True)

    # 4) 공유자 이름 — owner_name 제외하고 co_owners 에 dedupe 추가
    extra_owners: list[str] = []
    for ck in _CUSTOM_COOWNER_KEYS:
        if ck not in custom:
            continue
        value, conf = custom[ck]
        if conf < _CUSTOM_CONF_THRESHOLD_STR or not value:
            continue
        if value == extraction.owner_name:
            continue
        if value in extraction.co_owners or value in extra_owners:
            continue
        extra_owners.append(value)
    if extra_owners:
        extraction.co_owners = [*extraction.co_owners, *extra_owners]
        # 2명 이상이면 ownership_type 보정
        if extraction.co_owners and extraction.ownership_type in (None, "", "단독소유"):
            extraction.ownership_type = f"공유 {1 + len(extraction.co_owners)}명"

    # 5) 근저당 채권자 추가 (2번째 채권자) — 기존 문자열에 없으면 append
    for ck in _CUSTOM_EXTRA_CREDITOR_KEYS:
        if ck not in custom:
            continue
        value, conf = custom[ck]
        if conf < _CUSTOM_CONF_THRESHOLD_STR or not value:
            continue
        current = extraction.mortgage_creditor or ""
        if value in current:
            continue
        extraction.mortgage_creditor = (
            f"{current}, {value}" if current else value
        )

    # 6) 가압류 — 텍스트 존재 시 seizure_text 채우고 count 최소 1 보장 (OR 머지)
    if _CUSTOM_SEIZURE_KEY in custom:
        value, conf = custom[_CUSTOM_SEIZURE_KEY]
        if conf >= _CUSTOM_CONF_THRESHOLD_FLAG and value:
            if not extraction.seizure_text:
                extraction.seizure_text = value
            if extraction.seizure_count < 1:
                extraction.seizure_count = 1

    # 7) 근저당 채권최고액 보강 — LLM 이 누락(0) 한 경우에만 Custom 값 합산.
    #    Custom Neural 정확도 50-77% (메모리 기준) 라 보수적으로 LLM=0 일 때만 사용.
    #    덮어쓰지 않음 — false positive 깡통전세 위험 차단.
    if extraction.mortgage_claim_amount_krw == 0:
        custom_total = 0
        any_custom = False
        for ck in _CUSTOM_MORTGAGE_AMOUNT_KEYS:
            if ck not in custom:
                continue
            value, conf = custom[ck]
            if conf < _CUSTOM_CONF_THRESHOLD_FLAG or not value:
                continue
            try:
                custom_total += _parse_korean_amount(re.sub(r"[^\d억만천]", "", value))
                any_custom = True
            except Exception:
                continue
        if any_custom and custom_total > 0:
            extraction.mortgage_claim_amount_krw = custom_total
            extraction.mortgage_total_krw = int(custom_total * 0.83)

    # 8) 대지권 미등기 → raw_notes 누적
    if _CUSTOM_LAND_RIGHTS_UNREGISTERED_KEY in custom:
        value, conf = custom[_CUSTOM_LAND_RIGHTS_UNREGISTERED_KEY]
        if conf >= _CUSTOM_CONF_THRESHOLD_FLAG and value:
            marker = f"대지권 미등기: {value}"
            if marker not in extraction.raw_notes:
                extraction.raw_notes = [*extraction.raw_notes, marker]

    return extraction


_EXTRACT_INPUT_CHAR_CAP = 15_000  # ~5-7K tokens. 20 페이지 등기부도 표제부·갑구·을구는 앞 15K 안에 다 있음.


def _extract_with_llm(text: str) -> RegistryExtraction:
    """GPT-4o + Structured Output (json_schema strict 모드) 로 등기부 파싱.

    스키마 100% 준수 보장 — 필드 누락/타입 오류 없이 RegistryExtraction 반환.
    실패 시 rule-based regex 폴백.

    입력 cap: DocIntel PDF 텍스트는 20페이지 60K chars 까지 가능. 앞 15K 만 LLM 에
    보내 응답 지연·토큰 비용을 제어. 등기부 핵심은 표제부·갑구·을구로 상단 집중.
    """
    client = get_openai_client()
    if client is None:
        return _extract_rule_based(text)
    settings = get_settings()

    truncated_from = 0
    if len(text) > _EXTRACT_INPUT_CHAR_CAP:
        import logging as _log
        _log.getLogger("movewise").info(
            f"_extract_with_llm: text {len(text)}→{_EXTRACT_INPUT_CHAR_CAP} chars (truncated)"
        )
        truncated_from = len(text)
        text = text[:_EXTRACT_INPUT_CHAR_CAP]

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
            seed=42,
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
            max_tokens=1500,  # 추출 필드 한정 — 출력 cap
            timeout=20,
        )
        raw = resp.choices[0].message.content or "{}"
        ext = RegistryExtraction(**json.loads(raw))
        if truncated_from:
            ext.raw_notes = [
                *ext.raw_notes,
                f"⚠ 등기부 본문이 길어({truncated_from:,}자) 앞 {_EXTRACT_INPUT_CHAR_CAP:,}자만 분석 — "
                "후반부 갑구·을구 항목(잦은 소유권 이전·다건 근저당 등) 일부 누락 가능. 등기부 직접 검토 권장.",
            ]
        return ext
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
                seed=42,
                messages=[
                    {"role": "system", "content": EXTRACT_SYSTEM},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
                max_tokens=1500,
                timeout=20,
            )
            raw = resp.choices[0].message.content or "{}"
            ext = RegistryExtraction(**json.loads(raw))
            if truncated_from:
                ext.raw_notes = [
                    *ext.raw_notes,
                    f"⚠ 등기부 본문이 길어({truncated_from:,}자) 앞 {_EXTRACT_INPUT_CHAR_CAP:,}자만 분석 — "
                    "등기부 직접 검토 권장.",
                ]
            return ext
        except Exception:
            ext = _extract_rule_based(text)
            ext.raw_notes = [
                *ext.raw_notes,
                "⚠ LLM 분석 실패 — 룰베이스 폴백으로 일부 위험(가처분·전세권·비주거 등) 누락 가능. 직접 검토 필수.",
            ]
            return ext


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
    """law-index 단독 하이브리드 검색 (semantic + vector).

    등기부 특이사항에 매칭되는 조문을 불러와 LLM 설명 단계에 전달.
    3-index 분리 체제라 source_type 필터 불필요 — 바로 law-index 에 쿼리.
    """
    client = get_search_client_law()
    if client is None:
        return []
    settings = get_settings()
    queries: list[str] = []
    if extraction.mortgage_total_krw > 0:
        queries.append("근저당 대항력 우선변제")
    if extraction.seizure_count > 0:
        queries.append("가압류 임차권")
    if extraction.trust_registration:
        queries.append("신탁등기 임차인")
    if extraction.auction_in_progress:
        queries.append("임의경매 배당 순위")
    if extraction.injunction_registered:
        queries.append("가처분 소송 임차인")
    if extraction.non_residential_use:
        queries.append("주택임대차보호법 적용 범위 비주거")
    if extraction.provisional_registration:
        queries.append("가등기 본등기 소유권 이전")
    if extraction.jeonse_right_registered:
        queries.append("선순위 전세권 배당")
    if len(extraction.co_owners) > 0:
        queries.append("공유 부동산 임대 동의 민법 제265조")

    seen_ids: set[str] = set()
    hits: list[dict] = []
    for q in queries:
        # 쿼리별 임베딩 (4건 이하이므로 비용 미미). embedding None 이면 semantic-only
        embedding = embed_query(q)
        for h in hybrid_search(
            client,
            q,
            top=2,
            semantic_config=settings.azure_search_law_semantic_config,
            embedding=embedding,
        ):
            hid = h.get("id")
            if hid and hid in seen_ids:
                continue
            if hid:
                seen_ids.add(hid)
            hits.append(h)
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
    # 시세 미입력 시에도 등기상 critical/cautionary 플래그는 그대로 평가해야 함.
    # (이전 버그: market<=0 일 때 무조건 'green' 반환 → 경매·신탁이어도 헤더가 🟢
    # "안전" 표시 + 본문 risks 는 🔴 — 헤더/본문 모순)
    has_market = market > 0
    if has_market:
        jeontse = round(deposit / market, 3)
        mortgage = round(extraction.mortgage_total_krw / market, 3)
    else:
        jeontse, mortgage = 0.0, 0.0
    combined = jeontse + mortgage

    # RED 트리거 (치명) — 시세 의존인 깡통전세는 시세 있을 때만, 등기 플래그는 항상 평가
    # 임계값은 frontend stat 색상과 일치 (jeontse>=80 / mortgage>=50 / combined>=100)
    critical = (
        (has_market and (combined >= 1.0 or jeontse >= 0.8 or mortgage >= 0.5))
        or extraction.seizure_count > 0
        or extraction.trust_registration
        or extraction.auction_in_progress
        or extraction.injunction_registered  # 가처분
        or extraction.non_residential_use  # 비주거용
    )
    # YELLOW 트리거 (주의) — frontend warning 색상 임계값과 일치 (jeontse>=70 / mortgage>=30)
    cautionary = (
        (has_market and (jeontse >= 0.7 or mortgage >= 0.3))
        or extraction.provisional_registration  # 가등기
        or extraction.jeonse_right_registered  # 전세권
        or len(extraction.co_owners) > 0  # 공동명의
        or extraction.owner_change_within_2_years >= 2  # 잦은 소유권 이전
    )
    if critical:
        level = "red"
    elif cautionary:
        level = "yellow"
    else:
        level = "green"
    return jeontse, mortgage, level


def _explain_with_llm(
    extraction: RegistryExtraction,
    jeontse_ratio: float,
    mortgage_ratio: float,
    law_hits: list[dict],
    pre_computed_risk_level: str = "green",
) -> tuple[str, list[RiskItem]]:
    client = get_openai_client()
    if client is None:
        return _explain_rule_based(extraction, jeontse_ratio, mortgage_ratio)

    settings = get_settings()
    # law_hits cap: 상위 6건 × 400 chars → 최대 2400 chars. 쿼리별 의미 다양성 보존하며 상한 명시.
    context = "\n---\n".join(
        f"[{h.get('law_name')} {h.get('article')}] {h.get('content','')[:400]}"
        for h in law_hits[:6]
    )
    payload = {
        "extraction": extraction.model_dump(),
        "jeontse_ratio": jeontse_ratio,
        "mortgage_ratio": mortgage_ratio,
        "law_context": context,
        # rule-based 가 이미 결정한 risk_level. summary 첫 이모지·표현이 이 등급에
        # 맞아야 헤더(risk_level 기반)와 본문 톤이 어긋나지 않음.
        "pre_computed_risk_level": pre_computed_risk_level,
    }
    resp = client.chat.completions.create(
        model=settings.azure_openai_deployment_name,
        temperature=0,
        seed=42,
        messages=[
            {"role": "system", "content": EXPLAIN_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        max_tokens=2000,  # 위험 요약 + 5~8 risk items 충분
        timeout=20,
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

    # 0) 치명적 상태 먼저 체크 — 전세가율이 낮아도 RED
    critical_flags: list[str] = []
    if extraction.auction_in_progress:
        critical_flags.append("경매 진행 중")
    if extraction.trust_registration:
        critical_flags.append("신탁 등기")
    if extraction.seizure_count > 0:
        critical_flags.append(f"가압류 {extraction.seizure_count}건")
    if extraction.injunction_registered:
        critical_flags.append("가처분")
    if extraction.non_residential_use:
        critical_flags.append("비주거용 등재")

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
        # 깡통전세는 아니지만 단일 지표가 RED 임계값 도달 (combined<100 케이스)
        risks.append(RiskItem(
            severity="red",
            label=f"전세가율 {jeontse_pct}% · 근저당비율 {mortgage_pct}%",
            explanation_plain=(
                "단일 지표가 위험 임계값(전세가율 80% / 근저당비율 50%) 에 도달. "
                "HUG 보증보험 가입 가능 여부 확인 + 전입신고·확정일자로 대항력·우선변제권 확보 필수."
            ),
            related_laws=[_cite("주택임대차보호법", "제3조의2")],
        ))
        summary_parts.append(f"🔴 전세가율 {jeontse_pct}% · 근저당비율 {mortgage_pct}%")
    elif jeontse_ratio >= 0.7 or mortgage_ratio >= 0.3:
        risks.append(RiskItem(
            severity="yellow",
            label=f"전세가율 {jeontse_pct}% · 근저당비율 {mortgage_pct}%",
            explanation_plain=(
                "안전 범위를 약간 벗어났습니다. HUG 보증보험 가입 여부를 확인해보세요. "
                "전입신고+확정일자로 대항력·우선변제권을 확보해두는 것이 필수입니다."
            ),
            related_laws=[_cite("주택임대차보호법", "제3조의2")],
        ))
        summary_parts.append(f"🟡 전세가율 {jeontse_pct}% / 근저당 {mortgage_pct}% 주의")
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
    if extraction.injunction_registered:
        risks.append(RiskItem(
            severity="red",
            label="가처분 등기",
            explanation_plain=(
                "가처분은 소유권 다툼 등 소송이 진행 중임을 뜻합니다. "
                "결과에 따라 소유자가 바뀔 수 있어 임차인 권리가 불안정합니다. 계약 피하는 것을 권장."
            ),
        ))
    if extraction.non_residential_use:
        risks.append(RiskItem(
            severity="red",
            label="비주거용 건물",
            explanation_plain=(
                "등기상 용도가 근린생활시설·상가·사무실 등 비주거입니다. "
                "주거 목적 전세 계약은 주택임대차보호법 적용이 제한될 수 있고, 불법 거주로 과태료·퇴거 위험."
            ),
        ))
    # === YELLOW 단계 주의 ===
    if extraction.provisional_registration:
        risks.append(RiskItem(
            severity="yellow",
            label="가등기 존재",
            explanation_plain=(
                "가등기는 향후 본등기 권리를 미리 표시한 것. 본등기 완료 시 소유권이 "
                "다른 사람에게 넘어갈 수 있으므로 가등기 해제 여부 확인 필요."
            ),
        ))
    if extraction.jeonse_right_registered:
        risks.append(RiskItem(
            severity="yellow",
            label="선순위 전세권 존재",
            explanation_plain=(
                "을구에 전세권이 이미 설정돼 있습니다. 배당 순위에서 이 전세권이 우선하므로 "
                "본인 보증금 회수 순위가 뒤로 밀릴 수 있어요."
            ),
            related_laws=[_cite("주택임대차보호법", "제3조의2")],
        ))
    if len(extraction.co_owners) > 0:
        owner_count = 1 + len(extraction.co_owners)
        risks.append(RiskItem(
            severity="yellow",
            label=f"공동명의 {owner_count}인",
            explanation_plain=(
                f"공유 소유자 {owner_count}명 전원의 동의·서명이 계약에 필수입니다 (민법 제265조). "
                "대리인 계약이라면 인감증명서 · 위임장 반드시 확인하세요."
            ),
        ))
    if extraction.owner_change_within_2_years >= 2:
        risks.append(RiskItem(
            severity="yellow",
            label=f"소유권 이전 {extraction.owner_change_within_2_years}회 (최근 2년)",
            explanation_plain=(
                "최근 2년 내 소유자가 여러 번 바뀐 매물. 투자·명의신탁·갭투자 가능성이 있어 "
                "집주인의 실소유권·재정상태 확인을 권장."
            ),
        ))
    # 오피스텔: 주거 / 업무 양용 가능. RED 비주거가 아니라 YELLOW 로 사용자에게 확인 안내.
    if extraction.building_use and "오피스텔" in extraction.building_use:
        risks.append(RiskItem(
            severity="yellow",
            label="오피스텔 — 주거·업무 용도 확인 필요",
            explanation_plain=(
                "오피스텔은 건축법상 업무시설이지만 주거용 사용도 합법입니다. "
                "주거 목적이면 ① 임대인이 주거용으로 운영 동의했는지 ② 전입신고·확정일자 받을 수 있는지 "
                "③ 전세대출(HUG/SGI) 가능 매물인지 확인하세요. 사무실 전용으로 운영되는 오피스텔이라면 "
                "주택임대차보호법 적용이 어려워 보증금 보호가 약해집니다."
            ),
            related_laws=[_cite("주택임대차보호법", "제2조")],
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
    """region(시도+시군구) 으로 국토부 아파트 실거래가 자동 조회.

    시세 미입력 시 analyze_safecontract 가 호출. 아파트 전용 API 라 비아파트는
    error 필드로 표시되고, 전세가율 계산은 여전히 생략(effective=0).
    """
    if not region:
        return None
    try:
        s = get_region_price_summary(region)
    except RealtyApiNotAuthorized as exc:
        return MarketEstimate(
            source="국토교통부 아파트 매매 실거래가 API",
            region=region,
            query_ym="",
            error=f"API 승인 대기: {exc}",
        )
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


def analyze_safecontract(
    req: SafeContractRequest,
    custom_fields: Optional[dict[str, tuple[str, float]]] = None,
) -> SafeContractResponse:
    if not req.text:
        raise ValueError("text is required (PDF 업로드는 /safecontract/upload 참고)")

    # 결정론 캐시 — 같은 입력(텍스트+보증금+시세+지역+Custom 결과) → 같은 결과 반환.
    # Azure OpenAI seed=42 는 best-effort 라 LLM 추출·요약이 호출마다 미세하게 달라질 수
    # 있음. 발표 시연·재현성을 위해 hash 기반 LRU 캐시.
    cache_key = _safecontract_cache_key(req, custom_fields)
    cached = _safecontract_cache_get(cache_key)
    if cached is not None:
        return cached

    extraction = _extract_with_llm(req.text)
    # Custom Neural 로 식별 필드·위험 플래그 보강 (PDF 경로에서만 custom_fields 전달)
    if custom_fields:
        extraction = _merge_custom_into_extraction(extraction, custom_fields)

    # 오피스텔 하드 가드: 건축법상 "업무시설" 로 등재되지만 주거용 사용이 합법이고
    # 주택임대차보호법 적용 대상. LLM/Custom 이 "업무시설" 키워드만 보고 비주거로
    # false positive 잡는 것을 방지.
    if extraction.building_use and "오피스텔" in extraction.building_use:
        extraction.non_residential_use = False

    # 등기부 주소에서 시도+시군구 자동 추출 → 체크리스트 프리필 + 시세 자동 조회용
    inferred_region = (
        _parse_region_from_address(extraction.address)
        or _parse_region_from_address(req.text)
    )
    import logging as _l
    _l.getLogger("movewise").warning(
        f"[safecontract] address={extraction.address!r} → inferred_region={inferred_region!r}"
    )

    # 시세 자동 조회: 사용자 입력 0 이면 inferred_region 으로 국토부 API fetch.
    # 단, 국토부 API 는 아파트 전용 (RTMSDataSvcAptTradeDev) — 다세대/빌라/오피스텔에
    # 아파트 시세를 적용하면 시세 인플레이션 → jeontse_ratio 가 실제보다 낮아져
    # 깡통전세인데 GREEN 으로 잘못 분류됨. 비아파트면 자동 조회 차단 + 사용자에게
    # 직접 입력 안내 (시세 미입력 카드 활용).
    market = None
    effective_market_price = req.expected_market_price_krw
    if effective_market_price <= 0:
        non_apt_keywords = ("다세대", "빌라", "연립", "오피스텔", "단독")
        is_non_apt = bool(extraction.building_use) and any(
            k in extraction.building_use for k in non_apt_keywords
        )
        if is_non_apt:
            market = MarketEstimate(
                source="국토교통부 아파트 매매 실거래가 API",
                region=req.region or inferred_region or "",
                query_ym="",
                error=(
                    f"건물 용도가 '{extraction.building_use}' — 국토부 아파트 API 적용 시 "
                    f"시세가 부풀려져 깡통전세 위험을 놓칠 수 있어 자동 조회를 생략했습니다. "
                    f"네이버부동산·KB부동산 등에서 같은 단지·평형 시세를 확인 후 직접 입력하세요."
                ),
            )
        else:
            auto_region = req.region or inferred_region
            market = _fetch_market_estimate(auto_region)
            if market and market.median_price_krw:
                effective_market_price = market.median_price_krw

    jeontse_ratio, mortgage_ratio, risk_level = _compute_ratios(
        extraction, req.deposit_krw, effective_market_price
    )
    law_hits = _search_law_context(extraction)
    summary, risks = _explain_with_llm(
        extraction, jeontse_ratio, mortgage_ratio, law_hits, risk_level
    )

    response = SafeContractResponse(
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
        inferred_region=inferred_region,
    )
    _safecontract_cache_put(cache_key, response)
    return response


# ===== 결정론화 캐시 =====
# 같은 입력 → 같은 출력. SafeContract 는 LLM 추출 + 요약 두 번의 LLM 호출이 모두
# best-effort seed 라 호출마다 미세 편차 → 분석 신뢰도 떨어짐. hash 기반 LRU 로 보강.
from collections import OrderedDict as _SCOrdDict
_SAFECONTRACT_CACHE_MAX = 256  # 응답 1건 ~5-15KB. 상한 ~4MB.
_SAFECONTRACT_CACHE: "_SCOrdDict[str, SafeContractResponse]" = _SCOrdDict()


def _safecontract_cache_get(key: str):
    val = _SAFECONTRACT_CACHE.get(key)
    if val is not None:
        _SAFECONTRACT_CACHE.move_to_end(key)
    return val


def _safecontract_cache_put(key: str, value: SafeContractResponse) -> None:
    _SAFECONTRACT_CACHE[key] = value
    _SAFECONTRACT_CACHE.move_to_end(key)
    while len(_SAFECONTRACT_CACHE) > _SAFECONTRACT_CACHE_MAX:
        _SAFECONTRACT_CACHE.popitem(last=False)


def _safecontract_cache_key(
    req: SafeContractRequest,
    custom_fields: Optional[dict[str, tuple[str, float]]],
) -> str:
    """SafeContractRequest + Custom Neural 결과까지 포함한 SHA256 해시.

    Custom 결과를 포함하지 않으면 '같은 PDF + 직접 입력' vs '같은 PDF + Custom' 이
    같은 키로 충돌 → 다른 결과를 같은 캐시에 덮어쓸 수 있음.
    """
    import hashlib
    blob = json.dumps(
        {
            "req": req.model_dump(mode="json"),
            "custom": (
                # tuple → list 직렬화. 키 정렬로 안정.
                {k: [v[0], round(v[1], 4)] for k, v in sorted(custom_fields.items())}
                if custom_fields else None
            ),
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
