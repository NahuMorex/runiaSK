"""Semanas lunes-domingo (R-11, FR-016)."""

from datetime import date, timedelta

WEEKDAY_NAMES_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_end(d: date) -> date:
    return week_start(d) + timedelta(days=6)


def remaining_days(d: date) -> int:
    return 7 - d.weekday()


def sessions_required(frequency: int, start_date: date) -> int:
    if start_date.weekday() == 0:
        return frequency
    return min(frequency, remaining_days(start_date))


def allowed_dates(start_date: date) -> list[date]:
    return [start_date + timedelta(days=i) for i in range(remaining_days(start_date))]


def is_closed(ws: date, today: date) -> bool:
    return ws + timedelta(days=6) < today


def previous_week_start(ws: date) -> date:
    return ws - timedelta(days=7)


def weekday_es(d: date) -> str:
    return WEEKDAY_NAMES_ES[d.weekday()]
