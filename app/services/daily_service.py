"""Flujo diario a la hora de envío: pregunta de fatiga, espera de 2 h y mensaje (FR-029..FR-032)."""

import asyncio
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable

from app import audit
from app.ai import AIUnavailableError, DailyMessageData
from app.clock import TZ, Clock
from app.domain import daily_message
from app.services import repository

Writer = Callable[[DailyMessageData], Awaitable[str]]

FATIGUE_WINDOW = timedelta(hours=2)
WRITER_TIMEOUT_S = 5
_FATIGUE_RE = re.compile(r"\d{1,2}")


def _parse_fatigue(text: str | None) -> int | None:
    text = (text or "").strip()
    if not _FATIGUE_RE.fullmatch(text):
        return None
    value = int(text)
    return value if 1 <= value <= 10 else None


async def start_dispatches(conn: sqlite3.Connection, clock: Clock, notifier, weather) -> None:
    """Crea el dispatch y pregunta la fatiga a cada usuario debido.

    `weather` es el hook de US5; por ahora no se evalúa el clima.
    """
    now = clock.now()
    today = now.date()
    for row in repository.users_due_for_dispatch(conn, today, now.hour * 60 + now.minute):
        try:
            if repository.create_dispatch(conn, row["user_id"], row["session_id"], today, now) is None:
                continue
            audit.event("tool_call", tool="db", op="create_dispatch", user_id=row["user_id"])
            await notifier.send_message(row["chat_id"], daily_message.FATIGUE_QUESTION)
        except Exception as exc:  # la falla de un usuario no corta a los demás
            audit.event("daily_dispatch_error", user_id=row["user_id"], reason=type(exc).__name__)


async def handle_fatigue_reply(
    conn: sqlite3.Connection, clock: Clock, notifier, writer: Writer | None, chat_id: int, text: str
) -> str | None:
    """Devuelve el texto que el adaptador tiene que responder (solo FATIGUE_RETRY) o None."""
    now = clock.now()
    dispatch = repository.get_open_dispatch_by_chat(conn, chat_id, now.date())
    if dispatch is None or now - datetime.fromisoformat(dispatch["asked_at"]) >= FATIGUE_WINDOW:
        return None
    fatigue = _parse_fatigue(text)
    if fatigue is None:
        return daily_message.FATIGUE_RETRY
    await compose_and_send(conn, clock, notifier, writer, dispatch, fatigue)
    return None


async def expire_waits(conn: sqlite3.Connection, clock: Clock, notifier, writer: Writer | None) -> None:
    """Envía sin ajuste por fatiga los dispatches cuya espera de 2 h terminó."""
    cutoff = (clock.now() - FATIGUE_WINDOW).astimezone(TZ).isoformat(timespec="seconds")
    for dispatch in repository.expired_dispatches(conn, cutoff):
        try:
            await compose_and_send(conn, clock, notifier, writer, dispatch, None)
        except Exception as exc:
            audit.event("daily_dispatch_error", user_id=dispatch["user_id"], reason=type(exc).__name__)


async def _draft(writer: Writer | None, data: DailyMessageData) -> str | None:
    """Borrador del modelo, o None si falla, tarda más de 5 s o no pasa la validación (AC-78, AC-79)."""
    if writer is None:
        return None
    try:
        text = await asyncio.wait_for(writer(data), WRITER_TIMEOUT_S)
    except TimeoutError:
        audit.event("external_error", service="gemini", reason="timeout")
        return None
    except AIUnavailableError as exc:
        audit.event("external_error", service="gemini", reason=exc.reason)
        return None
    except Exception as exc:
        audit.event("external_error", service="gemini", reason="error", detail=type(exc).__name__)
        return None
    if not daily_message.validate_draft(text, data):
        audit.event("external_error", service="gemini", reason="invalid_draft")
        return None
    return text


async def compose_and_send(
    conn: sqlite3.Connection, clock: Clock, notifier, writer: Writer | None, dispatch, fatigue: int | None
) -> None:
    """Arma el mensaje (modelo validado o plantilla) y lo envía una sola vez, sin reintentos.

    El ajuste por fatiga solo cambia el mensaje, no la sesión guardada (FR-030).
    """
    if not repository.claim_dispatch(conn, dispatch["id"], fatigue):
        return
    user_id = dispatch["user_id"]
    session = repository.get_session_for_user_on(conn, user_id, date.fromisoformat(dispatch["date"]))
    profile = repository.get_profile(conn, user_id)
    data = daily_message.build_message_data(session, profile, fatigue, None, False)

    text = await _draft(writer, data)
    used_template = text is None
    if used_template:
        text = daily_message.render_template(data)

    chat_id = repository.get_chat_id(conn, user_id)
    delivered = bool(chat_id is not None and await notifier.send_message(chat_id, text))
    repository.set_dispatch_sent(conn, dispatch["id"], fatigue, used_template, delivered, clock.now())
    audit.event("tool_call", tool="db", op="set_dispatch_sent", user_id=user_id)
    audit.event("message_sent", template=used_template, user_id=user_id, delivered=delivered)
