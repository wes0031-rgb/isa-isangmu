"""MoveWise FastAPI entry point."""
from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .checklist_service import generate_checklist
from .config import get_settings
from .models import (
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

app = FastAPI(
    title="MoveWise API",
    description="이사 여정 가이드 — 체크리스트 + SafeContract",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    settings = get_settings()
    return {
        "service": "MoveWise",
        "version": "0.1.0",
        "azure_ready": settings.azure_ready,
        "endpoints": ["/checklist", "/safecontract"],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/checklist", response_model=ChecklistResponse)
def post_checklist(req: ChecklistRequest) -> ChecklistResponse:
    return generate_checklist(req)


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
