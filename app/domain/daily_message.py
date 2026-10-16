"""Mensaje diario: ajuste por fatiga, plantilla y validación del borrador del modelo (FR-030..FR-032, R-17)."""

import re

from app.domain import units, weather_rules, weeks
from app.domain.models import (
    EASY_TITLE,
    Block,
    DailyMessageData,
    WeatherAssessment,
    is_quality,
    session_type_label,
    to_easy,
)

FATIGUE_QUESTION = "¿Cómo está tu fatiga hoy del 1 al 10? Respondé con un número."
FATIGUE_RETRY = "Respondé con un número entero del 1 al 10."
FATIGUE_KEPT_EASY = "La sesión se mantiene suave por la fatiga."
HIGH_FATIGUE = 8
RECOVERY_LABEL = "suave/recuperación"
MAX_WORDS = 150

_NUMBER_RE = re.compile(r"\d+(?:[.,:]\d+)*")
_MARKDOWN_CHARS = ("*", "_", "`", "#", "[", "](")
_MARKDOWN_LINE_RE = re.compile(r"^\s*(?:>|- |\d+\. )")
_SEQ_SEP = "; "


def apply_fatigue(blocks: list[Block], title: str, fatigue: int | None) -> tuple[list[Block], str, str, bool]:
    """FR-030: con fatiga ≥ 8 la sesión del día es suave/recuperación. Solo afecta el mensaje, no el plan."""
    if fatigue is None or fatigue < HIGH_FATIGUE:
        return list(blocks), session_type_label(blocks), title, False
    if is_quality(blocks):
        return to_easy(blocks), RECOVERY_LABEL, EASY_TITLE, False
    return list(blocks), RECOVERY_LABEL, title, True


def _render_block(b: Block) -> str:
    km = units.format_km(b.distance_hm)
    if b.kind == "walk":
        text = f"caminata {km} km"
    else:
        text = f"trote {km} km"
        if b.target_pace_s is not None:
            time_s = b.target_time_s
            if time_s is None:
                time_s = units.target_time_s(b.distance_hm, b.target_pace_s)
            text += f" a {units.format_pace(b.target_pace_s)} min/km ({units.format_duration(time_s)})"
    if b.recovery_after_s is not None:
        text += f", recuperación {units.format_duration(b.recovery_after_s)}"
    return text


def render_sequence(blocks: list[Block]) -> str:
    return _SEQ_SEP.join(_render_block(b) for b in blocks)


def build_message_data(
    session: dict,
    profile: dict,
    fatigue: int | None,
    weather: WeatherAssessment | None,
    weather_unavailable: bool,
) -> DailyMessageData:
    """Datos ya decididos del mensaje. El rango sugerido es el rango preferido completo (R-17).

    `weather` es la evaluación a la hora de envío (None si no hay); `weather_unavailable`, si el servicio falló.
    """
    blocks, label, title, kept_easy = apply_fatigue(session["blocks"], session["title"], fatigue)
    pace = next((b.target_pace_s for b in blocks if b.kind == "run" and b.target_pace_s is not None), None)
    alert = weather is not None and weather.unfavorable
    alt = weather.alternative_date if alert else None
    return DailyMessageData(
        session_type_label=label,
        title=title,
        suggested_range=f"{units.format_hhmm(profile['range_start_min'])}–{units.format_hhmm(profile['range_end_min'])}",
        target_pace=f"{units.format_pace(pace)} min/km" if pace is not None else None,
        sequence=render_sequence(blocks) if blocks else None,
        weather_alert=f"Alerta climática: {' y '.join(weather.reasons)}." if alert else None,
        alternative_day=weeks.weekday_es(alt) if alt is not None else None,
        no_alternative_text=weather_rules.NO_ALTERNATIVE_TEXT if alert and alt is None else None,
        weather_unavailable_text=weather_rules.WEATHER_UNAVAILABLE_TEXT if weather_unavailable else None,
        fatigue_kept_easy_text=FATIGUE_KEPT_EASY if kept_easy else None,
    )


def _lines(data: DailyMessageData, sequence: str | None) -> list[str]:
    lines = [f"Hoy: {data.session_type_label} ({data.title}). Horario sugerido: {data.suggested_range}."]
    if sequence:
        lines.append(f"Secuencia: {sequence}.")
    if data.target_pace:
        lines.append(f"Ritmo objetivo: {data.target_pace}.")
    if data.weather_alert:
        line = data.weather_alert
        if data.alternative_day:
            line += f" Día alternativo: {data.alternative_day}."
        elif data.no_alternative_text:
            line += f" {data.no_alternative_text}."
        lines.append(line)
    if data.weather_unavailable_text:
        lines.append(data.weather_unavailable_text)
    if data.fatigue_kept_easy_text:
        lines.append(data.fatigue_kept_easy_text)
    return lines


def _fitted_sequence(data: DailyMessageData) -> str | None:
    """La secuencia completa o, si la plantilla supera 150 palabras, sus primeros bloques más "y n bloques más"."""
    if not data.sequence:
        return data.sequence
    parts = data.sequence.split(_SEQ_SEP)
    for keep in range(len(parts), 0, -1):
        seq = _SEQ_SEP.join(parts[:keep])
        if keep < len(parts):
            seq += f" y {len(parts) - keep} bloques más"
        if len("\n".join(_lines(data, seq)).split()) <= MAX_WORDS:
            return seq
    return seq


def render_template(data: DailyMessageData) -> str:
    return "\n".join(_lines(data, _fitted_sequence(data)))


def required_fragments(data: DailyMessageData) -> list[str]:
    fragments = [
        data.session_type_label,
        data.suggested_range,
        data.target_pace,
        _fitted_sequence(data),
        data.weather_alert,
        data.alternative_day,
        data.no_alternative_text,
        data.weather_unavailable_text,
        data.fatigue_kept_easy_text,
    ]
    return [f for f in fragments if f]


def _normalize_number(token: str) -> str:
    token = token.replace(".", ",")
    head, sep, rest = token.partition(":")
    return f"{int(head)}{sep}{rest}" if sep else token


def _numbers(text: str) -> set[str]:
    return {_normalize_number(n) for n in _NUMBER_RE.findall(text)}


def allowed_numbers(data: DailyMessageData) -> set[str]:
    """Los números de la plantilla, que incluye todos los campos (también los de clima)."""
    return _numbers(render_template(data))


def _has_markdown(text: str) -> bool:
    if any(c in text for c in _MARKDOWN_CHARS):
        return True
    return any(_MARKDOWN_LINE_RE.match(line) for line in text.splitlines())


def validate_draft(text: str | None, data: DailyMessageData) -> bool:
    """Las 6 reglas de R-17 (AC-78)."""
    if not text or not text.strip():
        return False
    if len(text.split()) > MAX_WORDS:
        return False
    if any(f not in text for f in required_fragments(data)):
        return False
    if not _numbers(text) <= allowed_numbers(data):
        return False
    if "?" in text or "¿" in text:
        return False
    return not _has_markdown(text)
