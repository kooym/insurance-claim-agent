"""
영업일 계산 (보험금 지급기한 등).
토·일 제외 + 대한민국 공휴일(주요 연도) 제외.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta

# 주요 공휴일 (ISO 날짜) — 2024~2026. 필요 시 확장.
_KR_HOLIDAYS = frozenset(
    # 2024
    "2024-01-01 2024-02-09 2024-02-10 2024-02-11 2024-02-12 "
    "2024-03-01 2024-04-10 2024-05-05 2024-05-06 2024-06-06 "
    "2024-08-15 2024-09-16 2024-09-17 2024-09-18 "
    "2024-10-03 2024-10-09 2024-12-25 "
    # 2025
    "2025-01-01 2025-01-28 2025-01-29 2025-01-30 "
    "2025-03-01 2025-03-03 2025-05-05 2025-05-06 2025-06-06 "
    "2025-08-15 2025-10-03 2025-10-05 2025-10-06 2025-10-07 2025-10-08 2025-10-09 "
    "2025-12-25 "
    # 2026
    "2026-01-01 2026-02-16 2026-02-17 2026-02-18 "
    "2026-03-01 2026-03-02 2026-05-05 2026-05-25 2026-06-03 2026-06-06 "
    "2026-08-17 2026-09-24 2026-09-25 2026-09-26 "
    "2026-10-03 2026-10-05 2026-12-25".split()
)


def _parse(s: str) -> date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def is_kr_business_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in _KR_HOLIDAYS


def add_business_days_iso(start_date_str: str, business_days: int = 3) -> str | None:
    """
    접수일(또는 기준일) 다음날부터 영업일 business_days일째 날짜를 YYYY-MM-DD로 반환.
    보험업 관행상 '접수 후 3영업일 이내' 지급 예정일 산정용.
    """
    start = _parse(start_date_str)
    if start is None or business_days < 1:
        return None
    d = start
    left = business_days
    while left > 0:
        d += timedelta(days=1)
        if is_kr_business_day(d):
            left -= 1
    return d.isoformat()


def business_days_explanation(start_date_str: str, n: int = 3) -> str:
    """직원·고객 안내용 한 줄 설명."""
    end = add_business_days_iso(start_date_str, n)
    if not end:
        return f"접수일({start_date_str}) 기준 영업일 계산 불가 — 수동 확인."
    return (
        f"접수일 {start_date_str} 기준 {n}영업일 후 지급 예정일(참고): {end} "
        f"(토·일·공휴일 제외, 상법 제732조·지급기한 기준 문서 참조)"
    )
