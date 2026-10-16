"""Interfaz pública del módulo de IA (principio I). El resto del sistema importa solo desde acá."""

from app.ai.errors import AIUnavailableError
from app.ai.gemini import draft_daily_message, propose_week_plan
from app.ai.schemas import (
    BlockOut,
    DailyMessageData,
    PlanRequest,
    SessionOut,
    WeekPlanProposal,
    WeekSummaryIn,
)

__all__ = [
    "AIUnavailableError",
    "BlockOut",
    "DailyMessageData",
    "PlanRequest",
    "SessionOut",
    "WeekPlanProposal",
    "WeekSummaryIn",
    "draft_daily_message",
    "propose_week_plan",
]
