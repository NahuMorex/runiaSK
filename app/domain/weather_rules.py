"""Reglas de clima sobre el pronóstico ya obtenido (R-04, FR-035, FR-037). Funciones puras.

Los intervalos del pronóstico son cualquier objeto con `start` (datetime aware), `pop_pct`, `temp_c` y
`thunderstorm`, como `app.integrations.openweather.Slot`; este módulo no importa la integración.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.domain import weeks
from app.domain.models import WeatherAssessment

SLOT_LENGTH = timedelta(hours=3)
ALTERNATIVE_WINDOW_DAYS = 3

NO_ALTERNATIVE_TEXT = "No hay una alternativa disponible esta semana"
WEATHER_UNAVAILABLE_TEXT = "Clima no disponible: seguí las pautas base de ritmo e hidratación."


@dataclass(frozen=True)
class DayConditions:
    max_pop: int
    max_temp: float
    thunder: bool


def _at(day: date, minutes: int, tzinfo) -> datetime:
    return datetime.combine(day, time(), tzinfo) + timedelta(minutes=minutes)


def day_conditions(forecast_slots, day: date, range_start_min: int, range_end_min: int) -> DayConditions | None:
    """Máximos de los intervalos [start, start + 3 h) que se solapan con el rango preferido del día."""
    overlapping = []
    for s in forecast_slots:
        start, end = _at(day, range_start_min, s.start.tzinfo), _at(day, range_end_min, s.start.tzinfo)
        if s.start < end and s.start + SLOT_LENGTH > start:
            overlapping.append(s)
    if not overlapping:
        return None
    return DayConditions(
        max_pop=max(s.pop_pct for s in overlapping),
        max_temp=max(s.temp_c for s in overlapping),
        thunder=any(s.thunderstorm for s in overlapping),
    )


def is_extreme(c: DayConditions) -> bool:
    return c.max_temp > 38 or c.thunder or c.max_pop > 80


def is_unfavorable(c: DayConditions) -> bool:
    """Lluvia > 60% o temperatura > 32 °C. Una tormenta también lo es: una condición extrema
    no puede quedar sin alerta ni ser un día alternativo."""
    return c.max_pop > 60 or c.max_temp > 32 or is_extreme(c)


def _reasons(c: DayConditions) -> list[str]:
    out = []
    if c.max_pop > 60:
        out.append(f"lluvia probable ({c.max_pop}%)")
    if c.max_temp > 32:
        out.append(f"calor extremo ({math.floor(c.max_temp + 0.5)} °C)")
    if c.thunder:
        out.append("tormenta eléctrica")
    return out


def reasons_text(c: DayConditions) -> str:
    return " y ".join(_reasons(c))


def assess(forecast_slots, session_date: date, range_start_min: int, range_end_min: int) -> WeatherAssessment:
    """Si el día no tiene intervalos que cubran el rango, no hay datos para alertar y se sigue sin ajuste."""
    c = day_conditions(forecast_slots, session_date, range_start_min, range_end_min)
    if c is None or not is_unfavorable(c):
        return WeatherAssessment(available=True)

    last = min(session_date + timedelta(days=ALTERNATIVE_WINDOW_DAYS), weeks.week_end(session_date))
    alternative = None
    day = session_date + timedelta(days=1)
    while day <= last:
        alt = day_conditions(forecast_slots, day, range_start_min, range_end_min)
        if alt is not None and not is_unfavorable(alt):
            alternative = day
            break
        day += timedelta(days=1)

    extreme = is_extreme(c)
    return WeatherAssessment(
        available=True,
        unfavorable=True,
        extreme=extreme,
        reasons=_reasons(c),
        alternative_date=alternative,
        postpone=extreme and alternative is None,
    )


def unavailable() -> WeatherAssessment:
    return WeatherAssessment(available=False)


def assessment_to_dict(a: WeatherAssessment) -> dict:
    if not a.available:
        return {"available": False}
    return {
        "available": True,
        "unfavorable": a.unfavorable,
        "extreme": a.extreme,
        "reasons": list(a.reasons),
        "alternative_date": a.alternative_date.isoformat() if a.alternative_date else None,
        "postpone": a.postpone,
    }


def assessment_from_dict(d: dict) -> WeatherAssessment:
    if not d.get("available"):
        return unavailable()
    alt = d.get("alternative_date")
    return WeatherAssessment(
        available=True,
        unfavorable=bool(d.get("unfavorable")),
        extreme=bool(d.get("extreme")),
        reasons=list(d.get("reasons") or []),
        alternative_date=date.fromisoformat(alt) if alt else None,
        postpone=bool(d.get("postpone")),
    )


def postponement_message(reason: str, count_week: int) -> str:
    text = (
        f"Tu sesión de hoy quedó pospuesta por clima: {reason}. "
        "No hay un día alternativo libre de condiciones desfavorables esta semana."
    )
    if count_week >= 2:
        text += f" Esta semana ya tenés {count_week} sesiones pospuestas por clima."
    return text
