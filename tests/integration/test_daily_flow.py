import json
import logging
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app import scheduler
from app.ai.errors import AIUnavailableError
from app.bot.handlers import handle_text
from app.clock import FixedClock
from app.domain.models import Block, PlannedSession
from app.services import daily_service, repository
from tests.helpers import FakeNotifier, FakeWeather, FakeWriter, ba, seed_plan, seed_result, seed_user, session_ids

pytestmark = pytest.mark.anyio

TODAY = date(2026, 10, 15)  # jueves
WEEK = date(2026, 10, 12)
CHAT = 42
QUESTION = "¿Cómo está tu fatiga hoy del 1 al 10? Respondé con un número."
RETRY = "Respondé con un número entero del 1 al 10."
QUALITY = [Block("run", 100), Block("run", 100, 345, 345, 120), Block("run", 100, 345, 345)]
# Borrador válido para la sesión de calidad con fatiga ≥ 8 (un único bloque de 3 km, sin ritmo).
EASY_DRAFT = "Hoy toca suave/recuperación, Trote suave. Horario sugerido 07:00–09:00. Secuencia: trote 3,00 km."


def state(db_path, writer=None, notifier=None):
    return SimpleNamespace(
        db_path=db_path,
        planner=None,
        writer=writer or FakeWriter(),
        weather=FakeWeather(),
        notifier=notifier or FakeNotifier(),
    )


def seed(conn, *, blocks=QUALITY, day=TODAY, title="Intervalos", **profile):
    uid = seed_user(conn, "a@example.com", chat_id=CHAT, **profile)
    plan_id = seed_plan(conn, uid, WEEK, [PlannedSession(day, title, blocks)], start_date=WEEK)
    return uid, plan_id


def dispatch(conn, uid, day=TODAY):
    return conn.execute("SELECT * FROM daily_dispatches WHERE user_id = ? AND date = ?", (uid, day.isoformat())).fetchone()


def reply(conn, st, at, text):
    return handle_text(conn, FixedClock(at), st.notifier, st.writer, CHAT, text)


def audit_events(caplog, type_):
    out = []
    for r in caplog.records:
        if r.name == "runia.audit":
            ev = json.loads(r.getMessage())
            if ev["type"] == type_:
                out.append(ev)
    return out


async def test_question_at_send_time_and_not_before(conn, db_path):
    uid, _ = seed(conn)
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 5, 59))
    assert st.notifier.messages == [] and dispatch(conn, uid) is None

    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    assert st.notifier.messages == [(CHAT, QUESTION)]
    d = dispatch(conn, uid)
    assert d["state"] == "awaiting_fatigue" and d["asked_at"].startswith("2026-10-15T06:00:00")

    await scheduler.tick(st, ba(2026, 10, 15, 6, 1))
    assert len(st.notifier.messages) == 1


async def test_invalid_reply_asks_again_without_resetting_window(conn, db_path):
    uid, _ = seed(conn)
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    asked_at = dispatch(conn, uid)["asked_at"]

    for text in ("abc", "0", "11", "7.5", ""):
        assert await reply(conn, st, ba(2026, 10, 15, 6, 30), text) == RETRY
    assert st.notifier.messages == [(CHAT, QUESTION)]
    d = dispatch(conn, uid)
    assert d["state"] == "awaiting_fatigue" and d["asked_at"] == asked_at


async def test_valid_reply_sends_adjusted_message(conn, db_path):
    uid, plan_id = seed(conn)
    st = state(db_path, writer=FakeWriter(text=EASY_DRAFT))
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))

    assert await reply(conn, st, ba(2026, 10, 15, 6, 10), " 9 ") is None
    assert st.notifier.messages == [(CHAT, QUESTION), (CHAT, EASY_DRAFT)]
    data = st.writer.calls[0]
    assert data.session_type_label == "suave/recuperación" and data.target_pace is None
    d = dispatch(conn, uid)
    assert d["state"] == "sent" and d["fatigue"] == 9 and d["used_template"] == 0 and d["delivered"] == 1
    # FR-030: el ajuste no toca la sesión guardada.
    assert repository.get_session_blocks(conn, session_ids(conn, plan_id)[0]) == QUALITY

    assert await reply(conn, st, ba(2026, 10, 15, 6, 11), "3") is None
    await scheduler.tick(st, ba(2026, 10, 15, 8, 30))
    assert len(st.notifier.messages) == 2


async def test_no_reply_sends_unadjusted_after_two_hours(conn, db_path):
    uid, _ = seed(conn)
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    await scheduler.tick(st, ba(2026, 10, 15, 7, 59))
    assert len(st.notifier.messages) == 1

    await scheduler.tick(st, ba(2026, 10, 15, 8, 0))
    assert len(st.notifier.messages) == 2
    text = st.notifier.messages[1][1]
    assert "calidad" in text and "Ritmo objetivo: 5:45 min/km." in text and "07:00–09:00" in text
    d = dispatch(conn, uid)
    assert d["state"] == "sent" and d["fatigue"] is None and d["used_template"] == 1

    assert await reply(conn, st, ba(2026, 10, 15, 8, 5), "9") is None
    assert len(st.notifier.messages) == 2


async def test_reply_after_window_is_ignored_before_tick(conn, db_path):
    uid, _ = seed(conn)
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    assert await reply(conn, st, ba(2026, 10, 15, 8, 0), "9") is None
    assert len(st.notifier.messages) == 1 and dispatch(conn, uid)["state"] == "awaiting_fatigue"


@pytest.mark.parametrize(
    "writer",
    [FakeWriter(error=AIUnavailableError("rate_limit")), FakeWriter(text=EASY_DRAFT, delay=1)],
    ids=["error", "timeout"],
)
async def test_writer_failure_falls_back_to_template(conn, db_path, writer, monkeypatch, caplog):
    monkeypatch.setattr(daily_service, "WRITER_TIMEOUT_S", 0.05)
    caplog.set_level(logging.INFO, logger="runia.audit")
    uid, _ = seed(conn)
    st = state(db_path, writer=writer)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    await reply(conn, st, ba(2026, 10, 15, 6, 5), "9")

    text = st.notifier.messages[1][1]
    assert text.startswith("Hoy: suave/recuperación (Trote suave).") and "trote 3,00 km" in text
    assert dispatch(conn, uid)["used_template"] == 1
    errors = audit_events(caplog, "external_error")
    assert errors and errors[-1]["service"] == "gemini"
    assert errors[-1]["reason"] == ("rate_limit" if writer.error else "timeout")
    sent = audit_events(caplog, "message_sent")
    assert sent[-1]["template"] is True and sent[-1]["delivered"] is True


@pytest.mark.parametrize("bad", ["", "Hoy: suave. Salí a las 07:00.", EASY_DRAFT + " ¿Vamos", EASY_DRAFT + " **Dale**"])
async def test_invalid_draft_falls_back_to_template(conn, db_path, bad):
    uid, _ = seed(conn)
    st = state(db_path, writer=FakeWriter(text=bad))
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    await reply(conn, st, ba(2026, 10, 15, 6, 5), "9")
    assert st.notifier.messages[1][1].startswith("Hoy: suave/recuperación (Trote suave).")
    assert dispatch(conn, uid)["used_template"] == 1


async def test_day_without_session_sends_nothing(conn, db_path):
    uid, _ = seed(conn, day=TODAY + timedelta(days=1))
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    await scheduler.tick(st, ba(2026, 10, 15, 9, 0))
    assert st.notifier.messages == [] and dispatch(conn, uid) is None


async def test_plan_created_after_send_time_starts_next_minute(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=CHAT)
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 9, 59))
    assert st.notifier.messages == []
    seed_plan(conn, uid, WEEK, [PlannedSession(TODAY, "Intervalos", QUALITY)], start_date=TODAY)
    await scheduler.tick(st, ba(2026, 10, 15, 10, 1))
    assert st.notifier.messages == [(CHAT, QUESTION)]


async def test_session_with_result_sends_nothing(conn, db_path):
    uid, plan_id = seed(conn)
    seed_result(conn, session_ids(conn, plan_id)[0], uid, "completed", 5)
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    assert st.notifier.messages == [] and dispatch(conn, uid) is None


async def test_unlinked_or_unknown_chat_is_ignored(conn, db_path):
    seed(conn)
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    assert await handle_text(conn, FixedClock(ba(2026, 10, 15, 6, 5)), st.notifier, st.writer, 999, "9") is None
    assert len(st.notifier.messages) == 1


async def test_failed_delivery_is_recorded_and_not_retried(conn, db_path):
    uid, _ = seed(conn)
    st = state(db_path, notifier=FakeNotifier(result=False))
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    await reply(conn, st, ba(2026, 10, 15, 6, 5), "5")
    d = dispatch(conn, uid)
    assert d["state"] == "sent" and d["delivered"] == 0
    count = len(st.notifier.messages)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 6))
    await scheduler.tick(st, ba(2026, 10, 15, 8, 30))
    assert len(st.notifier.messages) == count == 2


async def test_dispatch_is_isolated_per_user(conn, db_path):
    uid_a, _ = seed(conn)
    uid_b = seed_user(conn, "b@example.com", chat_id=77, send_time_min=6 * 60 + 30)
    seed_plan(conn, uid_b, WEEK, [PlannedSession(TODAY, "Rodaje", [Block("run", 400)])], start_date=WEEK)
    st = state(db_path)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    assert st.notifier.messages == [(CHAT, QUESTION)]
    await scheduler.tick(st, ba(2026, 10, 15, 6, 30))
    assert st.notifier.messages == [(CHAT, QUESTION), (77, QUESTION)]

    await handle_text(conn, FixedClock(ba(2026, 10, 15, 6, 40)), st.notifier, st.writer, 77, "4")
    assert dispatch(conn, uid_a)["state"] == "awaiting_fatigue"
    assert dispatch(conn, uid_b)["state"] == "sent"
    assert st.notifier.messages[-1][0] == 77 and "trote 4,00 km" in st.notifier.messages[-1][1]
