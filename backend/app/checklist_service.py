"""POST /checklist business logic — 4-step RAG pipeline."""
from __future__ import annotations

import json
from datetime import date

from .azure_clients import get_openai_client, get_search_client_procedure
from .config import get_settings
from .date_utils import compute_deadline, compute_start_date
from .local_search import find_law_article
from .local_search import search as local_search
from .models import (
    ChecklistCitation,
    ChecklistItem,
    ChecklistRequest,
    ChecklistResponse,
)
from .region_services import enrich_item_with_region


def _enrich_citation(cite: dict) -> dict:
    """Citation dict 에 Index A 조문 텍스트를 붙여 반환. 한자는 로드 시점에 이미 제거됨."""
    law_name = cite.get("law_name") or ""
    article = cite.get("article") or ""
    if not law_name or not article:
        return cite
    found = find_law_article(law_name, article)
    if not found:
        return cite
    content = (found.get("content") or "").strip()
    title = (found.get("title") or "").strip()
    source_url = found.get("source_url")
    enriched = dict(cite)
    if content and not enriched.get("article_text"):
        enriched["article_text"] = content[:500] + ("…" if len(content) > 500 else "")
    if title and not enriched.get("article_title"):
        enriched["article_title"] = title
    if source_url and not enriched.get("source_url"):
        enriched["source_url"] = source_url
    return enriched

# ---------- Step 1: 조건 → 검색 쿼리 변환 ----------

QUERY_SYSTEM_PROMPT = """당신은 한국에서 이사 관련 행정 절차를 안내하는 RAG 시스템의 쿼리 플래너입니다.
사용자의 조건을 분석하여 Azure AI Search에 던질 한국어 검색 쿼리 목록을 JSON 배열로 출력하세요.

규칙:
1. 반드시 필요한 절차(전입신고, 확정일자, 전기·수도·가스 명의변환)는 기본으로 포함
2. 사용자가 해당되지 않는 항목(예: 반려동물 없음)은 쿼리 생성 금지
3. 지역 정보가 있으면 쿼리에 시·도·구 키워드를 넣어 메타 필터에 걸리도록 할 것
4. 5~10개의 쿼리를 생성"""


def _effective_contracts(req: ChecklistRequest) -> list[str]:
    return list(req.contracts) if req.contracts else [req.contract]


def build_queries_rule_based(req: ChecklistRequest) -> list[str]:
    """Fallback query generation (Azure OpenAI 없을 때)."""
    q = ["전입신고 방법", "확정일자 신청"]
    contracts = _effective_contracts(req)
    for c in contracts:
        if c in ("전세", "월세"):
            q.append(f"대항력 우선변제권 {c}")
    q.extend([
        "전기 명의변환",
        f"수도 명의변환 {req.region}",
        f"도시가스 명의변환 {req.region}",
        "인터넷 이전 설치",
        "우편물 주소이전",
    ])
    if req.has_pet:
        q.append("반려동물 등록 주소변경")
    if req.has_car:
        q.append("자동차 변경등록")
    if req.has_children and req.children_school_level:
        q.append(f"자녀 {req.children_school_level} 전학")
    if req.is_foreigner:
        q.append("외국인등록 주소변경")
    if req.special_concerns:
        for c in req.special_concerns:
            q.append(c)
    return q


def build_queries_llm(req: ChecklistRequest) -> list[str]:
    client = get_openai_client()
    if client is None:
        return build_queries_rule_based(req)
    settings = get_settings()
    user_prompt = (
        f"세대유형: {req.household}\n"
        f"계약유형: {', '.join(_effective_contracts(req))}\n"
        f"지역: {req.region}\n"
        f"이사일: {req.move_date.isoformat()}\n"
        f"반려동물: {req.has_pet}, 자동차: {req.has_car}, 자녀: {req.has_children}\n"
        f"외국인: {req.is_foreigner}\n"
        f"특이사항: {req.special_concerns}\n"
        "→ JSON 배열로만 응답. 예: [\"전입신고\", \"확정일자 월세\", ...]"
    )
    # 429/timeout 자동 fallback
    try:
        resp = client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=0,
            messages=[
                {"role": "system", "content": QUERY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            timeout=10,
        )
    except Exception as exc:
        import logging
        logging.getLogger("movewise").warning(
            f"Azure OpenAI query LLM failed ({type(exc).__name__}): {exc} — falling back to rule-based"
        )
        return build_queries_rule_based(req)

    raw = resp.choices[0].message.content or "[]"
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "queries" in parsed:
            return list(parsed["queries"])
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return build_queries_rule_based(req)


# ---------- Step 2: AI Search 하이브리드 검색 ----------


def search_procedures(queries: list[str], req: ChecklistRequest) -> list[dict]:
    client = get_search_client_procedure()
    if client is None:
        # Local keyword search over curated chunks (index_b_chunks_curated.jsonl)
        return local_search(queries, top_k_per_query=3)
    results: list[dict] = []
    for q in queries:
        hits = client.search(
            search_text=q,
            filter=f"region eq '전국' or region eq '{req.region}'",
            top=3,
            query_type="semantic",
            semantic_configuration_name="movewise-semantic",
        )
        for h in hits:
            results.append(dict(h))
    return results


# ---------- Step 3: LLM 체크리스트 구조화 ----------

STRUCTURE_SYSTEM_PROMPT = """당신은 이사 후 행정 절차 체크리스트 생성기입니다.
주어진 검색 결과(chunks)를 근거로 사용자 조건에 맞는 체크리스트 항목을 JSON으로 출력하세요.

각 항목의 필수 필드:
- category: "전입신고" 같은 한글 카테고리
- title: 사용자에게 보일 제목
- description: 2~3문장 요약
- d_day_offset: 이사일 기준 시작일 (정수, 양수=이사 후)
- has_legal_deadline: 법정 기한 여부
- deadline_days: 기한이 있으면 일수, 없으면 null
- method: "정부24 온라인 또는 주민센터 방문"
- contact: 연락처 (있으면)
- citations: [{"law_name":"주민등록법","article":"제16조"}]

반드시 검색 결과의 content에 있는 내용만 사용. 없는 정보는 만들지 말 것."""


def structure_checklist_llm(
    req: ChecklistRequest, chunks: list[dict]
) -> list[ChecklistItem]:
    client = get_openai_client()
    if client is None:
        # 폴백도 검색된 청크의 메타데이터를 활용
        return structure_checklist_fallback(req, chunks)

    settings = get_settings()
    context = "\n\n---\n\n".join(
        f"[{c.get('id','?')}]\nbreadcrumb: {c.get('breadcrumb','')}\n"
        f"laws: {c.get('related_laws', [])}\n"
        f"deadlines: {c.get('deadlines', [])}\n"
        f"content: {c.get('content','')[:600]}"
        for c in chunks[:20]
    )

    import logging as _log
    _logger = _log.getLogger("movewise")
    try:
        resp = client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=0,
            messages=[
                {"role": "system", "content": STRUCTURE_SYSTEM_PROMPT},
                {"role": "user", "content": f"조건:\n{req.model_dump_json()}\n\n검색결과:\n{context}"},
            ],
            response_format={"type": "json_object"},
            timeout=20,
        )
    except Exception as exc:
        _logger.warning(
            f"structure LLM failed ({type(exc).__name__}): {exc} — falling back"
        )
        return structure_checklist_fallback(req, chunks)

    raw = resp.choices[0].message.content or '{"items": []}'
    try:
        parsed = json.loads(raw)
        items_data = parsed.get("items", parsed if isinstance(parsed, list) else [])
        items = []
        for d in items_data:
            items.append(_item_from_dict(d, req.move_date))
        return items
    except (json.JSONDecodeError, ValueError) as exc:
        _logger.warning(f"structure LLM parse error: {exc} — falling back")
        return structure_checklist_fallback(req, chunks)


def _item_from_dict(d: dict, move_date: date) -> ChecklistItem:
    d_day = int(d.get("d_day_offset", 1))
    start = compute_start_date(move_date, d_day)
    deadline_days = d.get("deadline_days")
    deadline_date = (
        compute_deadline(move_date, int(deadline_days)) if deadline_days else None
    )
    return ChecklistItem(
        category=d.get("category", "일반"),
        title=d.get("title", d.get("category", "일반")),
        description=d.get("description", ""),
        d_day_offset=d_day,
        start_date=start,
        has_legal_deadline=bool(d.get("has_legal_deadline")),
        deadline_date=deadline_date,
        deadline_days=int(deadline_days) if deadline_days else None,
        penalty=d.get("penalty"),
        method=d.get("method"),
        contact=d.get("contact"),
        region_hint=d.get("region_hint"),
        citations=[
            ChecklistCitation(**_enrich_citation(c))
            for c in d.get("citations", [])
        ],
    )


def structure_checklist_fallback(
    req: ChecklistRequest, chunks: list[dict] | None = None
) -> list[ChecklistItem]:
    """Rule-based fallback enriched with local chunk data when available.

    Azure OpenAI 없을 때도 index_b_chunks_curated.jsonl 검색 결과를 활용하여
    실제 법 조항·마감일·카테고리를 체크리스트에 반영한다.
    """
    chunks = chunks or []
    # 검색된 청크에서 category별 대표 데이터 집계
    cat_to_chunk: dict[str, dict] = {}
    for c in chunks:
        for cat in c.get("category", []):
            if cat not in cat_to_chunk:
                cat_to_chunk[cat] = c

    def enrich(default_item: dict) -> dict:
        """보수적 enrichment — citations 보강만 하고 deadline/penalty는 절대 덮어쓰지 않음.

        청크의 deadline/penalty는 문서 전체에서 추출된 값이라 특정 항목과 무관할 수
        있어서 오염 위험이 큼. base 항목이 이미 정확한 값을 가지고 있으면 유지.
        """
        cat = default_item["category"]
        chunk = cat_to_chunk.get(cat)
        if chunk is None:
            return default_item
        # citations 만 보강 (base에 없을 때)
        if chunk.get("related_laws") and not default_item.get("citations"):
            laws = []
            for cite in chunk["related_laws"][:2]:
                parts = cite.split(" 제", 1)
                if len(parts) == 2:
                    laws.append({"law_name": parts[0], "article": "제" + parts[1]})
            if laws:
                default_item["citations"] = laws
        # source_url을 region_hint로 활용
        if chunk.get("source_url") and not default_item.get("region_hint"):
            default_item["_source_url"] = chunk["source_url"]
        return default_item

    base: list[dict] = [
        {
            "category": "전입신고",
            "title": "전입신고",
            "description": "이사한 날부터 14일 이내에 정부24 또는 주민센터에서 전입신고를 해야 합니다.",
            "d_day_offset": 1,
            "has_legal_deadline": True,
            "deadline_days": 14,
            "penalty": "5만원 이하 과태료",
            "method": "정부24 온라인 또는 주민센터 방문",
            "citations": [{"law_name": "주민등록법", "article": "제16조"}],
        },
        {
            "category": "전기 명의변환",
            "title": "전기 명의변경",
            "description": "한전 123으로 전화 또는 한전 앱에서 명의변경 신청.",
            "d_day_offset": 2,
            "has_legal_deadline": False,
            "contact": "한전 123",
        },
        {
            "category": "수도 명의변환",
            "title": "수도 명의변경",
            "description": "해당 지역 수도사업소에 명의변경 신청.",
            "d_day_offset": 2,
            "has_legal_deadline": False,
            "region_hint": req.region,
        },
        {
            "category": "도시가스 명의변환",
            "title": "도시가스 명의변경",
            "description": "지역 공급사 고객센터에 명의변경 신청 (한국도시가스협회 매핑 참조).",
            "d_day_offset": 2,
            "has_legal_deadline": False,
        },
        {
            "category": "대형폐기물 배출",
            "title": "불필요한 가구·가전 폐기 신청",
            "description": (
                "버릴 가구·가전은 시·구청 폐기물 신고 시스템에서 미리 신청. "
                "수수료 2,000~15,000원. TV·냉장고·세탁기·에어컨은 한국전자제품자원순환공제조합 "
                "(1599-0903) 통해 무상 수거 가능."
            ),
            "d_day_offset": -14,
            "has_legal_deadline": False,
            "method": "시·구청 폐기물 시스템 / 전자제품 무상수거 1599-0903",
        },
        {
            "category": "이사업체 피해예방",
            "title": "이사업체 견적 비교 + 허가업체 확인",
            "description": (
                "이사 3~4주 전 최소 3개 업체 방문 견적 비교. "
                "전국화물자동차운송주선사업연합회(allmaeul.or.kr)에서 '화물자동차 운송주선' "
                "허가업체 여부 반드시 확인. 계약금은 총액의 10% 이내, 견적서에 품목·옵션·"
                "추가요금 조건 모두 서면 명시. 피해 시 소비자상담센터 1372."
            ),
            "d_day_offset": -21,
            "has_legal_deadline": False,
            "method": "allmaeul.or.kr 허가업체 조회 · 소비자상담센터 1372",
        },
        {
            "category": "인터넷 이전 설치",
            "title": "인터넷·TV 이전 설치",
            "description": "KT(100), SK브로드밴드(106), LG U+(101) 이전 신청.",
            "d_day_offset": -7,
            "has_legal_deadline": False,
        },
        {
            "category": "우편물 주소이전",
            "title": "우체국 주소이전 서비스",
            "description": "service.epost.go.kr에서 주소이전 서비스 신청. 유효기간 3개월.",
            "d_day_offset": 3,
            "has_legal_deadline": False,
        },
        {
            "category": "건강보험 주소변경",
            "title": "건강보험 주소 반영 확인",
            "description": (
                "전입신고 시 국민건강보험공단에 자동 반영되는 것이 원칙. "
                "직장가입자는 회사 주소 기준이라 별도 변경 불필요. "
                "지역가입자는 '국민건강보험공단 앱' 또는 ☎ 1577-1000 에서 확인 권장."
            ),
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "method": "국민건강보험공단 앱 또는 ☎ 1577-1000",
        },
        {
            "category": "금융기관 주소변경",
            "title": "은행·카드사 주소변경",
            "description": (
                "주거래 은행·카드사 앱에서 주소 변경. 미변경 시 우편물 미수령으로 "
                "카드 갱신·대출 심사 지연 가능. 금융결제원 '내계좌한눈에' "
                "(payinfo.or.kr)에서 본인 명의 계좌 일괄 조회 후 각 앱에서 변경."
            ),
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "method": "각 금융기관 앱 · 금융결제원 내계좌한눈에 payinfo.or.kr",
        },
    ]

    # 임차인 보호: 전세/월세일 때만 확정일자·대항력·퇴거 관련 추가 (자가 제외)
    contracts = _effective_contracts(req)
    is_tenant = any(c in ("전세", "월세") for c in contracts)

    if is_tenant:
        base.insert(1, {
            "category": "확정일자/임차권",
            "title": "확정일자 취득",
            "description": "보증금 보호를 위해 전입신고 당일 확정일자를 받아두세요.",
            "d_day_offset": 1,
            "deadline_days": 1,  # 전입신고 당일 권장 (우선변제권 확보 핵심)
            "has_legal_deadline": False,
            "method": "주민센터 방문 또는 인터넷등기소",
            "citations": [{"law_name": "주택임대차보호법", "article": "제3조의2"}],
        })

        # === 이전 집 퇴거 항목 (음수 d_day) ===
        base.extend([
            {
                "category": "계약 해지 통지",
                "title": "임대인에게 계약 종료 통지",
                "description": (
                    "계약 만료 6개월~2개월 전에 서면(문자·카톡 포함)으로 종료 의사 통지. "
                    "통지 안 하면 묵시적 갱신되어 이사 곤란."
                ),
                "d_day_offset": -60,
                "has_legal_deadline": True,
                "penalty": "묵시적 갱신 (2년 자동 연장)",
                "citations": [{"law_name": "주택임대차보호법", "article": "제6조"}],
            },
            {
                "category": "보증금 반환 일정 확인",
                "title": "임대인에게 보증금 반환 일정 재확인",
                "description": (
                    "이사 당일 보증금 반환이 원칙. 임대인이 미루면 "
                    "분쟁 조정 또는 임차권등기명령 준비."
                ),
                "d_day_offset": -30,
                "has_legal_deadline": False,
                "method": "주택임대차분쟁조정위원회 1600-2571",
                "citations": [{"law_name": "주택임대차보호법", "article": "제4조"}],
            },
            {
                "category": "사전 퇴실 점검",
                "title": "임대인과 1차 점검 + 퇴실 점검표 준비",
                "description": (
                    "이사 전 임대인과 함께 집 상태 사전 확인, 공제 항목 미리 합의. "
                    "'퇴실점검표' 양식 준비하여 방·거실·주방·욕실·가전 상태 체크."
                ),
                "d_day_offset": -7,
                "has_legal_deadline": False,
                "method": "문자·카톡 기록 보관 필수",
            },
            {
                "category": "계량기 촬영",
                "title": "전기·수도·가스 계량기 사진+영상 기록",
                "description": (
                    "이사 당일 아침 계량기 숫자를 사진과 영상으로 기록. "
                    "임대인과 함께 확인. 요금 정산 분쟁의 결정적 증거."
                ),
                "d_day_offset": 0,
                "has_legal_deadline": False,
                "method": "사진 + 1~2초 영상 (조작 의심 차단)",
            },
            {
                "category": "최종 퇴실 점검",
                "title": "임대인과 함께 집 상태 최종 점검 + 양측 서명",
                "description": (
                    "D-7 에 준비한 퇴실 점검표로 방별 체크. "
                    "합의 내용에 양측 서명. 원상회복 기준은 대법원 판례 참고 "
                    "(5년 이상 거주 시 벽지·장판은 통상 마모)."
                ),
                "d_day_offset": 0,
                "has_legal_deadline": False,
                "method": "양측 서명 점검표 1부 보관",
                "citations": [
                    {"law_name": "민법", "article": "제615조"},
                    {"law_name": "민법", "article": "제623조"},
                ],
            },
            {
                "category": "보증금 수령 후 키 반납",
                "title": "보증금 입금 확인 후 열쇠 인계",
                "description": (
                    "원칙: 보증금 계좌 입금 확인 → 정산서 수령 → 열쇠 인계. "
                    "절대 반환 전에 열쇠 넘기지 말 것. "
                    "임대인이 '입금했다' 해도 본인 계좌 앱에서 직접 확인."
                ),
                "d_day_offset": 0,
                "has_legal_deadline": False,
                "citations": [{"law_name": "주택임대차보호법", "article": "제3조의2"}],
            },
            {
                "category": "장기수선충당금 반환",
                "title": "관리사무소에서 납부확인서 발급 → 임대인 반환",
                "description": (
                    "공동주택(아파트·오피스텔)의 장기수선충당금은 법적으로 소유자(임대인) 부담. "
                    "임차인이 관리비에 포함해 낸 금액은 퇴거 시 반환 청구 가능."
                ),
                "d_day_offset": 0,
                "has_legal_deadline": False,
                "method": "관리사무소 → 납부확인서 → 임대인 보증금에서 공제 또는 별도 입금",
                "citations": [{"law_name": "공동주택관리법", "article": "제30조"}],
            },
            {
                "category": "관리비 예치금 반환",
                "title": "관리비예치금 반환 신청",
                "description": (
                    "입주 시 선납한 관리비예치금(10~30만원)은 이사 후 1~2주 내 반환. "
                    "관리사무소에 반환 신청 → 계좌 입금."
                ),
                "d_day_offset": 7,
                "has_legal_deadline": False,
                "citations": [{"law_name": "공동주택관리법", "article": "제24조"}],
            },
        ])
        base.append({
            "category": "대항력·우선변제권 확보",
            "title": "대항력·우선변제권 확보",
            "description": "주택 인도 + 전입신고 + 확정일자 3요건을 갖추면 보증금 우선변제권이 생깁니다.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제3조의2"}],
        })

    items = base
    if req.has_pet:
        items.append({
            "category": "반려동물 주소변경",
            "title": "반려동물 등록 주소변경",
            "description": "이사 후 30일 이내 정부24 또는 시·군·구청에서 동물등록 주소변경.",
            "d_day_offset": 7,
            "has_legal_deadline": True,
            "deadline_days": 30,
            "penalty": "50만원 이하 과태료",
            "citations": [{"law_name": "동물보호법", "article": "제15조"}],
        })
    if req.has_car:
        items.append({
            "category": "자동차 주소변경",
            "title": "자동차 변경등록",
            "description": "전입신고 완료 시 대부분 자동 반영. 다른 시·도로 이사하면 별도 신청 필요.",
            "d_day_offset": 14,
            "has_legal_deadline": True,
            "deadline_days": 30,
            "citations": [{"law_name": "자동차등록령", "article": "제22조"}],
        })
        items.append({
            "category": "운전면허 주소변경",
            "title": "운전면허증 기재사항 변경",
            "description": "전입신고 시 자동 반영되는 게 원칙이지만 전산 누락이 있어 2~3주 후 safedriving.or.kr 에서 직접 확인 권장.",
            "d_day_offset": 14,
            "has_legal_deadline": True,
            "deadline_days": 30,
            "penalty": "2만원 이하 과태료",
            "citations": [{"law_name": "도로교통법", "article": "제87조"}],
        })
        items.append({
            "category": "자동차보험 주소변경",
            "title": "자동차보험 주소·차고지 변경",
            "description": "가입 보험사에 주소·차고지 변경을 알리지 않으면 사고 시 '고지의무 위반'으로 보험금 삭감 가능. 자동차 변경등록과는 별개 절차.",
            "d_day_offset": 14,
            "has_legal_deadline": False,
            "citations": [{"law_name": "상법", "article": "제652조"}],
        })
    if req.has_children:
        level = req.children_school_level or "자녀"
        items.append({
            "category": "자녀 전학",
            "title": f"{level} 전학 절차",
            "description": "전입신고 후 교육청/학교에 전학 절차 문의. 초·중등은 주민센터 전입신고 시 자동 연계.",
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "citations": [{"law_name": "초·중등교육법", "article": "제13조"}],
        })
    if req.is_foreigner:
        items.append({
            "category": "외국인등록 주소변경",
            "title": "외국인등록 주소변경 신고",
            "description": "전입 후 14일 이내 관할 출입국·외국인청에 신고.",
            "d_day_offset": 1,
            "has_legal_deadline": True,
            "deadline_days": 14,
            "citations": [{"law_name": "출입국관리법", "article": "제36조"}],
        })

    if req.is_employed:
        items.append({
            "category": "직장 주소변경 신고",
            "title": "회사 인사팀에 주소변경 신고",
            "description": (
                "재직 중이라면 회사 인사팀·인사 시스템에 주소 변경 통지. "
                "원천징수·연말정산·4대보험 주소 반영에 필요. "
                "대부분 사내 시스템에서 셀프 수정 가능."
            ),
            "d_day_offset": 3,
            "has_legal_deadline": False,
            "method": "사내 인사 시스템 또는 인사팀",
        })
    if req.receives_welfare:
        items.append({
            "category": "복지급여 주소변경",
            "title": "복지급여 주소변경",
            "description": (
                "기초생활수급자·장애인연금·아동수당·한부모가족지원 등 복지급여 수급자는 "
                "이사 시 주소 반영 확인 필수. 대부분 전입신고로 자동 연계되지만 "
                "수급자격은 관할 자치단체 심사가 필요한 경우가 있어 누락되면 급여 중단 리스크. "
                "복지로(bokjiro.go.kr) 에서 확인 권장."
            ),
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "method": "복지로(bokjiro.go.kr) 또는 읍·면·동 주민센터 (☎ 129)",
            "citations": [{"law_name": "국민기초생활보장법", "article": "제23조"}],
        })
    if req.needs_id_reissue:
        items.append({
            "category": "주민등록증 재발급",
            "title": "주민등록증 재발급",
            "description": (
                "주소 변경은 전입신고로 자동 반영되므로 재발급 의무는 없음. "
                "10년 이상 경과·분실·훼손·사진 변경 시에만 신청. "
                "수수료 5,000원, 6개월 이내 촬영 규격 사진 필요."
            ),
            "d_day_offset": 14,
            "has_legal_deadline": False,
            "method": "정부24(gov.kr) 또는 주민센터 방문",
            "citations": [{"law_name": "주민등록법", "article": "제24조"}],
        })

    if req.is_apartment:
        items.append({
            "category": "관리사무소 입주 신고",
            "title": "관리사무소 입주자 카드 작성 (아파트·오피스텔)",
            "description": (
                "입주 당일 단지 관리사무소 방문하여 입주자 카드 작성. "
                "세대주·가족 인원·연락처·차량 정보 등록. "
                "관리비 고지서·승강기 카드·입주민 앱 이용에 필요."
            ),
            "d_day_offset": 0,
            "has_legal_deadline": False,
            "method": "단지 관리사무소 방문",
        })
        items.append({
            "category": "우편함 명패 교체",
            "title": "우편함·현관 명패 교체",
            "description": (
                "이전 거주자 명의가 남아있으면 우편물 오배송·분실 리스크. "
                "관리사무소에 명패 교체 요청 또는 직접 교체."
            ),
            "d_day_offset": 3,
            "has_legal_deadline": False,
        })
        if req.has_car:
            items.append({
                "category": "단지 주차 등록",
                "title": "단지 주차 등록 (차량 보유자)",
                "description": (
                    "차량 번호·모델·사진 등록 후 입주민 주차 스티커 발급. "
                    "미등록 차량은 견인 또는 과태료 대상."
                ),
                "d_day_offset": 1,
                "has_legal_deadline": False,
                "method": "관리사무소 주차 등록 창구",
            })

    # special_concerns 기반 추가 항목
    concerns = " ".join(req.special_concerns).lower()
    if any(k in concerns for k in ["장기수선충당금", "관리비예치금", "관리비"]):
        items.append({
            "category": "관리비예치금·장기수선충당금 정산",
            "title": "관리비예치금·장기수선충당금 반환청구",
            "description": "공동주택은 이사 시 장기수선충당금을 임대인에게 돌려받을 수 있습니다.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "공동주택관리법 시행령", "article": "제31조"}],
        })
    if any(k in concerns for k in ["보증금 반환", "임차권등기", "반환 우려"]):
        items.append({
            "category": "임차권등기명령 안내",
            "title": "임차권등기명령 신청 안내",
            "description": "임대차 종료 후 보증금 미반환 시 임차권등기명령으로 대항력 유지 가능.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제3조의3"}],
        })
    if any(k in concerns for k in ["월세 인상", "증액", "증감"]):
        items.append({
            "category": "차임·보증금 증감청구 한도",
            "title": "월세/보증금 증감청구 한도 안내",
            "description": "임대인은 연 5% 초과 인상을 청구할 수 없습니다.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제7조"}],
        })
    if any(k in concerns for k in ["갱신요구", "갱신"]):
        items.append({
            "category": "임대차 갱신요구권 안내",
            "title": "임대차 갱신요구권 행사",
            "description": "임차인은 1회에 한해 2년 갱신 요구 가능. 계약 만료 6개월~2개월 전 통지.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제6조의3"}],
        })
    if any(k in concerns for k in ["하자", "수선", "수리"]):
        items.append({
            "category": "주택수리 하자 분쟁해결",
            "title": "주택수리 하자 분쟁해결 기준",
            "description": "공정거래위원회 소비자분쟁해결기준을 따라 처리.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
        })
        items.append({
            "category": "임대인 수선의무 안내",
            "title": "임대인 수선의무",
            "description": "민법상 임대인은 임대물의 사용·수익에 필요한 수선 의무가 있습니다 (통상 사용 마모 제외).",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "민법", "article": "제623조"}],
        })
    if any(k in concerns for k in ["이사업체", "이삿짐"]):
        items.append({
            "category": "이사업체 분쟁해결",
            "title": "이사업체 분쟁해결 방법",
            "description": "한국소비자원 또는 공정거래위원회를 통해 분쟁 조정 신청.",
            "d_day_offset": -3,
            "has_legal_deadline": False,
        })
    if req.deposit_krw and req.monthly_rent_krw:
        items.append({
            "category": "전월세 계약 신고 (전월세신고제)",
            "title": "전월세 계약 신고",
            "description": "보증금 6천만원 초과 또는 월세 30만원 초과 계약은 30일 이내 신고 의무.",
            "d_day_offset": 1,
            "has_legal_deadline": True,
            "deadline_days": 30,
            "citations": [{"law_name": "부동산 거래신고 등에 관한 법률", "article": "제6조의2"}],
        })

    items = [enrich(d) for d in items]
    # 지역 기반 매핑 주입 — 수도·가스·전기·통신·우편·전학 등 항목에 정확한 연락처/URL
    items = [enrich_item_with_region(d, req.region) for d in items]
    return [_item_from_dict(d, req.move_date) for d in items]


# ---------- Step 4: 날짜 정렬 + 응답 조립 ----------


def generate_checklist(req: ChecklistRequest) -> ChecklistResponse:
    queries = build_queries_llm(req)
    chunks = search_procedures(queries, req)
    items = structure_checklist_llm(req, chunks)
    items.sort(key=lambda x: x.d_day_offset)
    return ChecklistResponse(
        request=req,
        generated_at=date.today(),
        items=items,
        total_items=len(items),
        used_queries=queries,
        warning=(
            None
            if get_settings().azure_ready
            else "Azure 자격 증명이 설정되지 않아 rule-based fallback 결과입니다."
        ),
    )
