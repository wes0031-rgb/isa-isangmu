"""Pydantic request/response models for MoveWise."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

HouseholdType = Literal["자취", "신혼", "가족"]
ContractType = Literal["전세", "월세", "자가"]
SchoolLevel = Literal["초등", "중등", "고등"]


# ===== /checklist =====


class ChecklistRequest(BaseModel):
    household: HouseholdType = Field(description="세대 유형")
    contract: ContractType = Field(description="계약 유형")
    region: str = Field(description="시/도 시/군/구 (예: '경기도 성남시 분당구')")
    move_date: date = Field(description="이사 예정일 (YYYY-MM-DD)")
    has_pet: bool = False
    has_car: bool = False
    car_count: int = 1
    has_children: bool = False
    children_count: int = 0
    children_school_level: Optional[SchoolLevel] = None
    is_foreigner: bool = False
    deposit_krw: Optional[int] = None
    monthly_rent_krw: Optional[int] = None
    special_concerns: list[str] = Field(default_factory=list)


class ChecklistCitation(BaseModel):
    law_name: str
    article: str
    source_url: Optional[str] = None


class ChecklistItem(BaseModel):
    category: str
    title: str
    description: str
    d_day_offset: int = Field(description="이사일 기준 시작일(일 단위, 음수=이사 전)")
    start_date: date
    has_legal_deadline: bool
    deadline_date: Optional[date] = None
    deadline_days: Optional[int] = None
    penalty: Optional[str] = None
    method: Optional[str] = None
    contact: Optional[str] = None
    region_hint: Optional[str] = None
    citations: list[ChecklistCitation] = Field(default_factory=list)


class ChecklistResponse(BaseModel):
    request: ChecklistRequest
    generated_at: date
    items: list[ChecklistItem]
    total_items: int
    used_queries: list[str] = Field(
        description="LLM이 생성한 AI Search 검색 쿼리 목록 (재현성 확인용)"
    )
    warning: Optional[str] = None


# ===== /safecontract =====


class SafeContractRequest(BaseModel):
    text: Optional[str] = Field(
        default=None,
        description="인터넷등기소에서 복사한 등기부등본 텍스트 (P0)",
    )
    # PDF 업로드는 multipart 엔드포인트로 별도 처리
    deposit_krw: int = Field(description="계약 보증금 (원)")
    expected_market_price_krw: int = Field(description="해당 주택 예상 시세 (원)")


class RegistryExtraction(BaseModel):
    owner_change_within_2_years: int = 0
    mortgage_total_krw: int = 0
    mortgage_claim_amount_krw: int = 0
    seizure_count: int = 0
    seizure_total_krw: int = 0
    trust_registration: bool = False
    auction_in_progress: bool = False
    raw_notes: list[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    severity: Literal["green", "yellow", "red"]
    label: str
    explanation_plain: str
    related_laws: list[ChecklistCitation] = Field(default_factory=list)


class ServiceReferral(BaseModel):
    icon: str
    name: str
    url: str
    description: str


class SafeContractResponse(BaseModel):
    extraction: RegistryExtraction
    jeontse_ratio: float = Field(description="(근저당액 + 보증금) / 시세")
    summary: str
    risks: list[RiskItem]
    referrals: list[ServiceReferral]
    disclaimer: str
