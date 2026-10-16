"""Registro del resultado de la sesión del día, compartido por la API y el bot (R-08, FR-040..FR-042)."""

import sqlite3
from datetime import date

from app import audit
from app.clock import Clock
from app.db import transaction
from app.domain import reclassification
from app.domain.models import EASY_TITLE, is_quality, reclassify, run_volume_hm, session_type_label
from app.services import repository

STATUSES = ("completed", "partial", "skipped")


class SessionNotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class PostponedSession(Exception):
    pass


class NotToday(Exception):
    pass


class AlreadyRegistered(Exception):
    pass


class InvalidRpe(Exception):
    pass


def _valid_rpe(status: str, rpe) -> bool:
    if status == "skipped":
        return rpe is None
    return isinstance(rpe, int) and not isinstance(rpe, bool) and 1 <= rpe <= 10


def _summary(session: dict) -> dict:
    return {
        "title": session["title"],
        "type": session_type_label(session["blocks"]),
        "run_hm": run_volume_hm(session["blocks"]),
        "blocks": len(session["blocks"]),
    }


def _reclassify_after(conn, user_id: int, session_date: date) -> tuple[list[int], int]:
    """FR-042: las 2 sesiones siguientes pasan a suave; las que falten quedan pendientes para el plan siguiente."""
    ids, remaining = reclassification.targets_after(session_date, repository.upcoming_sessions(conn, user_id, session_date))
    for sid in ids:
        target = repository.get_session(conn, sid)
        title = EASY_TITLE if is_quality(target["blocks"]) else target["title"]
        blocks = reclassify(target["blocks"])
        repository.replace_session_blocks(conn, sid, blocks, title, reclassified=True)
        audit.event(
            "guardrail",
            user_id=user_id,
            rule="reclassification",
            scope="session",
            session_date=target["date"],
            before=_summary(target),
            after=_summary({**target, "title": title, "blocks": blocks}),
        )
    if remaining:
        before = repository.get_pending_reclass(conn, user_id)
        repository.upsert_pending_reclass(conn, user_id, remaining)
        audit.event(
            "guardrail",
            user_id=user_id,
            rule="reclassification",
            scope="week",
            session_date=None,
            before={"pending": before},
            after={"pending": repository.get_pending_reclass(conn, user_id)},
        )
    return ids, remaining


def register_result(
    conn: sqlite3.Connection,
    user_id: int,
    session_id: int,
    status: str,
    rpe: int | None,
    notes: str | None,
    today: date,
    clock: Clock,
) -> dict:
    """Valida en el orden del contrato: existe → es del usuario → no está pospuesta → es de hoy →
    no tiene registro → el RPE es válido."""
    outcome = "error"
    try:
        with transaction(conn):
            session = repository.get_session(conn, session_id)
            if session is None:
                outcome = "not_found"
                raise SessionNotFound()
            if session["user_id"] != user_id:
                outcome = "forbidden"
                raise Forbidden()
            if session["system_status"] == "postponed_weather":
                outcome = "postponed"
                raise PostponedSession()
            if session["date"] != today:
                outcome = "not_today"
                raise NotToday()
            if repository.get_result(conn, session_id) is not None:
                outcome = "already_registered"
                raise AlreadyRegistered()
            if status not in STATUSES or not _valid_rpe(status, rpe):
                outcome = "invalid_rpe"
                raise InvalidRpe()

            repository.insert_result(conn, session_id, user_id, status, rpe, notes, clock.now())
            reclassified, pending = [], 0
            if reclassification.triggers(status, rpe):
                reclassified, pending = _reclassify_after(conn, user_id, session["date"])
            outcome = "ok"
    finally:
        audit.event("tool_call", tool="db", op="register_result", user_id=user_id, outcome=outcome)
    return {
        "session_id": session_id,
        "status": status,
        "rpe": rpe,
        "notes": notes,
        "reclassified_sessions": reclassified,
        "pending_reclassification": pending,
    }
