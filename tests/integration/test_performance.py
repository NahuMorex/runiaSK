"""Rendimiento del mensaje diario (SC-004, RNF-01): p95 ≤ 10 s con 10 usuarios simultáneos."""

import asyncio
import math
import time
from datetime import date
from types import SimpleNamespace

import pytest

from app import db
from app.bot.handlers import build_application
from app.clock import FixedClock
from app.domain.models import Block, PlannedSession
from app.services import daily_service
from tests.helpers import FakeNotifier, FakeWriter, ba, seed_plan, seed_user

pytestmark = pytest.mark.anyio

USERS = 10
TODAY = date(2026, 10, 15)
WEEK = date(2026, 10, 12)
FIRST_CHAT = 500
SLA_S = 10.0


def p95(durations: list[float]) -> float:
    """Percentil 95 por rango más cercano."""
    ordered = sorted(durations)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


async def seed_awaiting(conn) -> list[int]:
    """10 usuarios con sesión hoy y el dispatch en `awaiting_fatigue`."""
    chats = []
    for i in range(USERS):
        chat = FIRST_CHAT + i
        uid = seed_user(conn, f"corredor{i}@example.com", chat_id=chat)
        seed_plan(conn, uid, WEEK, [PlannedSession(TODAY, "Rodaje", [Block("run", 500)])], start_date=WEEK)
        chats.append(chat)
    await daily_service.start_dispatches(conn, FixedClock(ba(2026, 10, 15, 6, 0)), FakeNotifier(), None)
    states = {r["state"] for r in conn.execute("SELECT state FROM daily_dispatches")}
    assert states == {"awaiting_fatigue"}
    return chats


async def reply_all(db_path, writer, notifier, chats) -> tuple[list[float], float]:
    """Responde la fatiga de todos a la vez; cada usuario con su conexión, como el handler del bot."""
    clock = FixedClock(ba(2026, 10, 15, 6, 10))

    async def one(chat: int) -> float:
        conn = db.connect(db_path)
        try:
            started = time.monotonic()
            await daily_service.handle_fatigue_reply(conn, clock, notifier, writer, chat, "5")
            return time.monotonic() - started
        finally:
            conn.close()

    started = time.monotonic()
    durations = await asyncio.gather(*(one(c) for c in chats))
    return list(durations), time.monotonic() - started


async def test_p95_with_10_simultaneous_users(conn, db_path):
    chats = await seed_awaiting(conn)
    writer = FakeWriter("Hoy toca un rodaje suave.", delay=1.0)
    notifier = FakeNotifier(delay=0.2)

    durations, _ = await reply_all(db_path, writer, notifier, chats)

    assert len(writer.calls) == USERS
    assert sorted(c for c, _ in notifier.messages) == chats
    assert p95(durations) <= SLA_S


async def test_slow_writer_falls_back_to_template_within_sla(conn, db_path):
    chats = await seed_awaiting(conn)
    writer = FakeWriter("Hoy toca un rodaje suave.", delay=6.0)
    notifier = FakeNotifier(delay=0.2)

    durations, total = await reply_all(db_path, writer, notifier, chats)

    assert sorted(c for c, _ in notifier.messages) == chats
    rows = conn.execute("SELECT state, used_template FROM daily_dispatches").fetchall()
    assert {(r["state"], r["used_template"]) for r in rows} == {("sent", 1)}
    assert max(durations) >= daily_service.WRITER_TIMEOUT_S
    assert total < SLA_S


def test_bot_processes_updates_concurrently():
    application = build_application("123:dummy", SimpleNamespace(db_path=":memory:", clock=None))
    assert application.concurrent_updates > 1
