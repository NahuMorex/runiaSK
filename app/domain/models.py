"""Entidades de dominio sin I/O (data-model.md, "Entidades de dominio sin tabla")."""

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Literal

from pydantic import BaseModel

EASY_TITLE = "Trote suave"
QUALITY_TITLE = "Calidad"


@dataclass(frozen=True)
class Block:
    kind: Literal["walk", "run"]
    distance_hm: int
    target_pace_s: int | None = None
    target_time_s: int | None = None
    recovery_after_s: int | None = None


@dataclass(frozen=True)
class PlannedSession:
    date: date
    title: str
    blocks: list[Block]
    reclassified: bool = False

    def with_(self, **changes) -> "PlannedSession":
        return replace(self, **changes)


@dataclass(frozen=True)
class WeekSummary:
    week_start: date
    has_plan: bool
    is_full: bool
    is_deload: bool
    planned_volume_hm: int
    completed_count: int
    has_partial_rpe7: bool
    profile_snapshot: dict | None
    is_post_deload: bool = False


@dataclass(frozen=True)
class GuardrailEvent:
    rule: str
    scope: Literal["session", "week"]
    session_date: date | None
    before: object
    after: object
    reason: str | None = None  # regla concreta de un tope: initial_cap, target_distance, ten_percent, …


@dataclass
class GuardrailContext:
    level: Literal["novato", "intermedio", "avanzado"]
    frequency: int
    target_distance_hm: int
    current_pace_s: int | None
    start_date: date
    week_start: date
    is_full: bool
    is_deload: bool = False
    is_post_deload: bool = False
    initial_caps: bool = True
    base_10_hm: int | None = None
    no_increase_hm: int | None = None
    deload_v4_hm: int | None = None
    post_deload_target_hm: int | None = None
    floor_prev_hm: int | None = None
    novice_quality_allowed: bool = False
    pending_reclass: int = 0


@dataclass(frozen=True)
class WeatherAssessment:
    available: bool
    unfavorable: bool = False
    extreme: bool = False
    reasons: list[str] = field(default_factory=list)
    alternative_date: date | None = None
    postpone: bool = False


class DailyMessageData(BaseModel):
    """Datos ya decididos por el código determinista (contracts/ai-module.md)."""

    session_type_label: str
    title: str
    suggested_range: str
    target_pace: str | None = None
    sequence: str | None = None
    weather_alert: str | None = None
    alternative_day: str | None = None
    no_alternative_text: str | None = None
    weather_unavailable_text: str | None = None
    fatigue_kept_easy_text: str | None = None


def run_volume_hm(blocks: list[Block]) -> int:
    return sum(b.distance_hm for b in blocks if b.kind == "run")


def is_quality(blocks: list[Block]) -> bool:
    return any(b.kind == "run" and b.target_pace_s is not None for b in blocks)


def session_type_label(blocks: list[Block]) -> Literal["calidad", "suave"]:
    return "calidad" if is_quality(blocks) else "suave"


def to_easy(blocks: list[Block]) -> list[Block]:
    """Un único bloque de trote con los km de trote totales, sin ritmo, tiempo ni recuperación (R-12)."""
    return [Block("run", run_volume_hm(blocks))]


def reclassify(blocks: list[Block]) -> list[Block]:
    """FR-042: solo convierte las sesiones de calidad; las suaves quedan igual."""
    return to_easy(blocks) if is_quality(blocks) else list(blocks)
