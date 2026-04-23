"""D-day calculation with public holiday awareness."""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "holidays_2026.json"


@lru_cache(maxsize=1)
def load_holidays() -> set[date]:
    if not HOLIDAYS_FILE.exists():
        return set()
    data = json.loads(HOLIDAYS_FILE.read_text(encoding="utf-8"))
    out = set()
    for rec in data.get("holidays", []):
        iso = rec.get("date")
        if iso and rec.get("is_holiday"):
            y, m, d = iso.split("-")
            out.add(date(int(y), int(m), int(d)))
    return out


def is_business_day(d: date) -> bool:
    if d.weekday() >= 5:  # Sat/Sun
        return False
    if d in load_holidays():
        return False
    return True


def next_business_day(d: date) -> date:
    cur = d
    while not is_business_day(cur):
        cur += timedelta(days=1)
    return cur


def prev_business_day(d: date) -> date:
    cur = d
    while not is_business_day(cur):
        cur -= timedelta(days=1)
    return cur


def compute_start_date(move_date: date, d_day_offset: int) -> date:
    """이사일 기준 오프셋만큼 이동. 공휴일/주말이면 평일로 밀어줌.

    이동 방향:
      - 양수 offset (이사 후): 다음 평일 (예: 이사 2일 후가 일요일이면 월요일)
      - 음수 offset (이사 전): 이전 평일 (예: 이사 2일 전이 토요일이면 금요일).
        next_business_day 로 밀면 이사일 방향으로 가서 항목이 이사 당일·이후에
        표시되어 사용자 혼란 + 실효성 0.
      - 0 (이사 당일): 주말/공휴일이어도 그대로 (사용자가 정한 날짜 유지).
    """
    raw = move_date + timedelta(days=d_day_offset)
    if d_day_offset == 0:
        return raw
    if d_day_offset > 0:
        return next_business_day(raw)
    return prev_business_day(raw)


def compute_deadline(move_date: date, deadline_days: int) -> date:
    """법정 기한(전입신고 14일 등)을 이사일 기준 절대 날짜로 변환.

    주의: 법정 기한은 공휴일을 연장하는 경우도 있고 아닌 경우도 있음.
    MVP에서는 기한 자체는 그대로 두고 별도 경고로 표시.
    """
    return move_date + timedelta(days=deadline_days)
