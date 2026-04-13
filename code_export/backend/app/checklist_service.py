"""POST /checklist business logic — 4-step RAG pipeline."""
from __future__ import annotations

import json
from datetime import date

from .azure_clients import get_openai_client, get_search_client_procedure
from .config import get_settings
from .date_utils import compute_deadline, compute_start_date
from .local_search import search as local_search
from .models import (
    ChecklistCitation,
    ChecklistItem,
    ChecklistRequest,
    ChecklistResponse,
)

# ---------- Step 1: 조건 → 검색 쿼리 변환 ----------

QUERY_SYSTEM_PROMPT = """당신은 한국에서 이사 관련 행정 절차를 안내하는 RAG 시스템의 쿼리 플래너입니다.
사용자의 조건을 분석하여 Azure AI Search에 던질 한국어 검색 쿼리 목록을 JSON 배열로 출력하세요.

규칙:
1. 반드시 필요한 절차(전입신고, 확정일자, 전기·수도·가스 명의변환)는 기본으로 포함
2. 사용자가 해당되지 않는 항목(예: 반려동물 없음)은 쿼리 생성 금지
3. 지역 정보가 있으면 쿼리에 시·도·구 키워드를 넣어 메타 필터에 걸리도록 할 것
4. 5~10개의 쿼리를 생성"""


def build_queries_rule_based(req: ChecklistRequest) -> list[str]:
    """Fallback query generation (Azure OpenAI 없을 때)."""
    q = ["전입신고 방법", "확정일자 신청"]
    if req.contract in ("전세", "월세"):
        q.append(f"대항력 우선변제권 {req.contract}")
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
        f"계약유형: {req.contract}\n"
        f"지역: {req.region}\n"
        f"이사일: {req.move_date.isoformat()}\n"
        f"반려동물: {req.has_pet}, 자동차: {req.has_car}, 자녀: {req.has_children}\n"
        f"외국인: {req.is_foreigner}\n"
        f"특이사항: {req.special_concerns}\n"
        "→ JSON 배열로만 응답. 예: [\"전입신고\", \"확정일자 월세\", ...]"
    )
    resp = client.chat.completions.create(
        model=settings.azure_openai_deployment_name,
        temperature=0,
        messages=[
            {"role": "system", "content": QUERY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
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

    resp = client.chat.completions.create(
        model=settings.azure_openai_deployment_name,
        temperature=0,
        messages=[
            {"role": "system", "content": STRUCTURE_SYSTEM_PROMPT},
            {"role": "user", "content": f"조건:\n{req.model_dump_json()}\n\n검색결과:\n{context}"},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or '{"items": []}'
    try:
        parsed = json.loads(raw)
        items_data = parsed.get("items", parsed if isinstance(parsed, list) else [])
        items = []
        for d in items_data:
            items.append(_item_from_dict(d, req.move_date))
        return items
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"structure_checklist_llm parse error: {exc}")
        return structure_checklist_fallback(req)


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
        citations=[ChecklistCitation(**c) for c in d.get("citations", [])],
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
    ]

    # 임차인 보호: 전세/월세일 때만 확정일자·대항력 추가 (자가 제외)
    if req.contract in ("전세", "월세"):
        base.insert(1, {
            "category": "확정일자/임차권",
            "title": "확정일자 취득",
            "description": "보증금 보호를 위해 전입신고 당일 확정일자를 받아두세요.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "method": "주민센터 방문 또는 인터넷등기소",
            "citations": [{"law_name": "주택임대차보호법", "article": "제3조의2"}],
        })
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
