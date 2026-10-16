from datetime import date, timedelta

from app.domain.models import Block, PlannedSession
from app.services import repository
from tests.helpers import DEFAULT_PASSWORD, seed_plan, seed_result, seed_user, session_ids

EMAIL = "milena@example.com"
WEEK = date(2026, 10, 12)
PREV_WEEK = date(2026, 10, 5)
MON, TUE, WED, THU, SAT = (WEEK + timedelta(days=i) for i in (0, 1, 2, 3, 5))
EASY = [Block("run", 400)]
QUALITY = [Block("run", 100), Block("run", 100, 345, 345, 120), Block("run", 100, 345, 345)]


def login(client) -> dict:
    r = client.post("/auth/login", json={"email": EMAIL, "password": DEFAULT_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def seed_weeks(conn):
    """Semana anterior (martes salteada, viernes sin registro) y la actual de lunes a sábado, con hoy jueves."""
    uid = seed_user(conn, EMAIL, chat_id=4242)
    prev = seed_plan(
        conn,
        uid,
        PREV_WEEK,
        [PlannedSession(date(2026, 10, 6), "Rodaje", EASY), PlannedSession(date(2026, 10, 9), "Rodaje", EASY)],
    )
    prev_ids = session_ids(conn, prev)
    seed_result(conn, prev_ids[0], uid, "skipped", None)
    plan = seed_plan(
        conn,
        uid,
        WEEK,
        [
            PlannedSession(MON, "Rodaje", EASY),
            PlannedSession(TUE, "Intervalos", QUALITY),
            PlannedSession(WED, "Rodaje", EASY),
            PlannedSession(THU, "Rodaje", EASY),
            PlannedSession(SAT, "Fondo", [Block("run", 800)]),
        ],
    )
    ids = dict(zip((MON, TUE, WED, THU, SAT), session_ids(conn, plan)))
    seed_result(conn, ids[MON], uid, "completed", 6, "buenas piernas")
    repository.set_session_postponed(conn, ids[WED], "lluvia probable (90%)")
    return uid, plan, ids, prev_ids


# --- GET /schedule (AC-35) ----------------------------------------------------


def test_schedule_statuses_and_results(client, conn):
    _, plan, ids, _ = seed_weeks(conn)
    r = client.get("/schedule", headers=login(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == plan and body["week_start"] == "2026-10-12"
    by_date = {s["date"]: s for s in body["sessions"]}
    assert list(by_date) == ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-17"]
    assert [s["status"] for s in body["sessions"]] == [
        "Completada",
        "Sin registrar",
        "Pospuesta por clima",
        "Hoy",
        "Proyectada",
    ]
    assert by_date["2026-10-12"]["result"] == {"status": "completed", "rpe": 6, "notes": "buenas piernas"}
    assert all(by_date[d]["result"] is None for d in ("2026-10-13", "2026-10-14", "2026-10-15", "2026-10-17"))
    tue = by_date["2026-10-13"]
    assert tue["type"] == "calidad" and tue["weekday"] == "martes" and tue["run_km"] == 3.0
    assert tue["blocks"][1] == {"kind": "trote", "distance_km": 1.0, "target_pace": "5:45", "target_time": "5:45", "recovery_after": "2:00"}


def test_schedule_shows_today_result(client, conn):
    uid, _, ids, _ = seed_weeks(conn)
    seed_result(conn, ids[THU], uid, "partial", 7, None)
    r = client.get("/schedule", headers=login(client))
    today = next(s for s in r.json()["sessions"] if s["date"] == "2026-10-15")
    assert today["status"] == "Parcial/Cortada" and today["result"] == {"status": "partial", "rpe": 7, "notes": None}


def test_schedule_without_plan_is_404(client, conn):
    seed_user(conn, EMAIL, chat_id=4242)
    r = client.get("/schedule", headers=login(client))
    assert r.status_code == 404
    assert r.json() == {"detail": "No tenés un plan para la semana en curso"}


def test_schedule_requires_auth(client, conn):
    assert client.get("/schedule").status_code == 401
    assert client.get("/history").status_code == 401


# --- GET /history (AC-29, AC-36) ---------------------------------------------


def test_history_lists_past_sessions_newest_first(client, conn):
    _, _, ids, prev_ids = seed_weeks(conn)
    r = client.get("/history", headers=login(client))
    assert r.status_code == 200, r.text
    items = r.json()["sessions"]
    assert [i["date"] for i in items] == ["2026-10-14", "2026-10-13", "2026-10-12", "2026-10-09", "2026-10-06"]
    assert items[0] == {
        "session_id": ids[WED],
        "date": "2026-10-14",
        "title": "Rodaje",
        "type": "suave",
        "run_km": 4.0,
        "status": "Pospuesta por clima",
        "rpe": None,
        "notes": None,
    }
    assert [i["status"] for i in items] == ["Pospuesta por clima", "Sin registrar", "Completada", "Sin registrar", "Salteada"]
    assert (items[2]["rpe"], items[2]["notes"]) == (6, "buenas piernas")
    assert items[1]["type"] == "calidad" and items[1]["session_id"] == ids[TUE]
    assert items[-1]["session_id"] == prev_ids[0] and items[-1]["rpe"] is None


def test_history_includes_today_only_with_result(client, conn):
    uid, _, ids, _ = seed_weeks(conn)
    h = login(client)
    assert "2026-10-15" not in [i["date"] for i in client.get("/history", headers=h).json()["sessions"]]

    seed_result(conn, ids[THU], uid, "completed", 5, None)
    items = client.get("/history", headers=h).json()["sessions"]
    assert items[0]["date"] == "2026-10-15" and items[0]["status"] == "Completada" and items[0]["rpe"] == 5
    assert "2026-10-17" not in [i["date"] for i in items]
