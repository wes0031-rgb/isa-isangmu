"""safecontract_service — rule-based 근저당 금액 파싱 회귀 테스트."""
from backend.app.safecontract_service import _extract_rule_based, _parse_korean_amount


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
