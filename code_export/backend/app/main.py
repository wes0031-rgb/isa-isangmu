"""MoveWise FastAPI entry point."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .checklist_service import generate_checklist
from .config import get_settings
from .models import (
    ChecklistRequest,
    ChecklistResponse,
    SafeContractRequest,
    SafeContractResponse,
)
from .safecontract_service import analyze_safecontract

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
