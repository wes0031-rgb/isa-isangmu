"""이사이상무 FastAPI entry point."""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .chat_service import generate_chat_reply, get_preset_questions
from .checklist_service import generate_checklist
from .config import get_settings
from .local_search import load_chunks, load_laws, load_youtube
from .models import (
    ChatRequest,
    ChatResponse,
    ChecklistRequest,
    ChecklistResponse,
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
    title="이사이상무 API",
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
        "service": "이사이상무",
        "version": "0.2.0",
        "azure_ready": settings.azure_ready,
        "endpoints": [
            "/checklist",
            "/safecontract",
            "/safecontract/upload",
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
    }


@app.post("/checklist", response_model=ChecklistResponse)
def post_checklist(req: ChecklistRequest) -> ChecklistResponse:
    return generate_checklist(req)


@app.post("/chat", response_model=ChatResponse)
def post_chat(req: ChatRequest) -> ChatResponse:
    """챗봇 — 이사·전월세 질문에 대한 RAG 답변 (Azure 있으면 LLM, 없으면 키워드 검색)."""
    history = [{"role": m.role, "content": m.content} for m in req.history]
    reply = generate_chat_reply(req.question, history=history)
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
    expected_market_price_krw: int = Form(0, description="예상 시세 (원, 0 = 자동 조회)"),
    region: str = Form("", description="시·군·구 (비워두면 PDF 주소에서 자동 파싱)"),
) -> SafeContractResponse:
    """등기부등본 PDF 업로드 → Document Intelligence 파싱 → 기존 분석.

    기획서 3.5.2 P1 목표. Azure Document Intelligence 가 설정돼야 동작.

    expected_market_price_krw = 0 이고 region 이 비어있으면 PDF 에서 주소 파싱 후
    국토부 실거래가 API 로 시세 자동 조회.
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
            region=region or None,
        )
    except DocumentIntelligenceNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"PDF 처리 실패: {exc}"
        )
