"""Orquesta el plan: precondiciones → IA → estructura → guardarraíles → persistencia."""

import sqlite3
from dataclasses import asdict
from datetime import date, timedelta
from typing import Awaitable, Callable

from app import audit
from app.ai import AIUnavailableError, PlanRequest, WeekPlanProposal, WeekSummaryIn
from app.clock import Clock
from app.db import transaction
from app.domain import guardrails, summaries, units, weeks
from app.domain.models import Block, PlannedSession, run_volume_hm, session_type_label
from app.domain.profile_rules import missing_field_message
from app.domain.structure import InvalidProposalError, validate_proposal
from app.services import repository

Planner = Callable[[PlanRequest], Awaitable[WeekPlanProposal]]

RESULT_LABELS = {"completed": "Completada", "partial": "Parcial/Cortada", "skipped": "Salteada"}


class IncompleteProfileError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PlanExistsError(Exception):
    pass


def _load_context(conn, user_id: int, profile: dict, ws: date, start_date: date):
    plans, sessions, results = repository.history_rows_for_summaries(conn, user_id, ws)
    history = summaries.summarize_weeks(plans, sessions, results)
    pending = repository.get_pending_reclass(conn, user_id)
    ctx = summaries.build_context(profile, history, ws, start_date, pending)
    return history, ctx


def _audit_guardrails(user_id: int, events) -> None:
    for e in events:
        audit.event("guardrail", user_id=user_id, **asdict(e))


def _target_volume_hm(ctx) -> int | None:
    if ctx.is_deload and ctx.deload_v4_hm is not None:
        return ctx.deload_v4_hm * 3 // 4
    cap = guardrails.weekly_cap(ctx)
    return cap[0] if cap else None


def build_plan_request(profile: dict, history, ctx, start_date: date) -> PlanRequest:
    target = _target_volume_hm(ctx)
    return PlanRequest(
        level=profile["level"],
        frequency=profile["frequency"],
        target_distance_km=units.hm_to_km(profile["target_distance_hm"]),
        current_pace_s=profile.get("current_pace_s"),
        week_start=ctx.week_start,
        allowed_dates=weeks.allowed_dates(start_date),
        sessions_required=weeks.sessions_required(profile["frequency"], start_date),
        first_week_novice=summaries.first_week_novice(profile["level"], history),
        quality_allowed=ctx.novice_quality_allowed,
        target_volume_km=units.hm_to_km(target) if target is not None else None,
        max_session_km=units.hm_to_km(guardrails.session_cap(ctx)[0]),
        is_deload=ctx.is_deload,
        recent_weeks=[
            WeekSummaryIn(
                week_start=s.week_start,
                is_full=s.is_full,
                is_deload=s.is_deload,
                planned_volume_km=units.hm_to_km(s.planned_volume_hm),
                completed_sessions=s.completed_count,
                partial_rpe7=s.has_partial_rpe7,
            )
            for s in summaries.recent_summaries_for_ai(history)
        ],
    )


def _save(conn, user_id, ctx, profile, sessions, *, source, adopted_from_plan_id, clock, op) -> int:
    volume = guardrails.planned_volume_hm(sessions)
    try:
        with transaction(conn):
            if repository.get_plan_for_week(conn, user_id, ctx.week_start) is not None:
                raise PlanExistsError()
            plan_id = repository.save_plan(
                conn,
                user_id,
                week_start=ctx.week_start,
                start_date=ctx.start_date,
                is_full=ctx.is_full,
                is_deload=ctx.is_deload,
                is_post_deload=ctx.is_post_deload,
                source=source,
                adopted_from_plan_id=adopted_from_plan_id,
                planned_volume_hm=volume,
                profile_snapshot=summaries.profile_snapshot(profile),
                sessions=sessions,
                now=clock.now(),
            )
            repository.consume_pending_reclass(conn, user_id)
    except sqlite3.IntegrityError:
        raise PlanExistsError() from None
    audit.event("tool_call", tool="db", op=op, user_id=user_id, plan_id=plan_id)
    audit.event("plan_generation", source=source, outcome="created", user_id=user_id, planned_volume_hm=volume)
    return plan_id


async def build_and_save_plan(conn, user_id: int, clock: Clock, planner: Planner, *, source: str) -> int:
    profile = repository.get_profile(conn, user_id)
    linked = repository.get_chat_id(conn, user_id) is not None
    message = missing_field_message(profile, linked)
    if message is not None:
        raise IncompleteProfileError(message)

    today = clock.now().date()
    ws = weeks.week_start(today)
    if repository.get_plan_for_week(conn, user_id, ws) is not None:
        raise PlanExistsError()

    history, ctx = _load_context(conn, user_id, profile, ws, today)
    req = build_plan_request(profile, history, ctx, today)

    try:
        proposal = await planner(req)
        proposed = validate_proposal(
            proposal,
            start_date=today,
            sessions_required=req.sessions_required,
            first_week_novice=req.first_week_novice,
        )
    except InvalidProposalError as exc:
        audit.event("plan_generation", source=source, outcome="failed", reason="invalid_structure", detail=exc.reason)
        raise AIUnavailableError("invalid_structure", exc.reason) from exc
    except AIUnavailableError as exc:
        audit.event("plan_generation", source=source, outcome="failed", reason=exc.reason)
        raise

    sessions, events = guardrails.apply(proposed, ctx)
    plan_id = _save(conn, user_id, ctx, profile, sessions, source=source, adopted_from_plan_id=None, clock=clock, op="save_plan")
    _audit_guardrails(user_id, events)
    return plan_id


async def adopt_last_valid_plan(conn, user_id: int, clock: Clock) -> int | None:
    """R-13: mismos días de la semana y bloques del último plan, con los guardarraíles de la semana actual."""
    last = repository.get_last_plan(conn, user_id)
    if last is None:
        return None
    profile = repository.get_profile(conn, user_id)
    ws = weeks.week_start(clock.now().date())
    _, ctx = _load_context(conn, user_id, profile, ws, ws)

    mapped = [
        PlannedSession(
            date=ws + timedelta(days=s["date"].weekday()),
            title=s["title"],
            blocks=[Block(b.kind, b.distance_hm, b.target_pace_s, None, b.recovery_after_s) for b in s["blocks"]],
        )
        for s in last["sessions"]
    ]
    sessions, events = guardrails.apply(mapped, ctx)
    plan_id = _save(
        conn, user_id, ctx, profile, sessions, source="fallback", adopted_from_plan_id=last["id"], clock=clock, op="adopt_plan"
    )
    _audit_guardrails(user_id, events)
    return plan_id


def status_label(session: dict, result: dict | None, today: date) -> str:
    """R-19."""
    if result is not None:
        return RESULT_LABELS[result["status"]]
    if session.get("system_status") == "postponed_weather":
        return "Pospuesta por clima"
    d = session["date"]
    if d < today:
        return "Sin registrar"
    if d == today:
        return "Hoy"
    return "Proyectada"


def serialize_block(b: Block) -> dict:
    out = {"kind": "trote" if b.kind == "run" else "caminata", "distance_km": units.hm_to_km(b.distance_hm)}
    if b.target_pace_s is not None:
        out["target_pace"] = units.format_pace(b.target_pace_s)
    if b.target_time_s is not None:
        out["target_time"] = units.format_duration(b.target_time_s)
    if b.recovery_after_s is not None:
        out["recovery_after"] = units.format_duration(b.recovery_after_s)
    return out


def serialize_session(s: dict, today: date, *, include_result: bool = False) -> dict:
    out = {
        "id": s["id"],
        "date": s["date"].isoformat(),
        "weekday": weeks.weekday_es(s["date"]),
        "title": s["title"],
        "type": session_type_label(s["blocks"]),
        "run_km": units.hm_to_km(run_volume_hm(s["blocks"])),
        "status": status_label(s, s["result"], today),
        "blocks": [serialize_block(b) for b in s["blocks"]],
    }
    if include_result:
        out["result"] = s["result"]
    return out


def serialize_plan(conn, plan_id: int, today: date, *, include_result: bool = False) -> dict:
    plan = repository.get_plan(conn, plan_id)
    return {
        "id": plan["id"],
        "week_start": plan["week_start"],
        "start_date": plan["start_date"],
        "is_full": bool(plan["is_full"]),
        "is_deload": bool(plan["is_deload"]),
        "planned_volume_km": units.hm_to_km(plan["planned_volume_hm"]),
        "sessions": [
            serialize_session(s, today, include_result=include_result)
            for s in repository.get_plan_sessions(conn, plan_id)
        ],
    }


def serialize_history_item(row: dict, today: date) -> dict:
    """`HistoryItem` de contracts/api.md."""
    result = row["result"]
    return {
        "session_id": row["id"],
        "date": row["date"].isoformat(),
        "title": row["title"],
        "type": session_type_label(row["blocks"]),
        "run_km": units.hm_to_km(run_volume_hm(row["blocks"])),
        "status": status_label(row, result, today),
        "rpe": result["rpe"] if result else None,
        "notes": result["notes"] if result else None,
    }
