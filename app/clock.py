"""Reloj inyectable. Todo horario está en America/Argentina/Buenos_Aires."""

from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(TZ)


class FixedClock:
    def __init__(self, dt: datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        self._dt = dt.astimezone(TZ)

    def now(self) -> datetime:
        return self._dt

    def advance(self, delta: timedelta) -> None:
        self._dt = self._dt + delta

    def set(self, dt: datetime) -> None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        self._dt = dt.astimezone(TZ)


def today(clock: Clock) -> date:
    return clock.now().date()
