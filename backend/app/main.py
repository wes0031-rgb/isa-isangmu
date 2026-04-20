"""이사이상무 FastAPI entry point."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Rate limiting — slowapi 미설치 시 no-op 데코레이터로 graceful degrade.
# (팀원 로컬에 아직 pip install 전이어도 import 에러 없이 동작하도록)
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler  # type: ignore
    from slowapi.errors import RateLimitExceeded  # type: ignore
    from slowapi.util import get_remote_address  # type: ignore

    _RATE_LIMIT_AVAILABLE = True
except ImportError:
    _RATE_LIMIT_AVAILABLE = False

    def _noop_decorator(*_a, **_kw):
        def wrap(fn):
            return fn
        return wrap

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

# Rate limiter 인스턴스 — IP 기반. slowapi 미설치 시 no-op 데코레이터.
if _RATE_LIMIT_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    _limit = limiter.limit
else:
    _limit = _noop_decorator  # type: ignore[assignment]
    logger = logging.getLogger("movewise")
    logger.warning(
        "slowapi 미설치 — rate limiting 비활성화. `pip install slowapi` 권장."
    )

# CORS 화이트리스트 — 배포 도메인 + 개발 환경만 허용.
# Expo 번들 호스트는 random 이라 정규식으로 매칭.
_ALLOWED_ORIGINS = [
    "https://movewise-jf1s.onrender.com",       # 팀 Render 배포
    "https://iim-isaisangmu.azurewebsites.net", # Azure App Service (배포 후)
    "http://localhost:8081",                     # Metro 기본
    "http://localhost:8082",                     # 이사이상무 Metro
    "http://127.0.0.1:8765",                     # 로컬 uvicorn 직접 호출 테스트
]
_ALLOWED_ORIGIN_REGEX = (
    r"https?://"
    r"(localhost:\d+|127\.0\.0\.1:\d+|192\.168\.\d+\.\d+:\d+|"
    r"[a-z0-9-]+\.exp\.direct|"              # Expo tunnel
    r"[a-z0-9-]+\.azurewebsites\.net|"       # Azure App Service
    r"[a-z0-9-]+\.onrender\.com)"            # Render
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=_ALLOWED_ORIGIN_REGEX,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=False,
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


@app.get("/api/info")
def api_info() -> dict:
    """API 진단용 — 이전 `/` 핸들러. PWA 서빙과 충돌 방지 위해 /api/info 로 이동."""
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
@_limit("20/minute")
def post_checklist(request: Request, req: ChecklistRequest) -> ChecklistResponse:
    try:
        return generate_checklist(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("/checklist 처리 중 내부 오류")
        raise HTTPException(
            status_code=500,
            detail="체크리스트 생성에 실패했습니다. 잠시 후 다시 시도해주세요.",
        )


@app.post("/chat", response_model=ChatResponse)
@_limit("30/minute")
def post_chat(request: Request, req: ChatRequest) -> ChatResponse:
    """챗봇 — 이사·전월세 질문에 대한 RAG 답변 (Azure 있으면 LLM, 없으면 키워드 검색)."""
    try:
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("/chat 처리 중 내부 오류")
        raise HTTPException(
            status_code=500,
            detail="답변 생성에 실패했습니다. 잠시 후 다시 시도해주세요.",
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
@_limit("10/minute")
def post_safecontract(request: Request, req: SafeContractRequest) -> SafeContractResponse:
    try:
        return analyze_safecontract(req)
    except ValueError as exc:
        # ValueError 는 사용자 입력 문제 → 메시지 전달 OK
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        # 내부 예외 상세는 서버 로그로만, 클라이언트엔 일반 메시지
        logger.exception("/safecontract 처리 중 내부 오류")
        raise HTTPException(
            status_code=500, detail="분석에 실패했습니다. 잠시 후 다시 시도해주세요."
        )


@app.post("/safecontract/upload", response_model=SafeContractResponse)
@_limit("5/minute")
async def post_safecontract_upload(
    request: Request,
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
    # 1) 확장자 + 매직 바이트 검증 — 확장자 위조 방어
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다")

    MAX_SIZE = 20 * 1024 * 1024  # 20MB
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="파일 크기는 20MB 이하여야 합니다")
    # 2) PDF 매직바이트 체크 — 실 PDF 첫 4바이트 "%PDF"
    if not contents.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail="올바른 PDF 파일이 아닙니다 (파일 헤더 검증 실패)",
        )

    # 3) 입력 범위 검증 — 비정상 값 차단
    if deposit_krw < 0 or deposit_krw > 50_000_000_000:  # 500 억 상한
        raise HTTPException(status_code=400, detail="보증금 값이 올바르지 않습니다")
    if expected_market_price_krw < 0 or expected_market_price_krw > 50_000_000_000:
        raise HTTPException(status_code=400, detail="예상 시세 값이 올바르지 않습니다")

    try:
        return analyze_safecontract_pdf(
            contents,
            deposit_krw=deposit_krw,
            expected_market_price_krw=expected_market_price_krw,
            region=region or None,
        )
    except DocumentIntelligenceNotConfigured as exc:
        # 환경 설정 문제는 503 + 사용자용 안내 메시지
        raise HTTPException(
            status_code=503,
            detail="문서 분석 서비스가 준비되지 않았습니다. 관리자에게 문의해주세요.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("/safecontract/upload PDF 처리 중 내부 오류")
        raise HTTPException(
            status_code=500,
            detail="PDF 분석에 실패했습니다. 스캔 품질을 확인하거나 잠시 후 다시 시도해주세요.",
        )


# ==================================================================
# PWA 정적 서빙 (Expo web export → backend/app/main.py 기준 dist)
# ==================================================================
# frontend/movewise-app/dist 가 존재하면 FastAPI 에서 함께 서빙.
# - /_expo /assets 하위는 StaticFiles 직접 매핑 (파일 해시 포함)
# - 그 외 GET 경로는 SPA fallback → index.html (Expo Router client routing)
# - API 경로 (POST · /health · /realty/summary · /chat/presets · /api/info)
#   는 method/구체 path 우선 매칭으로 보존
_WEB_DIST = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend"
    / "movewise-app"
    / "dist"
)

if _WEB_DIST.is_dir():
    for _sub in ("_expo", "assets", "static"):
        _dir = _WEB_DIST / _sub
        if _dir.is_dir():
            app.mount(f"/{_sub}", StaticFiles(directory=_dir), name=f"pwa-{_sub}")

    _RESERVED_API_PATHS = {
        "health",
        "chat/presets",
        "realty/summary",
        "api/info",
    }

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # 예약된 API 경로는 명시 핸들러가 위에서 처리. catch-all 진입 시 404.
        if full_path in _RESERVED_API_PATHS:
            raise HTTPException(status_code=404)

        candidate = _WEB_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)

        # SPA routing: / · /chat · /checklist · /safecontract · /my 등
        return FileResponse(_WEB_DIST / "index.html")
else:
    logger.warning(
        f"PWA dist 디렉토리 없음 ({_WEB_DIST}) — API-only 모드로 동작. "
        "웹 배포하려면 `npx expo export --platform web` 실행 후 재기동."
    )
