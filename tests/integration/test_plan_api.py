from datetime import date

import pytest

from app.ai.errors import AIUnavailableError
from app.ai.schemas import WeekPlanProposal
from tests.helpers import (
    FakePlanner,
    ba,
    easy_session,
    quality_session,
    register_and_login,
    seed_link,
    seed_profile,
    user_id_by_email,
)

EMAIL = "milena@example.com"


def setup_user(client, conn, *, link=True, **profile):
    headers = register_and_login(client, EMAIL)
    user_id = user_id_by_email(conn, EMAIL)
    seed_profile(conn, user_id, **profile)
    if link:
        seed_link(conn, user_id, 4242)
    return headers, user_id


def login(client):
    r = client.post("/auth/login", json={"email": EMAIL, "password": "clave-segura-1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def plan_count(conn):
    return conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]


def test_missing_pace_for_intermediate(client, conn):
    h, _ = setup_user(client, conn, current_pace_s=None)
    r = client.post("/plan", headers=h)
    assert r.status_code == 422
    assert r.json() == {"detail": "No hay datos sobre tu ritmo cargados en tu perfil"}
    assert plan_count(conn) == 0


@pytest.mark.parametrize(
    "overrides,campo",
    [
        ({"level": None}, "nivel"),
        ({"frequency": None}, "frecuencia"),
        ({"target_distance_hm": None}, "distancia objetivo"),
        ({"city": None}, "ciudad"),
        ({"range_start_min": None, "range_end_min": None}, "rango horario"),
        ({"send_time_min": None}, "hora de envío"),
    ],
)
def test_missing_field(client, conn, overrides, campo):
    h, _ = setup_user(client, conn, **overrides)
    r = client.post("/plan", headers=h)
    assert r.status_code == 422
    assert r.json() == {"detail": f"No hay datos sobre tu {campo} cargados en tu perfil"}
    assert plan_count(conn) == 0


def test_missing_telegram(client, conn):
    h, _ = setup_user(client, conn, link=False)
    r = client.post("/plan", headers=h)
    assert r.status_code == 422
    assert r.json() == {"detail": "Tu cuenta no tiene un chat de Telegram vinculado"}
    assert plan_count(conn) == 0


def test_novice_without_pace_gets_plan(client, conn, planner):
    h, _ = setup_user(client, conn, level="novato", current_pace_s=None)
    r = client.post("/plan", headers=h)
    assert r.status_code == 201
    assert planner.requests[0].first_week_novice is True
    for s in r.json()["sessions"]:
        kinds = [b["kind"] for b in s["blocks"]]
        assert "caminata" in kinds and "trote" in kinds
        assert all(a != b for a, b in zip(kinds, kinds[1:]))


def test_partial_plan_thursday(client, conn, notifier):
    h, _ = setup_user(client, conn)
    r = client.post("/plan", headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["week_start"] == "2026-10-12" and body["start_date"] == "2026-10-15"
    assert body["is_full"] is False
    assert len(body["sessions"]) == 4
    assert len({s["date"] for s in body["sessions"]}) == 4
    assert body["sessions"][0]["status"] == "Hoy"
    assert notifier.messages == []
    r = client.post("/plan", headers=h)
    assert r.status_code == 409
    assert r.json() == {"detail": "Ya tenés un plan para la semana en curso"}
    assert plan_count(conn) == 1


@pytest.mark.parametrize("planner", [FakePlanner(error=AIUnavailableError("timeout"))])
def test_ai_failure_503(client, conn):
    h, _ = setup_user(client, conn)
    r = client.post("/plan", headers=h)
    assert r.status_code == 503
    assert r.json() == {"detail": "No es posible generar un plan en este momento."}
    assert plan_count(conn) == 0


@pytest.mark.parametrize(
    "planner", [FakePlanner(proposal=lambda req: WeekPlanProposal(sessions=[easy_session(req.allowed_dates[0], 3)]))]
)
def test_invalid_structure_503(client, conn):
    h, _ = setup_user(client, conn)
    r = client.post("/plan", headers=h)
    assert r.status_code == 503
    assert r.json() == {"detail": "No es posible generar un plan en este momento."}
    assert plan_count(conn) == 0


def _quality_then_easy(req):
    d = req.allowed_dates
    sessions = [quality_session(d[0], 345)] + [easy_session(x, 2) for x in d[1 : req.sessions_required]]
    return WeekPlanProposal(sessions=sessions)


@pytest.mark.parametrize("planner", [FakePlanner(proposal=_quality_then_easy)])
def test_quality_session_has_times_and_recovery(client, conn):
    h, _ = setup_user(client, conn)
    r = client.post("/plan", headers=h)
    assert r.status_code == 201
    q = r.json()["sessions"][0]
    assert q["type"] == "calidad"
    reps = [b for b in q["blocks"] if "target_pace" in b]
    assert reps[0]["target_time"] == "5:45" and reps[0]["recovery_after"] == "2:00"
    assert "target_time" in reps[-1]


def test_full_plan_monday_has_n_sessions(client, conn, clock):
    clock.set(ba(2026, 10, 19, 10))
    h, _ = setup_user(client, conn, frequency=5)
    r = client.post("/plan", headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["is_full"] is True
    assert len(body["sessions"]) == 5 and len({s["date"] for s in body["sessions"]}) == 5


def test_first_week_novice_until_first_full_plan(client, conn, clock, planner):
    setup_user(client, conn, level="novato", current_pace_s=None)
    assert client.post("/plan", headers=login(client)).status_code == 201  # jueves, parcial
    assert planner.requests[-1].first_week_novice is True
    clock.set(ba(2026, 10, 19, 10))
    assert client.post("/plan", headers=login(client)).status_code == 201  # primer plan completo
    assert planner.requests[-1].first_week_novice is True
    clock.set(ba(2026, 10, 26, 10))
    assert client.post("/plan", headers=login(client)).status_code == 201
    assert planner.requests[-1].first_week_novice is False


def test_intermediate_downgraded_to_novice_is_first_week(client, conn, clock, planner):
    clock.set(ba(2026, 10, 12, 10))
    _, user_id = setup_user(client, conn)
    assert client.post("/plan", headers=login(client)).status_code == 201
    assert planner.requests[-1].first_week_novice is False
    seed_profile(conn, user_id, level="novato")
    clock.set(ba(2026, 10, 19, 10))
    assert client.post("/plan", headers=login(client)).status_code == 201
    assert planner.requests[-1].first_week_novice is True


def test_plan_request_has_no_identifiers(client, conn, planner):
    h, _ = setup_user(client, conn)
    client.post("/plan", headers=h)
    dumped = planner.requests[0].model_dump_json()
    assert "@" not in dumped and "4242" not in dumped and EMAIL not in dumped
    assert set(planner.requests[0].model_dump()) == {
        "level", "frequency", "target_distance_km", "current_pace_s", "week_start", "allowed_dates",
        "sessions_required", "first_week_novice", "quality_allowed", "target_volume_km", "max_session_km",
        "is_deload", "recent_weeks",
    }
    assert planner.requests[0].allowed_dates[0] == date(2026, 10, 15)
