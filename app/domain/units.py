"""Unidades y redondeos (R-07). Distancias en centésimas de km (hm), ritmos y tiempos en segundos."""

import math
import re
from fractions import Fraction

_PACE_RE = re.compile(r"^(\d{1,2}):([0-5]\d)$")
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def km_to_hm(km: float) -> int:
    return round(km * 100)


def hm_to_km(hm: int) -> float:
    return hm / 100


def format_km(hm: int) -> str:
    return f"{hm // 100},{hm % 100:02d}"


def parse_pace(text: str) -> int:
    m = _PACE_RE.match(text.strip()) if isinstance(text, str) else None
    if not m:
        raise ValueError(f"ritmo inválido: {text!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def format_pace(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def parse_hhmm(text: str) -> int:
    m = _HHMM_RE.match(text.strip()) if isinstance(text, str) else None
    if not m:
        raise ValueError(f"horario inválido: {text!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def format_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_duration(seconds: int) -> str:
    if seconds >= 3600:
        h, rest = divmod(seconds, 3600)
        return f"{h}:{rest // 60:02d}:{rest % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


def scale_floor(hm: int, factor: Fraction) -> int:
    return math.floor(hm * Fraction(factor))


def round_half_up_div(num: int, den: int) -> int:
    return (2 * num + den) // (2 * den)


def target_time_s(hm: int, pace_s: int) -> int:
    return round_half_up_div(hm * pace_s, 100)


def fast_pace_limit(pace_s: int) -> int:
    """ceil(pace × 0,944), redondeado hacia el lado lento: 360 → 340."""
    return -((-pace_s * 944) // 1000)
