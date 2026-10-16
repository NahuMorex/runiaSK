"""Generación automática del lunes y fallback de AC-16 / AC-17b (FR-014, FR-027, R-13)."""

from datetime import date

from app import audit
from app.ai import AIUnavailableError
from app.clock import Clock
from app.domain import weeks
from app.domain.profile_rules import missing_field_message
from app.services import plan_service, repository

FALLBACK_NOTICE = "Generación de un nuevo plan no disponible: te enviamos tu último plan válido."
AI_UNAVAILABLE = "No es posible generar un plan en este momento."


def format_plan_summary(plan: dict) -> str:
    ws = date.fromisoformat(plan["week_start"])
    lines = [f"Tu plan de la semana del {ws:%d/%m}:"]
    for s in plan["sessions"]:
        km = f"{s['run_km']:.2f}".replace(".", ",")
        lines.append(f"- {s['weekday'].capitalize()}: {s['type']}, {km} km de trote")
    return "\n".join(lines)


async def _process_user(conn, clock: Clock, planner, notifier, user_id: int, ws: date) -> str:
    profile = repository.get_profile(conn, user_id)
    chat_id = repository.get_chat_id(conn, user_id)
    if missing_field_message(profile, chat_id is not None) is not None:
        return "skipped_incomplete"
    if repository.get_plan_for_week(conn, user_id, ws) is not None:
        return "skipped_existing"
    today = clock.now().date()
    try:
        plan_id = await plan_service.build_and_save_plan(conn, user_id, clock, planner, source="monday")
    except AIUnavailableError:
        plan_id = await plan_service.adopt_last_valid_plan(conn, user_id, clock)
        if plan_id is None:
            audit.event("plan_generation", source="monday", outcome="failed_no_previous", user_id=user_id)
            await notifier.send_message(chat_id, AI_UNAVAILABLE)
            return "failed_no_previous"
        summary = format_plan_summary(plan_service.serialize_plan(conn, plan_id, today))
        await notifier.send_message(chat_id, f"{FALLBACK_NOTICE}\n{summary}")
        return "fallback"
    await notifier.send_message(chat_id, format_plan_summary(plan_service.serialize_plan(conn, plan_id, today)))
    return "generated"


async def run_monday(conn, clock: Clock, planner, notifier) -> None:
    today = clock.now().date()
    if today.weekday() != 0:
        return
    ws = weeks.week_start(today)
    for user_id in repository.eligible_users_for_monday(conn):
        if repository.has_weekly_run(conn, user_id, ws):
            continue
        try:
            outcome = await _process_user(conn, clock, planner, notifier, user_id, ws)
        except Exception as exc:  # una falla de un usuario no corta a los demás
            audit.event("plan_generation", source="monday", outcome="error", user_id=user_id, reason=type(exc).__name__)
            outcome = "error"
        repository.record_weekly_run(conn, user_id, ws, outcome, clock.now())
