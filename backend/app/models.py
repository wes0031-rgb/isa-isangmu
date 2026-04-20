"""Pydantic request/response models for 이사이상무."""
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
    region: str = Field(
        description="시/도 시/군/구 (예: '경기도 성남시 분당구')",
        min_length=1,
        max_length=100,
    )
    move_date: date = Field(description="이사 예정일 (YYYY-MM-DD)")
    has_pet: bool = False
    has_car: bool = False
    car_count: int = 1
    has_children: bool = False
    children_count: int = 0
    children_school_level: Optional[SchoolLevel] = None
    is_foreigner: bool = False
    is_apartment: bool = Field(
        default=False,
        description="아파트·오피스텔 거주 여부 (관리사무소·우편함·주차 등록 항목 트리거)",
    )
    is_employed: bool = Field(
        default=False,
        description="재직 중 여부 (회사 인사팀 주소변경 신고 항목 트리거)",
    )
    receives_welfare: bool = Field(
        default=False,
        description="기초수급자·장애인·아동수당 등 복지급여 수급 여부 (복지급여 주소변경 항목 트리거)",
    )
    needs_id_reissue: bool = Field(
        default=False,
        description="주민등록증 재발급 필요 여부 — 10년 경과·분실·사진 변경 등",
    )
    # 범위 validation — 음수/비정상값 차단 (abuse 방지)
    deposit_krw: Optional[int] = Field(default=None, ge=0, le=50_000_000_000)
    monthly_rent_krw: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    special_concerns: list[str] = Field(default_factory=list, max_length=20)


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
    # 하한 1,000,000 원 = 100만원. 그 아래는 단위 실수 가능성 높음
    # (예: 1억을 100_000_000 대신 100 입력).
    # 사용자가 정말 보증금 100만원 미만인 경우는 거의 없으므로 sanity check.
    deposit_krw: int = Field(
        ge=1_000_000,
        le=50_000_000_000,
        description="계약 보증금 (원, 최소 100만원)",
    )
    expected_market_price_krw: int = Field(
        ge=0,
        le=50_000_000_000,
        description="해당 주택 예상 시세 (원). 0이면 region 으로 자동 조회 시도.",
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
    # 부동산 식별·표시 정보 (사용자에게 보여주는 용도)
    property_id: Optional[str] = Field(
        default=None,
        description="등기 고유번호 (예: 1102-2015-003456)",
    )
    address: Optional[str] = Field(
        default=None,
        description="건물 전체 주소 (시·구·동·번지·건물명·호수)",
    )
    area_m2: Optional[float] = Field(default=None, description="전용면적 (m²)")
    building_use: Optional[str] = Field(
        default=None,
        description="건물 용도 (예: 아파트, 다세대주택, 단독주택, 오피스텔)",
    )
    owner_name: Optional[str] = Field(default=None, description="현재 소유자 이름")
    owner_registration_front: Optional[str] = Field(
        default=None,
        description="소유자 주민등록번호 앞 6자리 (예: 800101)",
    )
    co_owner_name: Optional[str] = Field(
        default=None,
        description="[deprecated, co_owners 참조] 공유 소유자 두 번째 이름 (호환용)",
    )
    co_owners: list[str] = Field(
        default_factory=list,
        description="공유 소유자 전체 이름 리스트 (2명 이상). 본인(owner_name) 제외. 단독이면 빈 배열.",
    )
    ownership_type: Optional[str] = Field(
        default=None,
        description="소유 형태: '단독소유' 또는 '공유 1/2' 등",
    )
    special_note: Optional[str] = Field(
        default=None,
        description=(
            "특이사항 한 줄 요약 (신탁등기 / 임의경매 / 가압류 등 종합). "
            "해당 사항 없으면 null"
        ),
    )
    mortgage_creditor: Optional[str] = Field(
        default=None,
        description="근저당 채권자 (다건이면 ', ' 연결, 없으면 null)",
    )
    seizure_text: Optional[str] = Field(
        default=None,
        description="가압류 원문 요약 (예: '○○저축은행 가압류 3,000만원', 없으면 null)",
    )

    # 위험 분석용 수치 (기존 필드, 변경 금지)
    owner_change_within_2_years: int = 0
    mortgage_total_krw: int = 0
    mortgage_claim_amount_krw: int = 0
    seizure_count: int = 0
    seizure_total_krw: int = 0
    trust_registration: bool = False
    auction_in_progress: bool = False
    raw_notes: list[str] = Field(default_factory=list)

    # 추가 위험·주의 플래그 (2026-04-16)
    injunction_registered: bool = Field(
        default=False, description="가처분 등기 여부 (갑구 '가처분' 등기목적)"
    )
    provisional_registration: bool = Field(
        default=False,
        description="가등기 여부 (소유권이전청구권가등기·담보가등기 등)",
    )
    jeonse_right_registered: bool = Field(
        default=False,
        description="을구 전세권 설정 여부 (선순위 전세권자 존재)",
    )
    non_residential_use: bool = Field(
        default=False,
        description="비주거용 등재 여부 (근린생활시설·상가·사무실 등 → 주거 계약 위법 위험)",
    )
    caution_notes: list[str] = Field(
        default_factory=list,
        description=(
            "주의 단계(YELLOW) 안내 문구 리스트. 계약 자체를 피할 필요는 없지만 "
            "추가 확인·조치가 필요한 사항. 예: '공유자 전원 동의서 필수', "
            "'가등기 해제 확인 권장' 등."
        ),
    )


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


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    history: list[ChatHistoryMessage] = Field(
        default_factory=list,
        description="이전 대화 히스토리 (멀티턴 지원). 최근 N개 messages, frontend에서 제공.",
    )


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
    jeontse_ratio: float = Field(description="전세가율 = 보증금 / 시세 (0~1, 깡통전세인 경우 1 초과 가능)")
    mortgage_ratio: float = Field(default=0.0, description="근저당비율 = 근저당 실 추정액 / 시세")
    risk_level: Literal["green", "yellow", "red"] = Field(
        default="green",
        description="종합 위험도 (jeontse + mortgage 합산 기준)",
    )
    summary: str
    risks: list[RiskItem]
    referrals: list[ServiceReferral]
    disclaimer: str
    market_estimate: Optional[MarketEstimate] = Field(
        default=None,
        description="국토부 실거래가 API 자동 조회 결과 (region 제공 시)",
    )


