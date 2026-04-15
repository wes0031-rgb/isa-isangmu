"""safecontract_service — rule-based 근저당 금액 파싱 + 비율 계산 회귀 테스트."""
from backend.app.models import RegistryExtraction
from backend.app.safecontract_service import (
    _compute_ratios,
    _extract_rule_based,
    _parse_korean_amount,
)


def test_parse_amount_with_cheon():
    """'2억 4천만' 형태를 정확히 파싱한다."""
    assert _parse_korean_amount("2억4천만") == 240_000_000


def test_parse_amount_pure_eok():
    """'4억' 단독도 정확히 파싱한다."""
    assert _parse_korean_amount("4억") == 400_000_000


def test_rule_based_extracts_cheon_amount():
    """근저당권설정 금액에 '천'이 포함된 경우도 under-count 되지 않는다 (regex 버그 회귀 방지)."""
    text = "근저당권설정 2025년 1월 1일 채권최고액 금 3억 5천만원 채무자 홍길동"
    result = _extract_rule_based(text)
    # 3억 5천만원 = 350,000,000 원
    assert result.mortgage_claim_amount_krw == 350_000_000


def test_rule_based_extracts_multiple_mortgages():
    """여러 건의 근저당권설정이 있을 때 합산된다."""
    text = (
        "근저당권설정 채권최고액 금 4억원\n"
        "근저당권설정 채권최고액 금 1억 2천만원\n"
    )
    result = _extract_rule_based(text)
    # 4억 + 1억 2천만 = 520,000,000 원
    assert result.mortgage_claim_amount_krw == 520_000_000


def test_rule_based_detects_seizure_and_auction():
    """가압류/임의경매 신호를 함께 감지한다."""
    text = "근저당권설정 채권최고액 금 5천만원 가압류 임의경매 개시결정"
    result = _extract_rule_based(text)
    assert result.seizure_count >= 1
    assert result.auction_in_progress is True
    assert result.mortgage_claim_amount_krw == 50_000_000


# ===== 비율 계산 회귀 테스트 =====


def test_ratios_canonical_jeontse_is_deposit_over_market():
    """전세가율은 보증금/시세 로 정의 (근저당 포함 안 됨)."""
    e = RegistryExtraction(mortgage_total_krw=0)
    jeontse, mortgage, level = _compute_ratios(e, deposit=200_000_000, market=500_000_000)
    assert jeontse == 0.4
    assert mortgage == 0.0
    assert level == "green"


def test_ratios_risky_sample():
    """RISKY 샘플: 근저당 4억(실 3.32억) + 보증금 2억 + 시세 2.5억 → red."""
    e = RegistryExtraction(mortgage_total_krw=332_000_000)
    jeontse, mortgage, level = _compute_ratios(e, deposit=200_000_000, market=250_000_000)
    assert jeontse == 0.8  # 보증금만 보면 80% (유저에게 이게 보임)
    assert mortgage == 1.328  # 근저당비율 (내부 계산, display 에서는 "근저당이 시세 초과" 텍스트)
    assert level == "red"  # 근저당+보증금 합 = 2.128 >= 1.0


def test_ratios_safe_sample():
    """SAFE 샘플: 근저당 5000만(실 4150만) + 보증금 2억 + 시세 5억 → green."""
    e = RegistryExtraction(mortgage_total_krw=41_500_000)
    jeontse, mortgage, level = _compute_ratios(e, deposit=200_000_000, market=500_000_000)
    assert jeontse == 0.4
    assert mortgage == 0.083
    assert level == "green"


def test_ratios_seizure_forces_red():
    """가압류 1건이라도 있으면 비율 안전해도 red."""
    e = RegistryExtraction(mortgage_total_krw=0, seizure_count=1)
    _, _, level = _compute_ratios(e, deposit=100_000_000, market=500_000_000)
    assert level == "red"


def test_ratios_yellow_zone_high_jeontse():
    """전세가율 80% 이상이면 yellow (근저당 없더라도)."""
    e = RegistryExtraction(mortgage_total_krw=0)
    _, _, level = _compute_ratios(e, deposit=420_000_000, market=500_000_000)
    assert level == "yellow"


def test_ratios_market_zero_returns_safe_default():
    """시세 0 이면 계산 불가 → 기본값 반환."""
    e = RegistryExtraction(mortgage_total_krw=100_000_000)
    jeontse, mortgage, level = _compute_ratios(e, deposit=100_000_000, market=0)
    assert jeontse == 0.0
    assert mortgage == 0.0
    assert level == "green"
