"""MoveWise FastAPI entry point."""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .chat_service import generate_chat_reply, get_preset_questions
from .checklist_service import generate_checklist
from . import codef_client
from .config import get_settings
from .local_search import load_chunks, load_laws, load_youtube
from .models import (
    ChatRequest,
    ChatResponse,
    ChecklistRequest,
    ChecklistResponse,
    CodefRegisterCandidate,
    CodefRegisterSearchRequest,
    CodefRegisterSearchResponse,
    SafeContractRequest,
    SafeContractResponse,
)
from .safecontract_service import (
    DocumentIntelligenceNotConfigured,
    analyze_safecontract,
    analyze_safecontract_pdf,
)

# 성능 로깅 (task #72 성능 모니터링)
logger = logging.getLogger("movewise")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="MoveWise API",
    description="이사 여정 가이드 — 체크리스트 + SafeContract + 챗봇",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def perf_middleware(request: Request, call_next):
    """요청/응답 시간 + 상태 로깅."""
    start = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        logger.exception(
            f"{request.method} {request.url.path} → 500 ({elapsed:.0f}ms): {exc}"
        )
        raise
    elapsed = (time.time() - start) * 1000
    level = logger.warning if elapsed > 3000 else logger.info
    level(
        f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.0f}ms)"
    )
    return response


@app.get("/")
def root() -> dict:
    settings = get_settings()
    return {
        "service": "MoveWise",
        "version": "0.2.0",
        "azure_ready": settings.azure_ready,
        "codef_ready": codef_client.is_configured(),
        "codef_env": codef_client.env_mode(),
        "endpoints": [
            "/checklist",
            "/safecontract",
            "/safecontract/upload",
            "/safecontract/register-search",
            "/chat",
            "/health",
        ],
    }


@app.get("/health")
def health() -> dict:
    """깊은 헬스체크 — 모든 의존성 상태 반환."""
    settings = get_settings()
    checks = {
        "index_a_law_chunks": len(load_laws()),
        "index_b_procedure_chunks": len(load_chunks()),
        "index_c_youtube_chunks": len(load_youtube()),
    }
    azure = {
        "openai": bool(settings.azure_openai_api_key and settings.azure_openai_endpoint),
        "search": bool(settings.azure_search_api_key and settings.azure_search_endpoint),
        "docintel": bool(
            settings.azure_docintel_api_key and settings.azure_docintel_endpoint
        ),
        "blob": bool(settings.azure_blob_connection_string),
    }
    external = {
        "data_go_kr": bool(settings.data_go_kr_service_key),
        "law_oc": bool(settings.law_oc),
        "juso": bool(settings.juso_api_key),
    }
    all_indexes_loaded = all(checks.values())
    return {
        "status": "ok" if all_indexes_loaded else "degraded",
        "version": "0.2.0",
        "mode": "azure" if settings.azure_ready else "fallback",
        "indexes": checks,
        "azure": azure,
        "external_apis": external,
        "azure_ready": settings.azure_ready,
        "codef_ready": codef_client.is_configured(),
        "codef_env": codef_client.env_mode(),
    }


@app.post("/checklist", response_model=ChecklistResponse)
def post_checklist(req: ChecklistRequest) -> ChecklistResponse:
    return generate_checklist(req)


@app.post("/chat", response_model=ChatResponse)
def post_chat(req: ChatRequest) -> ChatResponse:
    """챗봇 — 이사·전월세 질문에 대한 RAG 답변 (Azure 있으면 LLM, 없으면 키워드 검색)."""
    reply = generate_chat_reply(req.question)
    return ChatResponse(
        answer=reply.answer,
        mode=reply.mode,
        citations=[
            {
                "source_type": c.source_type,
                "title": c.title,
                "content_snippet": c.content_snippet,
                "url": c.url,
                "meta": c.meta,
            }
            for c in reply.citations
        ],
        used_queries=reply.used_queries,
    )


@app.get("/chat/presets")
def get_chat_presets() -> dict:
    return {"questions": get_preset_questions()}


@app.get("/realty/summary")
def get_realty_summary(region: str) -> dict:
    """지역명으로 국토부 실거래가 최근 요약 반환 (홈 대시보드용)."""
    from .realty_price import get_region_price_summary

    s = get_region_price_summary(region)
    return {
        "region": s.region,
        "lawd_cd": s.lawd_cd,
        "query_ym": s.query_ym,
        "total_count": s.total_count,
        "median_price_krw": s.median_price_krw,
        "min_price_krw": s.min_price_krw,
        "max_price_krw": s.max_price_krw,
        "recent_deals": [
            {
                "apt_name": d.apt_name,
                "deal_amount_krw": d.deal_amount_krw,
                "deal_date": f"{d.deal_year}-{d.deal_month:02d}-{d.deal_day:02d}",
                "area_m2": d.area_m2,
                "floor": d.floor,
            }
            for d in s.recent_deals[:3]
        ],
        "error": s.error,
    }


@app.post("/safecontract", response_model=SafeContractResponse)
def post_safecontract(req: SafeContractRequest) -> SafeContractResponse:
    try:
        return analyze_safecontract(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/safecontract/upload", response_model=SafeContractResponse)
async def post_safecontract_upload(
    file: UploadFile = File(..., description="등기부등본 PDF"),
    deposit_krw: int = Form(..., description="보증금 (원)"),
    expected_market_price_krw: int = Form(..., description="예상 시세 (원)"),
) -> SafeContractResponse:
    """등기부등본 PDF 업로드 → Document Intelligence 파싱 → 기존 분석.

    기획서 3.5.2 P1 목표. Azure Document Intelligence 가 설정돼야 동작.
    """
    if not file.filename or not file.filename.lower().endswith((".pdf",)):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다")

    MAX_SIZE = 20 * 1024 * 1024  # 20MB
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="파일 크기는 20MB 이하여야 합니다")

    try:
        return analyze_safecontract_pdf(
            contents,
            deposit_krw=deposit_krw,
            expected_market_price_krw=expected_market_price_krw,
        )
    except DocumentIntelligenceNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"PDF 처리 실패: {exc}"
        )


@app.post(
    "/safecontract/register-search",
    response_model=CodefRegisterSearchResponse,
)
def post_register_search(
    req: CodefRegisterSearchRequest,
) -> CodefRegisterSearchResponse:
    """
    CODEF 등기부등본 주소 검색 — 주소 → 해당 주소의 등기부 후보 목록.

    개발환경(demo)에서는 실제 대법원 등기소 데이터를 무료로 반환.
    실 등기부등본 본문 조회는 운영환경 + 선불카드 필요.
    """
    client = codef_client.get_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="CODEF API 미설정 — .env 에 CODEF_CLIENT_ID / CLIENT_SECRET 필요",
        )
    try:
        res = client.search_real_estate_candidates(
            address=req.address,
            real_estate_type=req.real_estate_type,
        )
    except Exception as exc:
        logger.exception("CODEF register search 실패: %s", exc)
        raise HTTPException(status_code=502, detail=f"CODEF 호출 실패: {exc}")

    result = res.get("result", {})
    data = res.get("data", {}) or {}
    extra = data.get("extraInfo", {}) or {}
    raw_list = extra.get("resAddrList", []) or []

    # CODEF 응답 필드값은 URL-encoded (공백이 +). 디코딩해서 사용자에게 깔끔하게.
    from urllib.parse import unquote_plus
    candidates = [
        CodefRegisterCandidate(
            unique_no=item.get("commUniqueNo", ""),
            address=unquote_plus(item.get("commAddrLotNumber", "")),
            real_estate_type=unquote_plus(item.get("resType", "")),
            state=unquote_plus(item.get("resState", "")),
        )
        for item in raw_list
        if item.get("commUniqueNo")
    ]

    ok = result.get("code") in ("CF-00000", "CF-03002")
    return CodefRegisterSearchResponse(
        ok=ok,
        env_mode=codef_client.env_mode(),
        candidates=candidates,
        total=len(candidates),
        transaction_id=result.get("transactionId"),
        message=unquote_plus(result.get("message", "")) if result.get("message") else None,
    )
