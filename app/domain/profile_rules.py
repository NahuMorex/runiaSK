"""Validación del perfil y completitud (FR-005, FR-006, FR-012, R-20)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain import units


class ProfileValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class TimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str
    end: str


class ProfileUpdate(BaseModel):
    """Todos los campos son opcionales; `null` solo se acepta en `current_pace`."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["novato", "intermedio", "avanzado"] | None = None
    frequency: int | None = None
    target_distance_km: float | None = None
    current_pace: str | None = None
    city: str | None = None
    preferred_range: TimeRange | None = None
    send_time: str | None = None


def merge_and_validate(stored: dict, update: ProfileUpdate) -> dict:
    """Combina el PUT parcial con el perfil guardado y valida el resultado en unidades internas."""
    errors: list[str] = []
    result = dict(stored)
    sent = update.model_fields_set

    for name in sent - {"current_pace"}:
        if getattr(update, name) is None:
            errors.append(f"{name}: no admite null")

    if "level" in sent and update.level is not None:
        result["level"] = update.level

    if "frequency" in sent and update.frequency is not None:
        if 1 <= update.frequency <= 7:
            result["frequency"] = update.frequency
        else:
            errors.append("frequency: debe ser un entero de 1 a 7")

    if "target_distance_km" in sent and update.target_distance_km is not None:
        hm = units.km_to_hm(update.target_distance_km)
        if 100 <= hm <= 4220 and 1 <= update.target_distance_km <= 42.2:
            result["target_distance_hm"] = hm
        else:
            errors.append("target_distance_km: debe estar entre 1 y 42,2 km")

    if "current_pace" in sent:
        if update.current_pace is None:
            result["current_pace_s"] = None
        else:
            try:
                pace = units.parse_pace(update.current_pace)
            except ValueError:
                errors.append("current_pace: formato mm:ss inválido")
            else:
                if 180 <= pace <= 600:
                    result["current_pace_s"] = pace
                else:
                    errors.append("current_pace: debe estar entre 3:00 y 10:00")

    if "city" in sent and update.city is not None:
        city = update.city.strip()
        if 1 <= len(city) <= 100:
            result["city"] = city
        else:
            errors.append("city: debe tener entre 1 y 100 caracteres")

    if "preferred_range" in sent and update.preferred_range is not None:
        try:
            start = units.parse_hhmm(update.preferred_range.start)
            end = units.parse_hhmm(update.preferred_range.end)
        except ValueError:
            errors.append("preferred_range: formato HH:MM inválido")
        else:
            result["range_start_min"] = start
            result["range_end_min"] = end

    if "send_time" in sent and update.send_time is not None:
        try:
            result["send_time_min"] = units.parse_hhmm(update.send_time)
        except ValueError:
            errors.append("send_time: formato HH:MM inválido")

    start, end, send = result.get("range_start_min"), result.get("range_end_min"), result.get("send_time_min")
    if start is not None and end is not None:
        if start >= end:
            errors.append("preferred_range: el inicio debe ser anterior al fin")
        elif end - start < 60:
            errors.append("preferred_range: la duración mínima es 1 hora")
    if send is not None and end is not None and send >= end:
        errors.append("send_time: debe ser anterior al fin del rango horario")

    if errors:
        raise ProfileValidationError(errors)
    return result


def to_public(profile: dict, linked: bool) -> dict:
    hm = profile.get("target_distance_hm")
    pace = profile.get("current_pace_s")
    start, end = profile.get("range_start_min"), profile.get("range_end_min")
    send = profile.get("send_time_min")
    return {
        "level": profile.get("level"),
        "frequency": profile.get("frequency"),
        "target_distance_km": units.hm_to_km(hm) if hm is not None else None,
        "current_pace": units.format_pace(pace) if pace is not None else None,
        "city": profile.get("city"),
        "preferred_range": (
            {"start": units.format_hhmm(start), "end": units.format_hhmm(end)}
            if start is not None and end is not None
            else None
        ),
        "send_time": units.format_hhmm(send) if send is not None else None,
        "telegram_linked": linked,
    }


def missing_field_message(profile: dict, linked: bool) -> str | None:
    """Primer dato faltante para generar un plan, en el orden de data-model.md (FR-012)."""
    checks = [
        ("level", "nivel"),
        ("frequency", "frecuencia"),
        ("target_distance_hm", "distancia objetivo"),
    ]
    for key, name in checks:
        if profile.get(key) is None:
            return f"No hay datos sobre tu {name} cargados en tu perfil"
    if profile.get("level") != "novato" and profile.get("current_pace_s") is None:
        return "No hay datos sobre tu ritmo cargados en tu perfil"
    if not profile.get("city"):
        return "No hay datos sobre tu ciudad cargados en tu perfil"
    if profile.get("range_start_min") is None or profile.get("range_end_min") is None:
        return "No hay datos sobre tu rango horario cargados en tu perfil"
    if profile.get("send_time_min") is None:
        return "No hay datos sobre tu hora de envío cargados en tu perfil"
    if not linked:
        return "Tu cuenta no tiene un chat de Telegram vinculado"
    return None
