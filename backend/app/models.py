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
    contract: ContractType = Field(description="계약 유형 (대표값, legacy)")
    contracts: list[ContractType] = Field(
        default_factory=list,
        description="계약 유형 복수 선택 (없으면 contract 단일값으로 사용)",
    )
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
    article_title: Optional[str] = None
    article_text: Optional[str] = None


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
    expected_market_price_krw: int = Field(
        description="해당 주택 예상 시세 (원). 0이면 region 으로 자동 조회 시도."
    )
    region: Optional[str] = Field(
        default=None,
        description="시·군·구 지역명 (예: '서울특별시 강남구'). 실거래가 자동 조회용.",
    )


class MarketEstimate(BaseModel):
    """국토부 실거래가 API 기반 시세 추정."""
    source: str = Field(description="데이터 출처")
    region: str
    lawd_cd: Optional[str] = None
    query_ym: str = Field(description="조회 기준 년월 (YYYYMM)")
    total_count: int = 0
    median_price_krw: Optional[int] = None
    min_price_krw: Optional[int] = None
    max_price_krw: Optional[int] = None
    recent_deals: list[dict] = Field(default_factory=list)
    error: Optional[str] = None


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


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ChatCitationModel(BaseModel):
    source_type: Literal["law", "procedure", "youtube"]
    title: str
    content_snippet: str
    url: Optional[str] = None
    meta: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    mode: Literal["fallback", "azure"]
    citations: list[ChatCitationModel] = Field(default_factory=list)
    used_queries: list[str] = Field(default_factory=list)


class SafeContractResponse(BaseModel):
    extraction: RegistryExtraction
    jeontse_ratio: float = Field(description="(근저당액 + 보증금) / 시세")
    summary: str
    risks: list[RiskItem]
    referrals: list[ServiceReferral]
    disclaimer: str
    market_estimate: Optional[MarketEstimate] = Field(
        default=None,
        description="국토부 실거래가 API 자동 조회 결과 (region 제공 시)",
    )


# ---------- CODEF 등기부등본 주소 검색 ----------


class CodefRegisterSearchRequest(BaseModel):
    address: str = Field(description="조회할 주소 (지번 또는 도로명)")
    real_estate_type: str = Field(
        default="1",
        description="1=집합건물(아파트/오피스텔) 2=토지 3=건물",
    )


class CodefRegisterCandidate(BaseModel):
    unique_no: str = Field(description="등기부 고유번호 (13자리)")
    address: str = Field(description="전체 주소")
    real_estate_type: str = Field(description="토지 / 집합건물 / 건물")
    state: str = Field(description="현행 / 폐쇄 등")


class CodefRegisterSearchResponse(BaseModel):
    ok: bool
    env_mode: str = Field(description="demo / prod / unavailable")
    candidates: list[CodefRegisterCandidate] = Field(default_factory=list)
    total: int = 0
    transaction_id: Optional[str] = None
    message: Optional[str] = None
    note: str = Field(
        default="개발환경(demo) — CODEF 샘플 모드. 실 등기부 발급은 운영환경 전환 필요.",
    )
