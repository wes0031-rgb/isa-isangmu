"""POST /checklist business logic — 4-step RAG pipeline."""
from __future__ import annotations

import json
from datetime import date

from .azure_clients import get_openai_client
from .config import get_settings
from .date_utils import compute_deadline, compute_start_date
from .local_search import find_law_article
from .local_search import search as local_search
from .search_service import (
    DEFAULT_TOP_GUIDE_CHECKLIST,
    DEFAULT_TOP_LAW_CHECKLIST,
    embed_queries_batch,
    parallel_search_law_guide,
)
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
    """정형 토글 → 정적 쿼리 매핑.

    설계 원칙: 토글은 모두 정해진 옵션의 boolean 조합이므로 LLM 으로
    쿼리 생성할 필요가 없음 (deterministic 함수로 충분). LLM 호출 0회.
    자유 텍스트 (req.free_text) 가 있으면 build_queries_freetext_llm 으로
    별도 처리해서 결과에 합침 (generate_checklist 참조).
    """
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
        q.append("운전면허 주소변경")
        q.append("자동차보험 주소변경")
    if req.has_children and req.children_school_level:
        q.append(f"자녀 {req.children_school_level} 전학")
    if req.is_foreigner:
        q.append("외국인등록 주소변경")
    if getattr(req, "is_employed", False):
        q.append("직장 인사팀 주소변경")
    if getattr(req, "needs_id_reissue", False):
        q.append("주민등록증 재발급")
    if getattr(req, "receives_welfare", False):
        q.append("복지급여 수급자 주소변경")
    if getattr(req, "is_apartment", False):
        q.append("아파트 관리실 이사 통보")
    # special_concerns 의 토글 값들 → 정적 쿼리 매핑
    _CONCERN_QUERIES = {
        "학생": ["재학증명서 주소변경", "학자금대출 주소변경"],
        "병역 대상자": ["병무청 거주지 신고", "병적기록 주소변경"],
        "고층 이사 (엘베·곤도라)": ["엘리베이터 사용 예약", "사다리차·곤도라 예약"],
        "대형 폐기물 배출": ["대형폐기물 신고필증 발급"],
        "인터넷 이전": ["통신사 인터넷 이전 접수"],
        "TV 이전": ["IPTV 이전 설치", "TV 수신료 주소변경"],
        "보증금 반환": ["임차권등기명령 신청", "전세보증금 반환 분쟁"],
    }
    for concern in req.special_concerns or []:
        q.extend(_CONCERN_QUERIES.get(concern, [concern]))
    return q


def build_queries_freetext_llm(req: ChecklistRequest) -> list[str]:
    """자유 텍스트 (req.free_text) → 추가 검색 쿼리.

    토글로 못 잡는 엣지케이스 전담 (예: '해외 귀국', '전세금 미반환',
    '신축 입주 하자 점검'). free_text 가 비어있으면 호출하지 않는 게 호출자 책임.
    실패 시 빈 list 반환 (정적 쿼리만 사용).
    """
    text = (req.free_text or "").strip()
    if not text:
        return []
    client = get_openai_client()
    if client is None:
        return []
    settings = get_settings()
    user_prompt = (
        "사용자가 이사 관련 자유 텍스트로 적은 특이사항입니다. "
        "이걸 처리하려면 어떤 행정 절차·법령이 추가로 필요한지, "
        "AI Search 인덱스에서 검색할 짧은 한국어 쿼리 3~6개로 변환하세요. "
        "토글로 이미 처리되는 건(전입신고·확정일자·반려동물·자동차·외국인·전기수도가스 등)은 "
        "중복 생성 금지.\n\n"
        f"세대유형: {req.household}\n"
        f"계약유형: {', '.join(_effective_contracts(req))}\n"
        f"지역: {req.region}\n"
        f"자유 텍스트: {text}\n"
        "→ JSON 배열로만 응답. 예: {\"queries\": [\"임차권등기명령 신청\", \"전세보증금 반환 소송\"]}"
    )
    try:
        # max_retries=0: SDK 기본 2회 재시도 X → 총 대기시간 = timeout 그대로.
        # 재시도해도 쿼터 초과 같은 영구 오류는 안 풀리고, 대기시간만 3배로 늘어남.
        resp = client.with_options(max_retries=0).chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=0,
            seed=42,
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
            f"freetext LLM failed ({type(exc).__name__}): {exc} — skipping"
        )
        return []
    raw = resp.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "queries" in parsed:
            return [str(q) for q in parsed["queries"] if isinstance(q, (str, int, float))]
        if isinstance(parsed, list):
            return [str(q) for q in parsed if isinstance(q, (str, int, float))]
    except json.JSONDecodeError:
        pass
    return []


# ---------- Step 2: AI Search 하이브리드 검색 ----------


def search_procedures(queries: list[str], req: ChecklistRequest) -> list[dict]:
    """3-index 하이브리드 검색 (law + guide 병렬) — 최적화 버전.

    최적화 2종:
    1. 임베딩 batch — N 쿼리를 한 번의 OpenAI embeddings API 호출로 (N→1)
    2. 쿼리 병렬 — ThreadPoolExecutor 로 모든 쿼리를 동시에 Azure Search 에 쏨

    결과는 id dedupe 해서 합치고, `_source_type` 태그(law/guide) 를
    structure_checklist_llm 의 context 포맷 분기에 활용.

    law 결과 없이 guide 만으로는 LLM 이 자동차관리법 제11조 같은 가짜 조항을
    환각하는 현상이 세션 5 에 실증됨 → law 병렬 필수.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import logging as _log
    _logger = _log.getLogger("movewise")

    if not queries:
        return []

    # 1) 임베딩 batch — 실패 시 [None]*N 반환. 각 쿼리는 semantic-only 로 fallback.
    embeddings = embed_queries_batch(queries)

    # 2) 쿼리 병렬 실행 — 각 쿼리에 embedding 주입하여 재계산 방지.
    def _run_one(q: str, emb) -> tuple[str, list[dict], list[dict]]:
        try:
            law_hits, guide_hits = parallel_search_law_guide(
                q,
                top_law=DEFAULT_TOP_LAW_CHECKLIST,
                top_guide=DEFAULT_TOP_GUIDE_CHECKLIST,
                embedding=emb,
            )
            return (q, law_hits, guide_hits)
        except Exception as exc:
            _logger.warning(
                f"search_procedures: query '{q}' failed ({type(exc).__name__}: {exc})"
            )
            return (q, [], [])

    results_per_query: list[tuple[str, list[dict], list[dict]]] = []
    # Azure Search Semantic Ranker 는 동시 호출 수에 민감 (8개 동시 던지면
    # CapacityOverloaded → Partial Content 반환). 4개로 제한하면 체감 속도는
    # 여전히 빠르고 (순차 대비 3-4배 개선), quota 초과 위험 회피.
    max_workers = min(len(queries), 4)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_query = {
            pool.submit(_run_one, q, emb): q
            for q, emb in zip(queries, embeddings)
        }
        for future in as_completed(future_to_query):
            results_per_query.append(future.result())

    # 3) 원래 쿼리 순서대로 다시 정렬 (as_completed 는 완료 순 반환 → dedup 순서 유지)
    query_order = {q: i for i, q in enumerate(queries)}
    results_per_query.sort(key=lambda t: query_order.get(t[0], 99))

    # 4) id dedupe + _source_type 태그 주입
    seen_ids: set[str] = set()
    merged: list[dict] = []
    law_count = 0
    guide_count = 0

    for _q, law_hits, guide_hits in results_per_query:
        for hit in law_hits:
            hit_id = hit.get("id")
            if not hit_id or hit_id in seen_ids:
                continue
            seen_ids.add(hit_id)
            hit["_source_type"] = "law"
            merged.append(hit)
            law_count += 1
        for hit in guide_hits:
            hit_id = hit.get("id")
            if not hit_id or hit_id in seen_ids:
                continue
            seen_ids.add(hit_id)
            hit["_source_type"] = "guide"
            merged.append(hit)
            guide_count += 1

    _logger.info(
        f"search_procedures: queries={len(queries)} workers={max_workers} "
        f"merged={len(merged)} (law={law_count} guide={guide_count}) "
        f"embeddings={'batch' if any(e is not None for e in embeddings) else 'none'}"
    )
    if not merged:
        _logger.warning(
            "search_procedures: 0 hits from Azure — falling back to local_search"
        )
        return local_search(queries, top_k_per_query=3)
    return merged


# ---------- Step 3: LLM 체크리스트 구조화 ----------

STRUCTURE_SYSTEM_PROMPT = """당신은 이사 전·당일·후의 행정 절차 체크리스트 생성기입니다.
주어진 검색 결과(chunks)를 근거로 사용자 조건에 맞는 체크리스트 항목을 JSON으로 출력하세요.

검색 결과 포맷:
- [law | ID] 태그: 법령 조문 원문. law_name·article 필드가 있음.
- [guide | ID] 태그: 행정 절차 해설. breadcrumb·related_laws 필드가 있음.

각 항목의 필수 필드:
- category: "전입신고" 같은 한글 카테고리
- title: 사용자에게 보일 제목
- description: 2~3문장 요약
- d_day_offset: **이사일 기준 시작일 정수**. 음수=이사 전(준비·예약·포장), 0=이사 당일, 양수=이사 후(신고·등록).
- has_legal_deadline: 법정 기한 여부
- deadline_days: 기한이 있으면 일수, 없으면 null
- method: "정부24 온라인 또는 주민센터 방문"
- contact: 연락처 (있으면)
- citations: [{"law_name":"주민등록법","article":"제16조"}]

**Anti-hallucination 절대 규칙 (위반 시 항목 폐기):**
1. citations 의 law_name·article 은 반드시 [law | ...] 태그가 붙은 검색 결과의
   law_name·article 필드 조합을 **그대로** 사용할 것. guide 청크의 related_laws
   문자열("주택임대차보호법 제3조의2")도 근거로 사용 가능.
2. 검색 결과에 없는 법·조항을 상상해서 citations 에 넣는 것 절대 금지.
   예: "자동차관리법 제11조" 같은 존재하지 않는 조항 환각 금지.
3. 사용자 조건에서 false 인 항목은 체크리스트에 포함 금지.
   - has_car=false → 자동차/운전면허/자동차보험 항목 0개
   - has_pet=false → 반려동물 항목 0개
   - has_children=false → 전학 항목 0개
   - is_foreigner=false → 외국인등록 항목 0개
4. 확신 없는 법정 기한·과태료는 has_legal_deadline=false 로 두고 숫자를 지어내지 말 것.

**커버리지 규칙 (빠뜨리지 말 것):**
- 검색 결과에 등장한 **실질 행정·법적 의무와 생활 행정 절차는 빠뜨리지 말고 항목화**.
  예: 전입신고, 확정일자, 임대차 신고, 주소이전(우편·운전면허·건강보험·국민연금·주민등록증 재발급·은행·카드), 공과금 명의변경(전기·수도·도시가스), 인터넷·TV 이전, 쓰레기 종량제봉투·분리배출, 도어락 교체, 보증금 반환, 주택임대차 분쟁해결, 소방안전·가스점검 등.
- 사용자 조건(has_pet/has_car/has_children/is_foreigner/contracts)에 **해당되는** 항목은 검색결과에 있으면 모두 포함.
- 서로 **포괄관계** 인 항목만 병합 (예: "공과금 정산" 하나로 뭉치지 말고 전기·수도·가스 각각 분리). 거의 동일한 내용은 1개로 통합.
- 최소 권장 분량: **15~25개**. 사용자 조건이 많으면 (자취 + 전세 + 반려동물 + 자녀 등) 30+ 개까지 OK.

**d_day_offset 절대 규칙 (매우 중요):**
- 항목 성격에 맞게 **반드시 서로 다른 값**으로 분산. 모든 항목에 0을 넣는 것은 금지.
- 체크리스트는 "이사 전 준비 → 당일 → 이사 후 정리" 타임라인이 드러나야 합니다.
- 권장 매핑 (없는 항목은 상식적으로 추정):
  · 이사업체 계약·예약: -30 ~ -21
  · 짐 포장·정리 시작: -14 ~ -7
  · 우편물 주소이전 신청: -7
  · 인터넷·TV 이전 설치 예약: -7 ~ -3
  · 이사 전 체크리스트(청소 등): -3 ~ -1
  · 전기·수도·도시가스 명의변경 / 이사 당일 작업: 0
  · 전입신고: +1 (늦어도 +14 이내, 법정 14일)
  · 확정일자 받기: +1 (전입신고와 함께)
  · 자동차 변경등록: +14 ~ +20 (법정 30일)
  · 반려동물 등록 주소변경: +7 ~ +15 (법정 30일)
  · 자녀 전학 신청: +1 ~ +3
  · 운전면허 주소변경·건강보험·국민연금: +7 ~ +14

검색 결과의 content 에 있는 내용만 근거로 사용. 없는 정보는 만들지 말 것."""


def structure_checklist_llm(
    req: ChecklistRequest, chunks: list[dict]
) -> tuple[list[ChecklistItem], bool]:
    client = get_openai_client()
    if client is None:
        # 폴백도 검색된 청크의 메타데이터를 활용
        return structure_checklist_fallback(req, chunks), True

    settings = get_settings()

    def _format_chunk(c: dict) -> str:
        source = c.get("_source_type") or "guide"
        cid = c.get("id", "?")
        content = (c.get("content") or "")[:600]
        if source == "law":
            return (
                f"[law | {cid}]\n"
                f"law: {c.get('law_name','')} {c.get('article','')}\n"
                f"title: {c.get('title','')}\n"
                f"keywords: {c.get('keywords', [])}\n"
                f"deadlines: {c.get('deadlines', [])}\n"
                f"content: {content}"
            )
        return (
            f"[guide | {cid}]\n"
            f"breadcrumb: {c.get('breadcrumb','')}\n"
            f"related_laws: {c.get('related_laws', [])}\n"
            f"deadlines: {c.get('deadlines', [])}\n"
            f"content: {content}"
        )

    # 청크 24→16 — 입력 토큰 33%↓ → LLM 응답 시간 비례 감소.
    # 16개도 _ensure_utility/_ensure_conditional 후처리로 누락 항목 보강되어 안전.
    context = "\n\n---\n\n".join(_format_chunk(c) for c in chunks[:16])

    import logging as _log
    _logger = _log.getLogger("movewise")
    try:
        # max_retries=0: SDK 기본 2회 재시도 X → 총 대기시간 = timeout 그대로.
        # 재시도 2회 시 최악 20s * 3 = 60s → 프론트 45s 초과.
        # 결정론 완전 잠금 — temp=0 / seed=42 만으로는 Azure OpenAI 가 best-effort.
        # top_p·frequency/presence_penalty 까지 default 고정해서 호출마다 미세 변동 최소화.
        resp = client.with_options(max_retries=0).chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=0,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            seed=42,
            messages=[
                {"role": "system", "content": STRUCTURE_SYSTEM_PROMPT},
                {"role": "user", "content": f"조건:\n{req.model_dump_json()}\n\n검색결과:\n{context}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=3000,
            timeout=20,
        )
    except Exception as exc:
        _logger.warning(
            f"structure LLM failed ({type(exc).__name__}): {exc} — falling back"
        )
        return structure_checklist_fallback(req, chunks), True

    raw = resp.choices[0].message.content or '{"items": []}'
    try:
        parsed = json.loads(raw)
        items_data: list = []
        if isinstance(parsed, list):
            items_data = parsed
        elif isinstance(parsed, dict):
            for key in ("items", "checklist", "체크리스트", "procedures", "결과"):
                v = parsed.get(key)
                if isinstance(v, list):
                    items_data = v
                    break
            if not items_data:
                # 최후: dict 안에서 첫 list 값을 사용
                for v in parsed.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        items_data = v
                        break
        items: list[ChecklistItem] = []
        for d in items_data:
            if not isinstance(d, dict):
                continue
            try:
                items.append(_item_from_dict(d, req.move_date))
            except Exception as exc:
                _logger.warning(
                    f"_item_from_dict failed on {d.get('title', d)}: {type(exc).__name__}: {exc}"
                )
        _logger.info(
            f"structure_checklist_llm: chunks={len(chunks)} parsed_items={len(items_data)} built_items={len(items)}"
        )
        if not items:
            _logger.warning(
                f"structure LLM 0 items (parsed type={type(parsed).__name__}, keys={list(parsed.keys()) if isinstance(parsed, dict) else 'list'}) — falling back"
            )
            return structure_checklist_fallback(req, chunks), True
        return items, False
    except (json.JSONDecodeError, ValueError) as exc:
        _logger.warning(f"structure LLM parse error: {exc} — falling back")
        return structure_checklist_fallback(req, chunks), True


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
        # "이사업체 피해예방" 은 moving_style != "self" 조건부로 items = base 이후
        # 분기에서 주입 (셀프 이사 시 무의미한 항목 노이즈 제거).
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
        # 은행 / 카드사 주소변경 은 _CONDITIONAL_REQUIRED 의 canonical 2개로 분리 주입됨.
        # base 에 "금융기관 주소변경(은행·카드사)" 뭉친 항목을 두면 alias rename 으로
        # "카드사 주소변경 / title: 은행·카드사 주소변경" 같은 title 불일치가 발생 → 제거.
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
            # "장기수선충당금 반환청구" / "관리비 정산" 은 _CONDITIONAL_REQUIRED 에서
            # canonical 로 통합 주입. 여기 중복으로 두지 않음 (유사 항목 3중 중복 방지).
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
    # 이사업체 피해예방 — 셀프 이사(moving_style="self")는 업체 미사용이라 제외.
    # CONDITIONAL_REQUIRED 의 동명 canonical 과 조건 정합 유지.
    if (getattr(req, "moving_style", "company") or "company") != "self":
        items.append({
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
        })
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
    # (관리비/장기수선충당금 concerns 기반 항목 제거 — _CONDITIONAL_REQUIRED 의
    #  "장기수선충당금 반환청구" + "관리비 정산" canonical 2개가 contract=전세/월세 조건으로
    #  자동 주입됨. 중복 제거 및 title 일관성 확보.)
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


# ---------- Utility split post-processing ----------
#
# LLM 이 전기·수도·도시가스 명의변환을 한 항목("공과금 정산") 으로 묶는 경향이 강해서
# golden 평가 recall 이 크게 손해본다 (30 쿼리 중 도시가스 25회·전기 21회·수도 13회 누락).
# 실제 사용자 UX 에서도 3종이 각각 연락처·절차가 달라 분리 표시가 자연스럽다.
# 후처리로 (a) 뭉친 공과금 항목 드롭 → (b) 없는 3종 개별 항목 주입.

_UTILITY_TYPES = (
    ("전기 명의변환", ("전기", "한전")),
    ("수도 명의변환", ("수도", "상수도")),
    ("도시가스 명의변환", ("가스", "도시가스")),
)

_UTILITY_FALLBACK_DICT: dict[str, dict] = {
    "전기 명의변환": {
        "category": "전기 명의변환",
        "title": "전기 명의변경",
        "description": "한전 앱 또는 ☎ 123 에서 명의변경 신청. 이사 당일 계량기 지침수 확인 후 처리.",
        "d_day_offset": 0,
        "has_legal_deadline": False,
        "method": "한전 앱 · ☎ 123",
        "contact": "한전 123",
    },
    "수도 명의변환": {
        "category": "수도 명의변환",
        "title": "수도 명의변경",
        "description": "관할 수도사업소에 명의변경 신청 (전입신고와 별개 절차).",
        "d_day_offset": 0,
        "has_legal_deadline": False,
        "method": "지역 수도사업소 전화 또는 온라인",
    },
    "도시가스 명의변환": {
        "category": "도시가스 명의변환",
        "title": "도시가스 명의변경",
        "description": "지역 도시가스 공급사 고객센터에 명의변경 신청. 이사 당일 계량기 점검 필요할 수 있음.",
        "d_day_offset": 0,
        "has_legal_deadline": False,
        "method": "지역 도시가스 공급사 고객센터",
    },
}


def _ensure_utility_items(
    items: list[ChecklistItem], req: ChecklistRequest
) -> list[ChecklistItem]:
    """전기·수도·가스 3종 명의변환 항목이 각각 단독으로 존재하도록 보정."""

    def _hit_types(text: str) -> set[str]:
        hit = set()
        for name, kws in _UTILITY_TYPES:
            if any(kw in text for kw in kws):
                hit.add(name)
        return hit

    # 1) 2종 이상 섞여 있는 공과금 뭉침 항목 제거
    filtered: list[ChecklistItem] = []
    for it in items:
        hay = f"{it.category} {it.title} {it.description or ''}"
        if len(_hit_types(hay)) >= 2:
            continue
        filtered.append(it)

    # 2) 단독 존재 여부 확인 → 누락된 3종 주입
    present: set[str] = set()
    for it in filtered:
        hay = f"{it.category} {it.title}"
        for name, kws in _UTILITY_TYPES:
            if any(kw in hay for kw in kws):
                present.add(name)

    for name, _ in _UTILITY_TYPES:
        if name in present:
            continue
        raw = _UTILITY_FALLBACK_DICT[name]
        raw = enrich_item_with_region(dict(raw), req.region)
        filtered.append(_item_from_dict(raw, req.move_date))

    return filtered


# ---------- Conditional required-items post-processing ----------
#
# v1 평가(hardcoded 전) 30건 missing Top: 도시가스25·전기21·수도13·반려동물7·인터넷5·
# 외국인등록3·대항력/우선변제권3·임차권등기2. utility 3종은 위에서 처리. 아래는 나머지.
# 원칙: (a) 조건 함수 true → 키워드로 기존 item 스캔 → 없으면 주입.
# 각 항목 fallback 정의는 structure_checklist_fallback 의 대응 블록과 의도적으로 일치.

_CONDITIONAL_REQUIRED: list[tuple] = [
    # (조건 함수, 키워드 alias, fallback item dict)
    (
        lambda req: True,  # 인터넷은 거의 모든 이사에 필수
        ("인터넷", "KT", "SKB", "SK브로드", "LG U+"),
        {
            "category": "인터넷 이전 설치",
            "title": "인터넷·TV 이전 설치",
            "description": "KT(100), SK브로드밴드(106), LG U+(101) 이전 신청.",
            "d_day_offset": -7,
            "has_legal_deadline": False,
        },
    ),
    (
        lambda req: True,
        ("우편물", "우체국 주소", "epost"),
        {
            "category": "우편물 주소이전",
            "title": "우체국 주소이전 서비스",
            "description": "service.epost.go.kr 에서 주소이전 서비스 신청. 유효기간 3개월.",
            "d_day_offset": 3,
            "has_legal_deadline": False,
        },
    ),
    (
        lambda req: True,
        ("건강보험",),
        {
            "category": "건강보험 주소변경",
            "title": "건강보험 주소변경 (국민건강보험공단)",
            "description": (
                "전입신고 시 주민등록 주소가 자동 연계되는 게 원칙이지만, "
                "직장가입자는 사업장 4대 보험 주소 변경이 별도라 누락 사례가 있음. "
                "보험증·고지서·건강검진 안내 우편물 수령에 영향."
            ),
            "method": "The건강보험 앱 / 1577-1000 / www.nhis.or.kr 마이페이지",
            "contact": "1577-1000",
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "citations": [{"law_name": "국민건강보험법", "article": "제8조"}],
        },
    ),
    (
        lambda req: True,
        ("은행 주소", "주거래 은행", "은행 주거래"),
        {
            "category": "은행 주소변경",
            "title": "은행 주소변경 (주거래·전체)",
            "description": (
                "통장·체크카드·인증서·중요거래 통지 우편물 수령에 영향. "
                "자금세탁방지법(특정금융정보법)상 금융사는 주소 등 고객정보를 정기 갱신할 의무가 있어, "
                "장기 미갱신 시 일부 거래 제한될 수 있음."
            ),
            "method": "각 은행 모바일 앱 → 마이페이지 → 개인정보 수정. 공동인증서·OTP 필요.",
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "citations": [
                {"law_name": "특정 금융거래정보의 보고 및 이용 등에 관한 법률", "article": "제5조의2"}
            ],
        },
    ),
    (
        lambda req: True,
        ("카드사", "카드 주소", "신용카드 주소"),
        {
            "category": "카드사 주소변경",
            "title": "카드사 주소변경 (신용·체크 전부)",
            "description": (
                "월별 청구서·재발급 카드·하이패스·교통카드·연말정산 자료 등 "
                "카드사 우편물이 모두 신주소로 가도록 변경. 사용 중인 카드사 모두 개별 신청 필요."
            ),
            "method": "각 카드사 모바일 앱 → 회원정보 → 주소변경. 또는 카드사 고객센터.",
            "d_day_offset": 7,
            "has_legal_deadline": False,
        },
    ),
    (
        # 2026-04-22 옵션화 — 보험 가입 없는 사람 있으므로 체크박스로 이동
        lambda req: "보험 가입 있음 (생명·손해·실손)" in (req.special_concerns or []),
        ("보험사 주소", "보험 주소", "생명보험", "손해보험"),
        {
            "category": "보험사 주소변경",
            "title": "보험사 주소변경 (생명·손해·실손)",
            "description": (
                "보험증권 재발행·만기·해지환급금 안내·연말정산 자료 등 우편물 수령에 영향. "
                "자동차보험은 별도 항목(차고지 변경)이라 따로 신청. 가입 보험사 모두 개별 신청."
            ),
            "method": "각 보험사 앱 / 고객센터 / 설계사 통해 주소변경 요청.",
            "d_day_offset": 14,
            "has_legal_deadline": False,
        },
    ),
    (
        lambda req: True,
        ("통신사 주소", "휴대폰 주소", "이동통신 주소"),
        {
            "category": "통신사 주소변경",
            "title": "휴대폰 통신사 주소변경 (요금청구지)",
            "description": (
                "휴대폰 요금 청구서·USIM 재발급·기기변경 안내 등 우편물 수령에 영향. "
                "인터넷 회선 이전과는 별개 절차. SKT·KT·LGU+ 모두 개별 신청."
            ),
            "method": "T world / KT 마이케이티 / U+ 모바일 앱 → 회원정보 → 주소변경. 또는 114.",
            "contact": "SKT 114 / KT 100 / LGU+ 101",
            "d_day_offset": 7,
            "has_legal_deadline": False,
        },
    ),
    # ===== 사용자 피드백 반영 누락 6종 (2026-04-21) =====
    (
        # 전세만 — HUG 안심전세보증·SGI 전세금보장신용보험 모두 전세 전용 상품.
        # 월세 임차인에게 뜨면 무관한 항목이라 사용자 혼선 → 조건 좁힘.
        lambda req: "전세" in (req.contracts or [req.contract]),
        ("전세보증보험", "보증보험", "안심전세", "HUG", "SGI"),
        {
            "category": "전세보증보험 가입 검토",
            "title": "전세보증보험 가입 (HUG / SGI)",
            "description": (
                "HUG 안심전세보증(www.khug.or.kr) 또는 SGI 전세금보장신용보험(www.sgic.co.kr) 가입 가능 여부 검토. "
                "보증금이 시세의 90% 이하 + 등기부 깨끗(경매·신탁·다수 가압류 없음) 등 조건 충족 시 가입 가능. "
                "보증료 연 0.122~0.154%. 가입하면 임대인이 보증금을 못 돌려줘도 보증사가 대신 지급."
            ),
            "method": "HUG 안심전세 앱 또는 SGI 모바일에서 가입 신청. 잔금일 직후 신청 가능.",
            "contact": "HUG 1566-9009 / SGI 1670-7000",
            "d_day_offset": -3,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택도시기금법", "article": "제26조"}],
        },
    ),
    (
        # 2026-04-22 옵션화 — 풀옵션 원룸 이사는 불필요하므로 체크박스로 이동
        lambda req: "가전 설치 필요 (에어컨·세탁기·정수기 등)" in (req.special_concerns or []),
        ("에어컨", "세탁기", "가전 설치", "가전설치", "정수기 이전"),
        {
            "category": "가전 설치 업체 예약",
            "title": "에어컨·세탁기·정수기 등 설치 예약",
            "description": (
                "에어컨 이전 설치(제조사 또는 사설업체), 세탁기·건조기 호스 연결, 정수기 이전 설치 등 "
                "자가 설치 어려운 가전은 별도 업체 예약 필요. 이사 1주일 전 예약 권장."
            ),
            "method": "제조사 고객센터(LG 1544-7777, 삼성 1588-3366) 또는 설치전문 사설업체.",
            "d_day_offset": -7,
            "has_legal_deadline": False,
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("시설물 점검", "결로", "곰팡이", "파손 확인", "파손확인", "입주 점검", "입주점검"),
        {
            "category": "입주 시 시설물 점검",
            "title": "시설물 파손·결로·곰팡이 확인 (사진 필수)",
            "description": (
                "입주 당일 모든 방·욕실·주방 시설물을 사진/동영상으로 기록. "
                "결로·곰팡이·도배·바닥·문·창문·벽지·싱크대 등 파손 부분을 임대인에게 즉시 통지하지 않으면 "
                "퇴거 시 보증금 차감 분쟁 발생 가능. 민법 제623조(임대인 수선의무) 근거."
            ),
            "method": "체크리스트 작성 + 사진/동영상 보관 + 임대인에게 카톡/문자로 즉시 공유. 필요 시 부동산 중개인 입회.",
            "d_day_offset": 0,
            "has_legal_deadline": False,
            "citations": [{"law_name": "민법", "article": "제623조"}],
        },
    ),
    (
        # 자녀 학원 — 자녀 있을 때만. 학교는 "학교 학적 주소변경"(학생 본인)
        # + "자녀 전학"(has_children) canonical 이 이미 커버.
        lambda req: bool(getattr(req, "has_children", False)),
        ("학원 주소", "자녀 학원", "다니던 학원"),
        {
            "category": "자녀 학원 주소 확인",
            "title": "자녀 학원 등록 주소 확인",
            "description": (
                "주민등록 자동 연계가 안 되는 학원은 별도 신청 필요. "
                "다니던 학원·피아노·미술·태권도 등 회원 정보 주소 갱신."
            ),
            "method": "학원 직접 방문 또는 전화로 주소 변경 요청.",
            "d_day_offset": 14,
            "has_legal_deadline": False,
        },
    ),
    (
        # 병원 주소 확인 — 모두 공통. 단골 병원·치과 진료카드 주소 갱신.
        # 건강보험 주소변경(전입신고 자동연계) 과는 별도 — 각 병원 진료 기록은 수동.
        lambda req: True,
        ("병원 주소", "단골 병원", "진료카드", "치과 주소"),
        {
            "category": "병원 주소 확인",
            "title": "단골 병원·치과 진료카드 주소 확인",
            "description": (
                "주민등록 자동 연계가 안 되는 단골 병원·치과·영상의학과 등 "
                "진료카드 주소는 별도 신청. 건강보험 주소는 별도 항목으로 자동 반영."
            ),
            "method": "해당 병원 직접 방문 또는 전화로 주소 변경 요청.",
            "d_day_offset": 14,
            "has_legal_deadline": False,
        },
    ),
    (
        lambda req: bool(getattr(req, "is_employed", False)),
        ("직장 주소", "회사 주소", "인사팀", "4대보험 주소"),
        {
            "category": "직장 주소변경 신고",
            "title": "회사 인사팀에 주소변경 신고",
            "description": (
                "연말정산·주민세·교통비 정산 등에 영향. "
                "4대보험(건강·국민연금·고용·산재)은 회사가 자동 신고하지만 직원이 인사팀에 알려야 처리됨. "
                "원천징수영수증·재직증명서 발급지도 신주소로 변경됨."
            ),
            "method": "회사 인사팀에 주소변경 신청서 제출 또는 사내 인사 시스템에서 직접 수정.",
            "d_day_offset": 7,
            "has_legal_deadline": False,
        },
    ),
    (
        # 2026-04-22 옵션화 — 온라인 쇼핑 안 쓰는 사람 있으므로 체크박스로 이동
        lambda req: "온라인 쇼핑·배달앱 이용" in (req.special_concerns or []),
        ("쇼핑몰", "배달앱", "배송 주소", "배송주소", "쿠팡", "배민"),
        {
            "category": "쇼핑몰·배달앱 배송 주소 수정",
            "title": "쇼핑몰·배달앱 배송 주소 일괄 수정",
            "description": (
                "쿠팡·네이버·G마켓·11번가·SSG·올리브영 등 쇼핑몰, "
                "배민·요기요·쿠팡이츠 등 배달앱의 기본 배송지 변경. "
                "잘못된 주소로 배송돼서 분실되거나 이전 거주자에게 가는 사고 방지."
            ),
            "method": "각 앱 → 마이페이지 → 배송지 관리 → 기본 배송지 변경. 신주소 등록 + 구주소 삭제.",
            "d_day_offset": 3,
            "has_legal_deadline": False,
        },
    ),
    (
        lambda req: req.has_pet,
        ("반려동물", "동물등록"),
        {
            "category": "반려동물 등록 주소변경",
            "title": "반려동물 등록 주소변경",
            "description": "이사 후 30일 이내 정부24 또는 시·군·구청에서 동물등록 주소변경.",
            "d_day_offset": 7,
            "has_legal_deadline": True,
            "deadline_days": 30,
            "penalty": "50만원 이하 과태료",
            "citations": [{"law_name": "동물보호법", "article": "제15조"}],
        },
    ),
    (
        lambda req: req.has_car,
        ("자동차 변경", "자동차 주소", "자동차등록"),
        {
            "category": "자동차 변경등록",
            "title": "자동차 변경등록",
            "description": "전입신고 시 대부분 자동 반영. 다른 시·도로 이사하면 별도 신청 필요.",
            "d_day_offset": 14,
            "has_legal_deadline": True,
            "deadline_days": 30,
            "citations": [{"law_name": "자동차등록령", "article": "제22조"}],
        },
    ),
    (
        lambda req: req.has_car,
        ("운전면허",),
        {
            "category": "운전면허 주소변경",
            "title": "운전면허증 기재사항 변경",
            "description": "전입신고 시 자동 반영되는 게 원칙이지만 전산 누락이 있어 safedriving.or.kr 에서 직접 확인 권장.",
            "d_day_offset": 14,
            "has_legal_deadline": True,
            "deadline_days": 30,
            "penalty": "2만원 이하 과태료",
            "citations": [{"law_name": "도로교통법", "article": "제87조"}],
        },
    ),
    (
        lambda req: req.has_car,
        ("자동차보험",),
        {
            "category": "자동차보험 주소변경",
            "title": "자동차보험 주소·차고지 변경",
            "description": "가입 보험사에 주소·차고지 변경을 알리지 않으면 사고 시 '고지의무 위반'으로 보험금 삭감 가능.",
            "d_day_offset": 14,
            "has_legal_deadline": False,
            "citations": [{"law_name": "상법", "article": "제652조"}],
        },
    ),
    (
        lambda req: req.has_children,
        ("전학",),
        {
            "category": "자녀 전학",
            "title": "자녀 전학 절차",
            "description": "전입신고 후 교육청/학교에 전학 절차 문의. 초·중등은 주민센터 전입신고 시 자동 연계.",
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "citations": [{"law_name": "초·중등교육법", "article": "제13조"}],
        },
    ),
    (
        lambda req: req.is_foreigner,
        ("외국인등록",),
        {
            "category": "외국인등록 주소변경",
            "title": "외국인등록 주소변경 신고",
            "description": "전입 후 14일 이내 관할 출입국·외국인청에 신고.",
            "d_day_offset": 1,
            "has_legal_deadline": True,
            "deadline_days": 14,
            "citations": [{"law_name": "출입국관리법", "article": "제36조"}],
        },
    ),
    # 한국인 귀국자 4종 — 외국인과 별개 (is_returning_from_abroad 트리거)
    (
        lambda req: getattr(req, "is_returning_from_abroad", False),
        ("재외국민 거소", "재외국민 신고"),
        {
            "category": "재외국민 거소신고",
            "title": "재외국민 국내거소신고 (장기 해외체류 후 귀국 시)",
            "description": (
                "30일 이상 해외 체류 후 귀국하여 국내 거주 시 관할 출입국·외국인관서 또는 정부24에서 "
                "국내거소신고. 신고 후 거소신고증 발급. 본인 확인·금융·통신 개설에 활용 가능."
            ),
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "method": "정부24 또는 출입국·외국인청 방문",
            "citations": [{"law_name": "재외동포의 출입국과 법적 지위에 관한 법률", "article": "제6조"}],
        },
    ),
    (
        lambda req: getattr(req, "is_returning_from_abroad", False),
        ("외국 운전면허", "외국면허 인정"),
        {
            "category": "외국 운전면허 한국 인정",
            "title": "외국 운전면허 → 한국 면허 인정 신청",
            "description": (
                "한국이 인정하는 국가의 운전면허는 적성검사 후 한국 면허로 갱신 가능 (필기·실기 면제). "
                "운전면허시험장 또는 안전운전 통합민원에서 신청. 미인정 국가면 신규 취득 절차."
            ),
            "d_day_offset": 14,
            "has_legal_deadline": False,
            "method": "도로교통공단 운전면허시험장 방문",
            "citations": [{"law_name": "도로교통법 시행규칙", "article": "제53조"}],
        },
    ),
    (
        lambda req: getattr(req, "is_returning_from_abroad", False),
        ("건강보험 재가입", "건강보험 자격"),
        {
            "category": "건강보험 재가입",
            "title": "건강보험 자격 재취득 (해외 체류 중 자격정지된 경우)",
            "description": (
                "1개월 이상 해외 체류 시 건강보험 자격정지 신청한 경우, 입국 후 자격 재취득 신고 필요. "
                "직장가입자는 회사 4대보험 담당, 지역가입자는 가까운 건강보험공단 지사 방문 또는 1577-1000."
            ),
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "method": "건강보험공단 1577-1000 또는 지사 방문",
        },
    ),
    (
        lambda req: getattr(req, "is_returning_from_abroad", False),
        ("해외 휴대전화", "해외 번호"),
        {
            "category": "해외 휴대전화 정리",
            "title": "해외 통신사 정리 + 한국 번호 개통/이전",
            "description": (
                "해외 체류 중 사용한 현지 통신사 자동결제·로밍·해지 처리. 한국 번호는 본인 명의 신규 개통 "
                "(외국 영주권자는 거소신고증 또는 여권 본인확인) 또는 가족 명의 회선 본인 명의 변경."
            ),
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "method": "통신사 대리점 방문 (본인 신분증·거소신고증)",
        },
    ),
    # 전세·월세 계약일 때만
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("대항력", "우선변제권"),
        {
            "category": "대항력·우선변제권 확보",
            "title": "대항력·우선변제권 확보",
            "description": "주택 인도 + 전입신고 + 확정일자 3요건을 갖추면 보증금 우선변제권이 생깁니다.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제3조의2"}],
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("임차권등기",),
        {
            "category": "임차권등기명령 안내",
            "title": "임차권등기명령 신청 안내",
            "description": "임대차 종료 후 보증금 미반환 시 임차권등기명령으로 대항력 유지 가능.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제3조의3"}],
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("수선의무", "임대인 수선"),
        {
            "category": "임대인 수선의무 안내",
            "title": "임대인 수선의무",
            "description": "민법상 임대인은 임대물의 사용·수익에 필요한 수선 의무가 있습니다 (통상 사용 마모 제외).",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "민법", "article": "제623조"}],
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("갱신요구", "갱신 요구"),
        {
            "category": "임대차 갱신요구권 안내",
            "title": "임대차 갱신요구권 행사",
            "description": "임차인은 1회에 한해 2년 갱신 요구 가능. 계약 만료 6개월~2개월 전 통지.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제6조의3"}],
        },
    ),
    # 전월세 계약 신고 (2021년 6월 시행) — 보증금 6천만 초과 또는 월세 30만 초과
    (
        lambda req: (
            any(c in ("전세", "월세") for c in (req.contracts or [req.contract]))
            and (
                (req.deposit_krw or 0) > 60_000_000
                or (req.monthly_rent_krw or 0) > 300_000
            )
        ),
        ("전월세 계약 신고", "전월세신고"),
        {
            "category": "전월세 계약 신고",
            "title": "전월세 계약 신고 (전월세신고제)",
            "description": "보증금 6천만원 초과 또는 월세 30만원 초과 계약은 30일 이내 신고 의무.",
            "d_day_offset": 1,
            "has_legal_deadline": True,
            "deadline_days": 30,
            "citations": [
                {"law_name": "부동산 거래신고 등에 관한 법률", "article": "제6조의2"},
            ],
        },
    ),
    # 장기수선충당금 반환 — 아파트·오피스텔(공동주택) + 임차인만 해당.
    # 일반 원룸·빌라는 장기수선충당금 제도 없음 → is_apartment 조건 필수.
    (
        lambda req: bool(getattr(req, "is_apartment", False))
        and any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("장기수선충당금", "수선충당"),
        {
            "category": "장기수선충당금 반환청구",
            "title": "장기수선충당금 반환청구",
            "description": "공동주택(아파트·오피스텔) 장기수선충당금은 소유자(임대인) 부담 — 임차인이 관리비로 낸 금액은 퇴거 시 반환 청구 가능.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "공동주택관리법", "article": "제30조"}],
        },
    ),
    # 관리비 정산 — 전세/월세
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("관리비 정산", "관리비예치금", "관리비 예치금"),
        {
            "category": "관리비 정산",
            "title": "관리비예치금·관리비 정산",
            "description": "입주 시 선납한 관리비예치금은 이사 후 1~2주 내 반환 신청. 퇴거 월 관리비는 일할 정산.",
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "citations": [{"law_name": "공동주택관리법", "article": "제24조"}],
        },
    ),
    # 차임·보증금 증감청구 한도 (5% 상한) — 주임법 제7조 는 "차임 또는 보증금"
    # 모두 규율 → 전세·월세 모두 해당. 이전엔 월세만 조건으로 걸려 전세 임차인이
    # 누락되던 오류 수정.
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("증감청구", "증감 청구", "월세 인상", "전세금 인상"),
        {
            "category": "차임·보증금 증감청구 한도 안내",
            "title": "월세/보증금 증감청구 한도 안내",
            "description": "임대인은 연 5% 초과 인상을 청구할 수 없습니다. 증액은 1년에 1회 제한.",
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제7조"}],
        },
    ),
    # 주택수리 하자 분쟁해결 — 전세/월세
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("하자 분쟁", "하자분쟁", "주택수리"),
        {
            "category": "주택수리 하자 분쟁해결 기준",
            "title": "주택수리 하자 분쟁해결 기준",
            "description": "공정거래위원회 소비자분쟁해결기준 적용. 민사 소액 분쟁은 임대차분쟁조정위원회(1600-2571).",
            "d_day_offset": 1,
            "has_legal_deadline": False,
        },
    ),
    # 이사업체 분쟁 해결 방법 — 이사업체 이용자만
    (
        lambda req: getattr(req, "moving_style", "company") == "company",
        ("이사업체 분쟁", "이사 분쟁"),
        {
            "category": "이사업체 분쟁 해결 방법",
            "title": "이사업체 분쟁 해결 방법",
            "description": "한국소비자원(1372) 또는 공정거래위원회를 통해 분쟁 조정 신청. 허가업체 여부는 allmaeul.or.kr.",
            "d_day_offset": -3,
            "has_legal_deadline": False,
        },
    ),
    # 셀프 이사 — 용달·렌터카·포장자재
    (
        lambda req: getattr(req, "moving_style", "company") == "self",
        ("용달", "렌터카", "포장자재"),
        {
            "category": "셀프 이사 준비",
            "title": "용달·렌터카 예약 및 포장자재 구입",
            "description": "1톤 용달(화물맨·카모아 앱 등) 또는 카셰어링 카고밴 예약. 박스·테이프·뽁뽁이는 최소 1주 전 확보 권장.",
            "d_day_offset": -10,
            "has_legal_deadline": False,
        },
    ),
    # EXTRA special_concerns 라벨 기반 (프론트 checklist.tsx EXTRA_LABELS 와 정확히 일치)
    # 학생
    (
        lambda req: "학생" in (req.special_concerns or []),
        ("학교 주소변경", "재학증명", "학적"),
        {
            "category": "학교 학적 주소변경",
            "title": "학교 학적·재학증명 주소변경",
            "description": "재학 중인 학교/대학 학사시스템에서 주소 변경. 기숙사 입실 예정자는 별도 신청 필요. 도서관 회원정보도 동일 주소로 업데이트 권장.",
            "d_day_offset": 7,
            "has_legal_deadline": False,
        },
    ),
    # 병역 대상자
    (
        lambda req: "병역 대상자" in (req.special_concerns or []),
        ("병무청", "병역 주소"),
        {
            "category": "병무청 주소변경",
            "title": "병무청 거주지 신고",
            "description": "병역법에 따라 전입일로부터 14일 이내 관할 지방병무청에 거주지 변경 신고. 병무청 홈페이지 또는 직접 방문.",
            "d_day_offset": 1,
            "has_legal_deadline": True,
            "deadline_days": 14,
            "citations": [{"law_name": "병역법", "article": "제70조"}],
        },
    ),
    # 고층 이사
    (
        lambda req: "고층 이사 (엘베·곤도라)" in (req.special_concerns or []),
        ("엘리베이터", "곤도라", "사다리차"),
        {
            "category": "고층 이사 장비 예약",
            "title": "엘리베이터 사용 예약 및 곤도라·사다리차 신청",
            "description": "아파트 관리사무소에 엘리베이터 사용 신청 (보통 이사일 3~7일 전). 5층 이상이면 사다리차·곤도라 예약 필수. 대형 가구는 창문 반출 여부 확인.",
            "d_day_offset": -7,
            "has_legal_deadline": False,
        },
    ),
    # 대형 폐기물 배출
    (
        lambda req: "대형 폐기물 배출" in (req.special_concerns or []),
        ("대형폐기물", "대형 폐기물", "폐기물 스티커"),
        {
            "category": "대형 폐기물 배출",
            "title": "대형 폐기물 스티커 발급·배출 예약",
            "description": "주소지 관할 주민센터 또는 시·군·구청 홈페이지에서 품목별 수수료 결제 후 스티커 발급. 배출 지정일·장소 확인. 가전은 무상 수거 서비스(1599-0903) 가능.",
            "d_day_offset": -3,
            "has_legal_deadline": False,
        },
    ),
    # (인터넷 이전 설치 canonical 은 위쪽 `lambda req: True` 조건으로 이미 정의되어 있음 —
    #  special_concerns 기반 중복 정의는 제거. step 1 정확 일치로 항상 skip 되어 작동 안 함.)
    # TV 이전 (인터넷 이전과 별도 관리 — 하위 옵션이지만 하드코딩은 독립)
    (
        lambda req: "TV 이전" in (req.special_concerns or []),
        ("TV 수신료", "IPTV 이전", "TV 이전"),
        {
            "category": "TV 이전 설치·수신료 주소변경",
            "title": "IPTV 이전 설치 및 TV 수신료 주소변경",
            "description": "인터넷 이전과 동시 예약 시 편리. 지상파 수신 가구는 한전(123)에 TV 수신료 주소변경 별도 신고. 셋톱박스 분실 시 반납비 발생.",
            "d_day_offset": -7,
            "has_legal_deadline": False,
        },
    ),
    # ===== 임차인 이전 집 퇴거 (2026-04-22 추가) =====
    # structure_checklist_fallback 의 base 리스트에만 있던 7종을 canonical 로 승격.
    # free_text 있을 때(LLM 경로)는 base fallback 을 안 호출하므로, 이 항목들이
    # LLM 결과에 누락되면 사용자 눈엔 "재생성했더니 임대인 관련 항목이 사라졌다" 로 보였음.
    # _ensure_conditional_items 가 정적/LLM 양 경로 모두에서 호출되므로 여기 canonical 로
    # 두면 항상 주입됨. 정적 경로는 base 에 이미 있어 step1 정확 일치로 skip → 중복 없음.
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("계약 종료 통지", "계약 해지 통지", "종료 통지", "해지 통지"),
        {
            "category": "계약 해지 통지",
            "title": "임대인에게 계약 종료 통지",
            "description": "계약 만료 6개월~2개월 전에 서면(문자·카톡 포함)으로 종료 의사 통지. 통지 안 하면 묵시적 갱신되어 이사 곤란.",
            "d_day_offset": -60,
            "has_legal_deadline": True,
            "penalty": "묵시적 갱신 (2년 자동 연장)",
            "citations": [{"law_name": "주택임대차보호법", "article": "제6조"}],
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("보증금 반환 일정", "반환 일정 확인"),
        {
            "category": "보증금 반환 일정 확인",
            "title": "임대인에게 보증금 반환 일정 재확인",
            "description": "이사 당일 보증금 반환이 원칙. 임대인이 미루면 분쟁 조정 또는 임차권등기명령 준비.",
            "d_day_offset": -30,
            "has_legal_deadline": False,
            "method": "주택임대차분쟁조정위원회 1600-2571",
            "citations": [{"law_name": "주택임대차보호법", "article": "제4조"}],
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("사전 퇴실 점검", "퇴실 점검표", "1차 점검"),
        {
            "category": "사전 퇴실 점검",
            "title": "임대인과 1차 점검 + 퇴실 점검표 준비",
            "description": "이사 전 임대인과 함께 집 상태 사전 확인, 공제 항목 미리 합의. '퇴실점검표' 양식 준비하여 방·거실·주방·욕실·가전 상태 체크.",
            "d_day_offset": -7,
            "has_legal_deadline": False,
            "method": "문자·카톡 기록 보관 필수",
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("계량기 촬영", "계량기 사진", "계량기 기록"),
        {
            "category": "계량기 촬영",
            "title": "전기·수도·가스 계량기 사진+영상 기록",
            "description": "이사 당일 아침 계량기 숫자를 사진과 영상으로 기록. 임대인과 함께 확인. 요금 정산 분쟁의 결정적 증거.",
            "d_day_offset": 0,
            "has_legal_deadline": False,
            "method": "사진 + 1~2초 영상 (조작 의심 차단)",
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("최종 퇴실 점검", "퇴실 최종 점검", "원상회복"),
        {
            "category": "최종 퇴실 점검",
            "title": "임대인과 함께 집 상태 최종 점검 + 양측 서명",
            "description": "D-7 에 준비한 퇴실 점검표로 방별 체크. 합의 내용에 양측 서명. 원상회복 기준은 대법원 판례 참고 (5년 이상 거주 시 벽지·장판은 통상 마모).",
            "d_day_offset": 0,
            "has_legal_deadline": False,
            "method": "양측 서명 점검표 1부 보관",
            "citations": [
                {"law_name": "민법", "article": "제615조"},
                {"law_name": "민법", "article": "제623조"},
            ],
        },
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("보증금 수령", "키 반납", "열쇠 인계"),
        {
            "category": "보증금 수령 후 키 반납",
            "title": "보증금 입금 확인 후 열쇠 인계",
            "description": "원칙: 보증금 계좌 입금 확인 → 정산서 수령 → 열쇠 인계. 절대 반환 전에 열쇠 넘기지 말 것. 임대인이 '입금했다' 해도 본인 계좌 앱에서 직접 확인.",
            "d_day_offset": 0,
            "has_legal_deadline": False,
            "citations": [{"law_name": "주택임대차보호법", "article": "제3조의2"}],
        },
    ),
    # (대항력·우선변제권 canonical 은 위 line 1278-1289 에 이미 있어 중복 제거됨)

    # ===== 기본 법정 절차 (2026-04-22 추가) =====
    # 전입신고·확정일자 는 base(structure_checklist_fallback) 에만 있어서
    # free_text 있는 LLM 경로 진입 시 LLM 응답에 빠지면 그대로 누락됐다.
    # 이 두 항목은 모든 이사 · 모든 임차인의 최필수 법정 절차라서 무조건 보강.
    (
        lambda req: True,  # 전입신고는 모든 이사에 법정 필수 (14일 이내)
        ("전입신고",),
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
    ),
    (
        lambda req: any(c in ("전세", "월세") for c in (req.contracts or [req.contract])),
        ("확정일자",),
        {
            "category": "확정일자/임차권",
            "title": "확정일자 취득",
            "description": "보증금 보호를 위해 전입신고 당일 확정일자를 받아두세요.",
            "d_day_offset": 1,
            "deadline_days": 1,
            "has_legal_deadline": False,
            "method": "주민센터 방문 또는 인터넷등기소",
            "citations": [{"law_name": "주택임대차보호법", "article": "제3조의2"}],
        },
    ),
    # ===== base 에만 있던 실무·조건부 항목 보강 (2026-04-22) =====
    (
        # 셀프 이사는 업체 미사용 → 피해예방 항목이 무의미하므로 제외.
        # base 분기 조건과 정합.
        lambda req: (getattr(req, "moving_style", "company") or "company") != "self",
        ("이사업체 피해예방", "허가업체", "화물자동차 운송주선", "이사업체 견적"),
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
    ),
    (
        lambda req: bool(getattr(req, "receives_welfare", False)),
        ("복지급여", "기초생활수급", "복지로"),
        {
            "category": "복지급여 주소변경",
            "title": "복지급여 주소변경",
            "description": (
                "기초생활수급자·장애인연금·아동수당·한부모가족지원 등 복지급여 수급자는 "
                "이사 시 주소 반영 확인 필수. 대부분 전입신고로 자동 연계되지만 "
                "수급자격은 관할 자치단체 심사가 필요한 경우가 있어 누락되면 급여 중단 리스크."
            ),
            "d_day_offset": 7,
            "has_legal_deadline": False,
            "method": "복지로(bokjiro.go.kr) 또는 읍·면·동 주민센터 (☎ 129)",
            "citations": [{"law_name": "국민기초생활보장법", "article": "제23조"}],
        },
    ),
    (
        lambda req: bool(getattr(req, "needs_id_reissue", False)),
        ("주민등록증 재발급",),
        {
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
        },
    ),
    (
        lambda req: bool(getattr(req, "is_apartment", False)),
        ("관리사무소", "입주자 카드"),
        {
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
        },
    ),
    (
        lambda req: bool(getattr(req, "is_apartment", False)),
        ("우편함 명패", "현관 명패", "명패 교체"),
        {
            "category": "우편함 명패 교체",
            "title": "우편함·현관 명패 교체",
            "description": (
                "이전 거주자 명의가 남아있으면 우편물 오배송·분실 리스크. "
                "관리사무소에 명패 교체 요청 또는 직접 교체."
            ),
            "d_day_offset": 3,
            "has_legal_deadline": False,
        },
    ),
    (
        lambda req: bool(getattr(req, "is_apartment", False))
        and bool(getattr(req, "has_car", False)),
        ("단지 주차", "주차 등록", "입주민 주차"),
        {
            "category": "단지 주차 등록",
            "title": "단지 주차 등록 (차량 보유자)",
            "description": (
                "차량 번호·모델·사진 등록 후 입주민 주차 스티커 발급. "
                "미등록 차량은 견인 또는 과태료 대상."
            ),
            "d_day_offset": 1,
            "has_legal_deadline": False,
            "method": "관리사무소 주차 등록 창구",
        },
    ),
]


def _ensure_conditional_items(
    items: list[ChecklistItem], req: ChecklistRequest
) -> list[ChecklistItem]:
    """조건부 필수 항목 보정. 3-way 로직 (결정론 강화판 · 2026-04-22):

    1. canonical category 와 정확히 일치하는 item 이 이미 있음 → 본문(title·
       description·d_day_offset·has_legal_deadline·citations)을 하드코드로
       **덮어씀** — LLM 호출마다 미세하게 바뀌던 문구를 제거.
    2. 유사 항목(aliases 매칭)이 있음 → category 뿐 아니라 본문 전체를 canonical
       하드코드로 **덮어씀** (이전에는 category 만 rename 하고 LLM 문구 보존 →
       호출마다 description 변동이 사용자에게 "내용이 달라진다" 체감 원인).
    3. 둘 다 없음 → fallback_dict 로 새 항목 주입.

    결과: 같은 조건·같은 free_text 라면 canonical 에 해당하는 50개 항목은 문구
    까지 완전히 동일. LLM 은 canonical 탐지용으로만 사용.
    """
    all_canonicals = {fb["category"] for _, _, fb in _CONDITIONAL_REQUIRED}

    def _overwrite_with_fallback(it: ChecklistItem, fb: dict) -> None:
        """LLM 문구 변동 제거를 위해 item 본문을 canonical 하드코드로 대체."""
        raw = enrich_item_with_region(dict(fb), req.region)
        new_item = _item_from_dict(raw, req.move_date)
        it.category = new_item.category
        it.title = new_item.title
        it.description = new_item.description
        it.d_day_offset = new_item.d_day_offset
        it.start_date = new_item.start_date
        it.deadline_date = new_item.deadline_date
        it.deadline_days = new_item.deadline_days
        it.has_legal_deadline = new_item.has_legal_deadline
        it.penalty = new_item.penalty
        it.method = new_item.method
        it.contact = new_item.contact
        it.region_hint = new_item.region_hint
        it.citations = new_item.citations

    for condition_fn, aliases, fallback_dict in _CONDITIONAL_REQUIRED:
        try:
            if not condition_fn(req):
                continue
        except AttributeError:
            continue
        canonical = fallback_dict["category"]

        # 1) 정확 일치가 이미 있음 — 본문 덮어쓰기로 결정론 보장
        exact = next((it for it in items if it.category == canonical), None)
        if exact is not None:
            _overwrite_with_fallback(exact, fallback_dict)
            continue

        # 2) aliases 매칭되는 유사 LLM 항목 찾기 → canonical 본문 전체로 대체
        #    단, 이미 다른 canonical 카테고리로 분류된 항목은 건드리지 않음
        renamed = False
        for it in items:
            if it.category in all_canonicals and it.category != canonical:
                continue
            hay = f"{it.category} {it.title}"
            if any(kw in hay for kw in aliases):
                _overwrite_with_fallback(it, fallback_dict)
                renamed = True
                break
        if renamed:
            continue

        # 3) 완전 부재 → 하드코딩 주입
        raw = enrich_item_with_region(dict(fallback_dict), req.region)
        items.append(_item_from_dict(raw, req.move_date))
    return items


# ---------- Step 4: 날짜 정렬 + 응답 조립 ----------


# ===== 결정론화 캐시 =====
# 같은 입력(요청 필드 전체) → 같은 출력 보장. LLM seed=42 + temperature=0 이 best-effort 라
# 100% 보장 안 되므로 추가 안전장치로 메모리 캐시. 발표 시연 시 매번 같은 결과 노출.
# process 재시작 시 사라지는 in-memory LRU — 발표·운영 모두 안전.
from collections import OrderedDict as _OrdDict
_GENERATE_CACHE_MAX = 512  # 메모리 폭주 방어. 응답 1건당 ~30-50KB JSON → 상한 ~25MB.
_GENERATE_CACHE: "_OrdDict[str, ChecklistResponse]" = _OrdDict()


def _cache_get(key: str):
    val = _GENERATE_CACHE.get(key)
    if val is not None:
        _GENERATE_CACHE.move_to_end(key)  # LRU: 재접근 시 뒤로
    return val


def _cache_put(key: str, value) -> None:
    _GENERATE_CACHE[key] = value
    _GENERATE_CACHE.move_to_end(key)
    while len(_GENERATE_CACHE) > _GENERATE_CACHE_MAX:
        _GENERATE_CACHE.popitem(last=False)  # 가장 오래된 것 제거


def _request_cache_key(req: ChecklistRequest) -> str:
    """ChecklistRequest 의 모든 필드를 안정적으로 직렬화한 SHA256 해시."""
    import hashlib
    blob = json.dumps(
        req.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------- free_text 키워드 → 구조화 플래그 자동 승격 ----------
# 사용자가 체크박스를 안 켜고 기타 특이사항에만 "강아지 키울 예정" 같이 서술한 경우,
# LLM 은 맞춤 항목을 생성할 수 있어도 `has_pet` 조건 canonical (반려동물 등록 주소변경 등)
# 은 주입되지 않아 핵심 법정 절차가 누락됨. 키워드 매칭으로 플래그를 끌어올려 정적
# 경로의 canonical 조건을 재활용한다.
_FREETEXT_FLAG_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("has_pet", ("강아지", "고양이", "반려동물", "반려견", "반려묘", "댕댕이",
                 "냥이", "개를 키", "고양이를 키")),
    ("has_car", ("자동차", "차량", "운전면허", "차고지", "자가용", "승용차")),
    ("has_children", ("자녀", "아이가", "아이를", "유치원", "어린이집",
                      "초등학교", "중학교", "고등학교", "자녀 전학")),
    # is_foreigner 는 "외국 국적자" 트리거 — 외국인등록 주소변경 항목 주입.
    # "해외에서" / "귀국" 은 한국인 귀국자도 매칭되어 false positive (외국인 등록
    # 항목이 한국인에게 잘못 추가됨) → 제외. 한국인 귀국자 전용 항목은 별도 플래그
    # (`is_returning_from_abroad`) 도입 시 처리.
    ("is_foreigner", ("외국인", "비자", "영주권", "이주민", "체류")),
    # 한국인 귀국자 — 재외국민 거소신고·외국면허 인정·건강보험 재가입·해외 휴대전화 정리
    ("is_returning_from_abroad", (
        "해외에서 귀국", "해외에서 돌아", "한국으로 돌아", "한국 돌아",
        "귀국", "역이민", "재외국민", "장기 해외 체류",
    )),
    ("is_apartment", ("아파트", "오피스텔", "단지", "관리사무소", "입주자 카드")),
    ("receives_welfare", ("기초생활수급", "복지급여", "장애인연금",
                          "한부모", "수급자")),
    ("is_employed", ("직장", "회사", "재직", "근무 중", "출근", "사내")),
    ("needs_id_reissue", ("주민등록증 재발급", "신분증 분실", "주민증 분실")),
]


# 승격된 플래그 → 영향받는 canonical category 매핑 (프론트 보라색 표시용).
_FLAG_TO_CATEGORIES: dict[str, tuple[str, ...]] = {
    "has_pet": ("반려동물 등록 주소변경",),
    "has_car": (
        "자동차 변경등록",
        "운전면허 주소변경",
        "자동차보험 주소변경",
        "단지 주차 등록",
    ),
    "has_children": ("자녀 전학", "자녀 학원 주소 확인"),
    "is_foreigner": ("외국인등록 주소변경",),
    "is_returning_from_abroad": (
        "재외국민 거소신고",
        "외국 운전면허 한국 인정",
        "건강보험 재가입",
        "해외 휴대전화 정리",
    ),
    "is_apartment": (
        "관리사무소 입주 신고",
        "우편함 명패 교체",
        "단지 주차 등록",
        "장기수선충당금 반환청구",
    ),
    "is_employed": ("직장 주소변경 신고",),
    "receives_welfare": ("복지급여 주소변경",),
    "needs_id_reissue": ("주민등록증 재발급",),
}


# 키워드 매칭 후 같은 컨텍스트 윈도우 안에 있으면 false positive 로 판정해 skip 하는 패턴.
# - 부정: "강아지 키우고 싶지만 못", "직장이 없어서", "회사 안 다녀요"
# - 과거: "아파트 살았는데", "고등학교 다닐 때"
# - 타인: "친구가 외국인", "이전 직장에서"
_NEGATION_PATTERNS = ("없", "안 ", "못 ", "안다닌", "안다녀", "안키")
_PAST_PATTERNS = ("었어", "었던", "었을", "었지", "였어", "였던", "다녔", "살았",
                  "지냈", "받았", "였습", "었습")
_OTHER_PERSON_PATTERNS = ("친구", "지인", "이전", "예전", "전에", "옛날", "동생",
                          "부모님", "어머니", "아버지", "형이", "누나가", "언니가")


def _is_negated_context(text: str, kw: str) -> bool:
    """키워드 매칭이 부정/과거/타인 컨텍스트인지 휴리스틱.

    키워드 위치 ±15자 윈도우에 부정·과거·타인 지칭 패턴이 있으면 True.
    한글 부정어가 키워드보다 뒤에 오는 경우가 많아 뒤쪽 윈도우를 더 넓게.
    """
    idx = text.find(kw)
    if idx < 0:
        return False
    start = max(0, idx - 10)
    end = min(len(text), idx + len(kw) + 20)
    window = text[start:end]
    for p in _NEGATION_PATTERNS + _PAST_PATTERNS + _OTHER_PERSON_PATTERNS:
        if p in window:
            return True
    return False


def _augment_flags_from_freetext(
    req: ChecklistRequest,
) -> tuple[ChecklistRequest, list[str], list[str]]:
    """free_text 를 파싱해 구조화 플래그 (has_pet 등) 를 끌어올림.

    이미 True 인 플래그는 건드리지 않음 (사용자가 명시적으로 체크한 건 유지).
    False 인 플래그 중 free_text 에 관련 키워드가 있으면 True 로 승격하되,
    부정·과거·타인 지칭 컨텍스트는 휴리스틱으로 false positive 차단.
    반환: (새 req, 매칭 키워드, 승격된 플래그). 승격 없으면 원본 req + 빈 리스트 × 2.
    """
    ft = (req.free_text or "")
    if not ft.strip():
        return req, [], []
    updates: dict = {}
    matched: list[str] = []
    for flag, keywords in _FREETEXT_FLAG_KEYWORDS:
        if getattr(req, flag, False):
            continue  # 이미 True 면 유지
        for kw in keywords:
            if kw not in ft:
                continue
            if _is_negated_context(ft, kw):
                continue  # 부정·과거·타인 컨텍스트 → skip
            updates[flag] = True
            matched.append(kw)
            break  # 같은 flag 는 한 키워드만
    if not updates:
        return req, [], []
    import logging as _log
    _log.getLogger("movewise").info(
        f"[checklist] freetext→flags promoted: {list(updates.keys())} "
        f"matched={matched}"
    )
    return req.model_copy(update=updates), matched, list(updates.keys())


def generate_checklist(req: ChecklistRequest) -> ChecklistResponse:
    """체크리스트 생성 — 정적 매핑 중심 + free_text 만 LLM.

    설계 원칙 (2026-04-21 확정):
    - 정형 토글(household/contracts/has_pet/has_car/...)은 모두 정적 매핑으로 처리.
      LLM 호출 0회, 응답 시간 대폭 단축, 결정론 보장.
    - `free_text` (Step 4 "기타 특이사항") 가 있을 때만 LLM 경로 활성화:
      → build_queries_freetext_llm → search_procedures → structure_checklist_llm.
    - 기본 경로(free_text 비어있음): search/LLM 전부 스킵하고 fallback 리스트만 사용 +
      _ensure_utility_items · _ensure_conditional_items 로 26+ 조건부 항목 보강.
    - free_text 에 "강아지"·"아파트" 같은 키워드가 있으면 체크박스 미선택이어도
      구조화 플래그로 자동 승격되어 해당 canonical 항목이 주입된다 (2026-04-22).
    """
    import logging as _log
    _logger = _log.getLogger("movewise")

    # 0) free_text 키워드 → 구조화 플래그 자동 승격 (체크박스 누락 보정)
    original_ft = (req.free_text or "").strip()
    req, matched_keywords, promoted_flags = _augment_flags_from_freetext(req)

    # 1) 캐시 hit → 즉시 반환 (LLM 호출 0회)
    cache_key = _request_cache_key(req)
    cached = _cache_get(cache_key)
    if cached is not None:
        _logger.info(f"[checklist] cache HIT key={cache_key}")
        return cached

    # 2) 경로 분기 — free_text 있을 때만 LLM 경로 (Azure Search + GPT-4o)
    # 정형 토글만이면 정적 fallback. free_text 의 자유 표현은 키워드 매칭으로
    # 못 잡는 엣지케이스(예: "신축 입주 하자 점검", "조부모 동거") 까지 커버.
    # 결정론은 _request_cache_key 캐시 (위) 가 담당 — 같은 input → 같은 output.
    has_free_text = bool(original_ft)
    if has_free_text:
        queries = build_queries_freetext_llm(req)
        chunks = search_procedures(queries, req)
        items, used_fallback = structure_checklist_llm(req, chunks)
        _logger.info(
            f"[checklist] mode=llm free_text=on queries={len(queries)} "
            f"chunks={len(chunks)} items={len(items)} fallback={used_fallback}"
        )
    else:
        queries = build_queries_rule_based(req)
        items = structure_checklist_fallback(req, chunks=[])
        _logger.info(f"[checklist] mode=static items={len(items)}")

    items = _ensure_utility_items(items, req)
    items = _ensure_conditional_items(items, req)

    # free_text 승격된 플래그로 인해 등장한 항목에 from_freetext=True 마킹
    # 프론트에서 해당 item 보라색 표시용.
    if promoted_flags:
        freetext_cats: set[str] = set()
        for flag in promoted_flags:
            freetext_cats.update(_FLAG_TO_CATEGORIES.get(flag, ()))
        for it in items:
            if it.category in freetext_cats:
                it.from_freetext = True

    # 결정론적 정렬: d_day_offset → category → title (tie-break 안정화)
    items.sort(key=lambda x: (x.d_day_offset, x.category or "", x.title or ""))

    # free_text 반영 여부 사용자 피드백 메시지 — warning 필드 재활용.
    if matched_keywords:
        unique_kws = list(dict.fromkeys(matched_keywords))  # 순서 유지 dedupe
        warning = (
            f"입력하신 \"{', '.join(unique_kws[:3])}\" 키워드로 관련 체크 항목이 "
            f"자동 추가되었습니다."
        )
    elif original_ft:
        warning = (
            "입력하신 내용에 해당하는 추가 항목이 없어요. "
            "예) 강아지·고양이 · 아파트·오피스텔 · 자녀·아이 · 외국인·귀국 · "
            "직장·재직 · 복지급여 · 자동차 · 보험 · 주민등록증 재발급 등"
        )
    else:
        warning = None

    response = ChecklistResponse(
        request=req,
        generated_at=date.today(),
        items=items,
        total_items=len(items),
        used_queries=queries,
        warning=warning,
    )
    _cache_put(cache_key, response)
    return response
