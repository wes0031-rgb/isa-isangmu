"""date_utils — 공휴일 인식 D-day 계산."""
from datetime import date

from backend.app.date_utils import (
    compute_deadline,
    compute_start_date,
    is_business_day,
    load_holidays,
    next_business_day,
    prev_business_day,
)


def test_load_holidays_has_entries():
    """2026 공휴일 파일이 존재하고 최소 20건 이상 로드되어야 함."""
    holidays = load_holidays()
    assert len(holidays) >= 20
    # 2026-01-01 (신정) 은 반드시 포함
    assert date(2026, 1, 1) in holidays


def test_is_business_day_weekend():
    """토·일요일은 영업일 아님."""
    assert is_business_day(date(2026, 5, 2)) is False  # Sat
    assert is_business_day(date(2026, 5, 3)) is False  # Sun


def test_is_business_day_weekday_non_holiday():
    """평일은 영업일."""
    assert is_business_day(date(2026, 5, 4)) is True  # Mon


def test_is_business_day_holiday():
    """공휴일은 영업일 아님."""
    holidays = load_holidays()
    # 공휴일 중 아무거나 하나
    sample = next(iter(holidays))
    assert is_business_day(sample) is False


def test_next_business_day_skips_weekend():
    """금요일에서 +1일 요청 → 월요일로 밀려야 함."""
    fri = date(2026, 5, 1)
    sat = fri + __import__("datetime").timedelta(days=1)
    mon = next_business_day(sat)
    # 월요일(5/4) 또는 그 이후가 나와야 함
    assert mon.weekday() < 5
    assert mon >= date(2026, 5, 4)


def test_compute_start_date_pushes_past_weekend():
    """이사일 = 금요일(5/1), d_day +1 → 토요일 → 월요일(5/4)."""
    move = date(2026, 5, 1)  # Friday
    start = compute_start_date(move, 1)
    assert start.weekday() < 5  # 평일


def test_compute_start_date_negative_offset_shifts_past():
    """이사 전(음수 offset) 항목이 주말이면 이전 평일로 밀려야 함.

    이전엔 next_business_day(이사일 방향) 로 잘못 밀어서 '이사 2일 전' 항목이
    이사 당일에 표시되는 버그. 이제 prev_business_day(과거 방향) 로 정정.
    """
    # 이사일 월요일(5/4) - 2일 = 토(5/2) → 금(5/1) 이어야 함 (이전 평일)
    move = date(2026, 5, 4)
    start = compute_start_date(move, -2)
    assert start == date(2026, 5, 1)
    # 이사일 월요일 - 1일 = 일 → 금(5/1)
    assert compute_start_date(move, -1) == date(2026, 5, 1)


def test_prev_business_day_skips_weekend():
    """일요일(5/3)에서 이전 평일 → 금요일(5/1)."""
    sun = date(2026, 5, 3)
    assert prev_business_day(sun) == date(2026, 5, 1)


def test_compute_deadline_no_shift():
    """법정 기한은 그대로 더하기만 함 (공휴일 보정 없음)."""
    move = date(2026, 5, 1)
    assert compute_deadline(move, 14) == date(2026, 5, 15)
    assert compute_deadline(move, 30) == date(2026, 5, 31)
