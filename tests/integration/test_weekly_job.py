import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app import scheduler
from app.ai.errors import AIUnavailableError
from app.domain.models import Block, PlannedSession
from app.services import repository
from tests.helpers import FakeNotifier, FakePlanner, ba, seed_plan, seed_user

pytestmark = pytest.mark.anyio

NOW = ba(2026, 10, 19, 0, 1)
PREV = date(2026, 10, 12)
CUR = date(2026, 10, 19)
NOTICE = "Generación de un nuevo plan no disponible: te enviamos tu último plan válido."
NO_PLAN = "No es posible generar un plan en este momento."


def state(db_path, planner, notifier=None):
    return SimpleNamespace(db_path=db_path, planner=planner, notifier=notifier or FakeNotifier(), writer=None, weather=None)


def plans_of(conn, user_id):
    return conn.execute("SELECT * FROM plans WHERE user_id = ? ORDER BY week_start", (user_id,)).fetchall()


def runs(conn, user_id):
    return [r["outcome"] for r in conn.execute("SELECT outcome FROM weekly_generation_runs WHERE user_id = ?", (user_id,))]


def easy(d, hm, title="Rodaje"):
    return PlannedSession(d, title, [Block("run", hm)])


def quality(d):
    return PlannedSession(
        d, "Intervalos", [Block("run", 100), Block("run", 100, 345, 345, 120), Block("run", 100, 345, 345)]
    )


async def test_eligible_user_gets_plan_and_summary(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=11)
    st = state(db_path, FakePlanner())
    await scheduler.tick(st, NOW)
    plans = plans_of(conn, uid)
    assert len(plans) == 1 and plans[0]["source"] == "monday" and plans[0]["is_full"] == 1
    assert len(st.notifier.messages) == 1
    chat, text = st.notifier.messages[0]
    assert chat == 11
    lines = text.splitlines()
    assert lines[0] == "Tu plan de la semana del 19/10:"
    assert len(lines) == 5
    assert lines[1].startswith("- Lunes: suave, ") and lines[1].endswith(" km de trote")
    assert runs(conn, uid) == ["generated"]

    await scheduler.tick(st, NOW + timedelta(minutes=1))
    assert len(plans_of(conn, uid)) == 1 and len(st.notifier.messages) == 1


async def test_not_on_other_days(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=11)
    await scheduler.tick(state(db_path, FakePlanner()), ba(2026, 10, 20, 0, 1))
    assert plans_of(conn, uid) == []


async def test_unlinked_or_incomplete_get_nothing(conn, db_path):
    unlinked = seed_user(conn, "a@example.com")
    incomplete = seed_user(conn, "b@example.com", chat_id=22, city=None)
    st = state(db_path, FakePlanner())
    await scheduler.tick(st, NOW)
    assert plans_of(conn, unlinked) == [] and plans_of(conn, incomplete) == []
    assert st.notifier.messages == []
    assert runs(conn, incomplete) == ["skipped_incomplete"]


async def test_fallback_adopts_last_plan_with_current_guardrails(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=11)
    prev_id = seed_plan(conn, uid, PREV, [easy(PREV, 500), easy(PREV + timedelta(days=2), 500), easy(PREV + timedelta(days=4), 500)])
    st = state(db_path, FakePlanner(error=AIUnavailableError("timeout")))
    await scheduler.tick(st, NOW)
    plan = plans_of(conn, uid)[-1]
    assert plan["source"] == "fallback" and plan["adopted_from_plan_id"] == prev_id
    assert plan["week_start"] == CUR.isoformat()
    # la semana previa no tuvo Completadas: el volumen no supera el planificado (1500)
    assert plan["planned_volume_hm"] <= 1500
    dates = [s["date"] for s in repository.get_plan_sessions(conn, plan["id"])]
    assert dates == [CUR, CUR + timedelta(days=2), CUR + timedelta(days=4)]
    text = st.notifier.messages[0][1]
    assert text.startswith(NOTICE + "\nTu plan de la semana del 19/10:")
    assert runs(conn, uid) == ["fallback"]


async def test_failure_without_previous_plan(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=11)
    st = state(db_path, FakePlanner(error=AIUnavailableError("server_error")))
    await scheduler.tick(st, NOW)
    assert plans_of(conn, uid) == []
    assert st.notifier.messages == [(11, NO_PLAN)]
    await scheduler.tick(st, NOW + timedelta(minutes=5))
    assert st.notifier.messages == [(11, NO_PLAN)]
    assert runs(conn, uid) == ["failed_no_previous"]


async def test_fallback_consumes_pending_reclass(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=11)
    seed_plan(conn, uid, PREV, [quality(PREV), easy(PREV + timedelta(days=2), 400), quality(PREV + timedelta(days=4))])
    conn.execute("INSERT INTO pending_reclassifications (user_id, remaining) VALUES (?, 1)", (uid,))
    await scheduler.tick(state(db_path, FakePlanner(error=AIUnavailableError("timeout"))), NOW)
    plan = plans_of(conn, uid)[-1]
    sessions = repository.get_plan_sessions(conn, plan["id"])
    assert sessions[0]["reclassified"] and sessions[0]["title"] == "Trote suave"
    assert all(b.target_pace_s is None for b in sessions[0]["blocks"])
    assert not sessions[1]["reclassified"]
    assert repository.get_pending_reclass(conn, uid) == 0

    await scheduler.tick(state(db_path, FakePlanner()), ba(2026, 10, 26, 0, 1))
    nxt = plans_of(conn, uid)[-1]
    assert nxt["week_start"] == "2026-10-26"
    assert not any(s["reclassified"] for s in repository.get_plan_sessions(conn, nxt["id"]))


async def test_fallback_from_partial_plan_is_full(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=11)
    thu = PREV + timedelta(days=3)
    seed_plan(conn, uid, PREV, [easy(thu, 300), easy(thu + timedelta(days=1), 300), easy(thu + timedelta(days=3), 300)], start_date=thu)
    await scheduler.tick(state(db_path, FakePlanner(error=AIUnavailableError("timeout"))), NOW)
    plan = plans_of(conn, uid)[-1]
    assert plan["start_date"] == CUR.isoformat() and plan["is_full"] == 1
    dates = [s["date"] for s in repository.get_plan_sessions(conn, plan["id"])]
    assert dates == [date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 25)]


class FlakyPlanner(FakePlanner):
    async def __call__(self, req):
        self.requests.append(req)
        if len(self.requests) == 1:
            raise RuntimeError("boom")
        return await FakePlanner.__call__(self, req)


async def test_unexpected_error_isolated_per_user(conn, db_path):
    first = seed_user(conn, "a@example.com", chat_id=11)
    second = seed_user(conn, "b@example.com", chat_id=22)
    planner = FlakyPlanner()
    st = state(db_path, planner)
    await scheduler.tick(st, NOW)
    assert plans_of(conn, first) == [] and runs(conn, first) == ["error"]
    assert len(plans_of(conn, second)) == 1
    calls = len(planner.requests)
    await scheduler.tick(st, NOW + timedelta(minutes=1))
    assert len(planner.requests) == calls and plans_of(conn, first) == []


async def test_snapshot_saved(conn, db_path):
    uid = seed_user(conn, "a@example.com", chat_id=11)
    await scheduler.tick(state(db_path, FakePlanner()), NOW)
    snap = json.loads(plans_of(conn, uid)[0]["profile_snapshot"])
    assert snap == {"level": "intermedio", "frequency": 4, "target_distance_hm": 1000, "current_pace_s": 360}
