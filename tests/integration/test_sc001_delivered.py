"""SC-001 sobre planes guardados: a demanda, del lunes y adoptados por fallback."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app import scheduler
from app.ai.errors import AIUnavailableError
from app.domain import summaries
from app.domain.models import Block, PlannedSession
from app.services import repository
from tests.helpers import (
    FakeNotifier,
    FakePlanner,
    adverse_proposal,
    ba,
    register_and_login,
    seed_link,
    seed_plan,
    seed_profile,
    seed_result,
    seed_user,
    session_ids,
    user_id_by_email,
)
from tests.sc001_check import check_sc001

pytestmark = pytest.mark.anyio


def delivered(conn, plan_id):
    plan = repository.get_plan(conn, plan_id)
    sessions = [
        PlannedSession(s["date"], s["title"], s["blocks"], s["reclassified"])
        for s in repository.get_plan_sessions(conn, plan_id)
    ]
    return plan, sessions


def context_for(conn, user_id, plan, pending=0):
    ws = date.fromisoformat(plan["week_start"])
    history = summaries.summarize_weeks(*repository.history_rows_for_summaries(conn, user_id, ws))
    return summaries.build_context(
        repository.get_profile(conn, user_id), history, ws, date.fromisoformat(plan["start_date"]), pending
    )


def assert_sc001(conn, user_id, plan_id, pending=0):
    plan, sessions = delivered(conn, plan_id)
    ctx = context_for(conn, user_id, plan, pending)
    assert check_sc001(sessions, ctx) == []
    return plan, sessions


@pytest.mark.parametrize("planner", [FakePlanner(proposal=adverse_proposal)])
@pytest.mark.parametrize("level,pace", [("novato", None), ("intermedio", 360), ("avanzado", 300)])
def test_on_demand_plan(client, conn, level, pace):
    h = register_and_login(client, "a@example.com")
    uid = user_id_by_email(conn, "a@example.com")
    seed_profile(conn, uid, level=level, current_pace_s=pace)
    seed_link(conn, uid, 77)
    r = client.post("/plan", headers=h)
    assert r.status_code == 201
    assert_sc001(conn, uid, r.json()["id"])


def _history(conn, uid, n_weeks, *, start=date(2026, 10, 19), volume=1200):
    """n semanas completas con una Completada cada una, antes de `start`."""
    for i in range(n_weeks, 0, -1):
        ws = start - timedelta(days=7 * i)
        pid = seed_plan(conn, uid, ws, [PlannedSession(ws + timedelta(days=d), "R", [Block("run", volume // 3)]) for d in (0, 2, 4)])
        seed_result(conn, session_ids(conn, pid)[0], uid)


@pytest.mark.parametrize("weeks_before", [0, 1, 4])
async def test_monday_plan(conn, db_path, weeks_before):
    uid = seed_user(conn, "a@example.com", chat_id=11, frequency=3)
    _history(conn, uid, weeks_before)
    st = SimpleNamespace(db_path=db_path, planner=FakePlanner(proposal=adverse_proposal), notifier=FakeNotifier(), writer=None, weather=None)
    await scheduler.tick(st, ba(2026, 10, 19, 0, 1))
    plan_id = repository.get_plan_for_week(conn, uid, date(2026, 10, 19))["id"]
    plan, _ = assert_sc001(conn, uid, plan_id)
    if weeks_before == 4:
        assert plan["is_deload"] == 1


async def test_fallback_plan(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=11, frequency=3)
    _history(conn, uid, 2, volume=1500)
    # el último plan propone mucho más que lo permitido para la semana actual
    ws = date(2026, 10, 12)
    conn.execute("DELETE FROM plans WHERE week_start = ?", (ws.isoformat(),))
    last = seed_plan(conn, uid, ws, [
        PlannedSession(ws, "Q", [Block("run", 300), Block("run", 400, 250, None, 60), Block("run", 400, 250)]),
        PlannedSession(ws + timedelta(days=2), "Q", [Block("run", 900, 300)]),
        PlannedSession(ws + timedelta(days=4), "R", [Block("run", 2500)]),
    ])
    seed_result(conn, session_ids(conn, last)[0], uid)
    conn.execute("INSERT INTO pending_reclassifications (user_id, remaining) VALUES (?, 1)", (uid,))
    st = SimpleNamespace(db_path=db_path, planner=FakePlanner(error=AIUnavailableError("timeout")), notifier=FakeNotifier(), writer=None, weather=None)
    await scheduler.tick(st, ba(2026, 10, 19, 0, 1))
    plan_row = repository.get_plan_for_week(conn, uid, date(2026, 10, 19))
    assert plan_row["source"] == "fallback"
    assert_sc001(conn, uid, plan_row["id"], pending=1)
