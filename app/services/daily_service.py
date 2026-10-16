"""Flujo diario a la hora de envío: pregunta de fatiga, espera de 2 h y mensaje (FR-029..FR-032)."""

import asyncio
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable

from app import audit
from app.ai import AIUnavailableError, DailyMessageData
from app.clock import TZ, Clock
from app.domain import daily_message, weather_rules, weeks
from app.domain.models import WeatherAssessment
from app.integrations.openweather import WeatherUnavailableError
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


async def _assess_weather(weather, user_id: int, profile: dict, today: date) -> WeatherAssessment | None:
    """Evaluación climática con la ciudad y el rango vigentes (FR-034, AC-71). None si no hay servicio inyectado."""
    if weather is None:
        return None
    try:
        forecast = await weather.fetch_forecast(profile["city"])
    except WeatherUnavailableError as exc:
        audit.event("external_error", service="openweather", reason=exc.reason, user_id=user_id)
        return weather_rules.unavailable()
    except Exception as exc:
        audit.event("external_error", service="openweather", reason="error", detail=type(exc).__name__, user_id=user_id)
        return weather_rules.unavailable()
    assessment = weather_rules.assess(forecast.slots, today, profile["range_start_min"], profile["range_end_min"])
    audit.event(
        "weather_decision",
        user_id=user_id,
        unfavorable=assessment.unfavorable,
        extreme=assessment.extreme,
        alternative=assessment.alternative_date,
        postpone=assessment.postpone,
    )
    return assessment


async def _postpone(conn: sqlite3.Connection, now: datetime, notifier, row, assessment: WeatherAssessment) -> None:
    """FR-037, FR-038: la sesión queda pospuesta y se envía un único aviso, sin pregunta de fatiga."""
    user_id = row["user_id"]
    reason = " y ".join(assessment.reasons)
    repository.set_session_postponed(conn, row["session_id"], reason)
    audit.event("tool_call", tool="db", op="set_session_postponed", user_id=user_id)
    count = repository.count_postponed_in_week(conn, user_id, weeks.week_start(now.date()))
    audit.event("session_postponed", user_id=user_id, session_id=row["session_id"], reason=reason, count_week=count)
    delivered = bool(await notifier.send_message(row["chat_id"], weather_rules.postponement_message(reason, count)))
    dispatch_id = repository.create_dispatch(
        conn, user_id, row["session_id"], now.date(), now, state="postponed_sent", delivered=delivered
    )
    audit.event("tool_call", tool="db", op="create_dispatch", user_id=user_id)
    if dispatch_id is not None:
        repository.set_dispatch_weather(conn, dispatch_id, weather_rules.assessment_to_dict(assessment))


async def start_dispatches(conn: sqlite3.Connection, clock: Clock, notifier, weather) -> None:
    """Evalúa el clima y, salvo que la sesión se posponga, crea el dispatch y pregunta la fatiga."""
    now = clock.now()
    today = now.date()
    for row in repository.users_due_for_dispatch(conn, today, now.hour * 60 + now.minute):
        try:
            assessment = await _assess_weather(weather, row["user_id"], repository.get_profile(conn, row["user_id"]), today)
            if assessment is not None and assessment.postpone:
                await _postpone(conn, now, notifier, row, assessment)
                continue
            dispatch_id = repository.create_dispatch(conn, row["user_id"], row["session_id"], today, now)
            if dispatch_id is None:
                continue
            audit.event("tool_call", tool="db", op="create_dispatch", user_id=row["user_id"])
            if assessment is not None:
                repository.set_dispatch_weather(conn, dispatch_id, weather_rules.assessment_to_dict(assessment))
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
    assessment = None
    if dispatch["weather_json"]:
        assessment = weather_rules.assessment_from_dict(json.loads(dispatch["weather_json"]))
    unavailable = assessment is not None and not assessment.available
    data = daily_message.build_message_data(session, profile, fatigue, None if unavailable else assessment, unavailable)

    text = await _draft(writer, data)
    used_template = text is None
    if used_template:
        text = daily_message.render_template(data)

    chat_id = repository.get_chat_id(conn, user_id)
    delivered = bool(chat_id is not None and await notifier.send_message(chat_id, text))
    repository.set_dispatch_sent(conn, dispatch["id"], fatigue, used_template, delivered, clock.now())
    audit.event("tool_call", tool="db", op="set_dispatch_sent", user_id=user_id)
    audit.event("message_sent", template=used_template, user_id=user_id, delivered=delivered)
