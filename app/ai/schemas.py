"""Esquemas pydantic del módulo de IA (contracts/ai-module.md)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.domain.models import DailyMessageData


class WeekSummaryIn(BaseModel):
    """FR-028: solo agregados, nunca sesiones individuales."""

    week_start: date
    is_full: bool
    is_deload: bool
    planned_volume_km: float
    completed_sessions: int
    partial_rpe7: bool


class PlanRequest(BaseModel):
    level: Literal["novato", "intermedio", "avanzado"]
    frequency: int
    target_distance_km: float
    current_pace_s: int | None
    week_start: date
    allowed_dates: list[date]
    sessions_required: int
    first_week_novice: bool
    quality_allowed: bool
    target_volume_km: float | None
    max_session_km: float | None
    is_deload: bool
    recent_weeks: list[WeekSummaryIn]


class BlockOut(BaseModel):
    kind: Literal["walk", "run"]
    distance_km: float
    target_pace_s: int | None = None
    recovery_after_s: int | None = None


class SessionOut(BaseModel):
    date: date
    title: str
    blocks: list[BlockOut]


class WeekPlanProposal(BaseModel):
    sessions: list[SessionOut]


__all__ = [
    "WeekSummaryIn",
    "PlanRequest",
    "BlockOut",
    "SessionOut",
    "WeekPlanProposal",
    "DailyMessageData",
]
