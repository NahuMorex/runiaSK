from datetime import date, timedelta

import pytest

from app.bot.handlers import handle_registrar
from app.domain.models import Block, PlannedSession
from app.main import app as _default_app
from tests.helpers import DEFAULT_PASSWORD, seed_plan, seed_result, seed_user, session_ids

WEEK = date(2026, 10, 12)
THU = date(2026, 10, 15)
CHAT_A, CHAT_B = 101, 202
A_EMAIL, B_EMAIL = "ana@example.com", "beto@example.com"

HAS_US7 = {"/schedule", "/history"} <= {getattr(r, "path", None) for r in _default_app.routes}
needs_us7 = pytest.mark.skipif(not HAS_US7, reason="GET /schedule y /history llegan con US7")


def login(client, email) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": DEFAULT_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def seed_two(conn, *, b_has_session_today=True):
    """A en Rosario con sesiones el miércoles (registrada, con notas) y hoy; B en Mendoza."""
    a = seed_user(conn, A_EMAIL, chat_id=CHAT_A, city="Rosario")
    b = seed_user(conn, B_EMAIL, chat_id=CHAT_B, city="Mendoza")
    plan_a = seed_plan(
        conn,
        a,
        WEEK,
        [PlannedSession(THU - timedelta(days=1), "Fondo de Ana", [Block("run", 800)]), PlannedSession(THU, "Rodaje de Ana", [Block("run", 400)])],
    )
    a_ids = session_ids(conn, plan_a)
    seed_result(conn, a_ids[0], a, "completed", 6, "nota privada de Ana")
    b_days = [THU] if b_has_session_today else [THU + timedelta(days=1)]
    plan_b = seed_plan(conn, b, WEEK, [PlannedSession(d, "Rodaje de Beto", [Block("run", 300)]) for d in b_days])
    return a, b, a_ids, session_ids(conn, plan_b)


def results_of(conn, user_id):
    return [dict(r) for r in conn.execute("SELECT * FROM session_results WHERE user_id = ? ORDER BY session_id", (user_id,))]


def assert_no_a_data(text: str, a_ids):
    for leak in ("Ana", "ana@example.com", "Rosario", "nota privada"):
        assert leak not in text
    for sid in a_ids:
        assert f'"id":{sid},' not in text.replace(" ", "") and f'"session_id":{sid},' not in text.replace(" ", "")


# --- POST /sessions/{id}/result (AC-37) --------------------------------------


def test_other_users_session_is_403_without_data(client, conn):
    a, _, a_ids, _ = seed_two(conn)
    before = results_of(conn, a)
    r = client.post(f"/sessions/{a_ids[1]}/result", json={"status": "completed", "rpe": 5}, headers=login(client, B_EMAIL))
    assert r.status_code == 403
    assert r.json() == {"detail": "Acceso denegado"}
    assert results_of(conn, a) == before


def test_other_users_registered_session_is_403_and_unchanged(client, conn):
    a, _, a_ids, _ = seed_two(conn)
    before = results_of(conn, a)
    r = client.post(f"/sessions/{a_ids[0]}/result", json={"status": "skipped"}, headers=login(client, B_EMAIL))
    assert r.status_code == 403 and r.json() == {"detail": "Acceso denegado"}
    assert results_of(conn, a) == before


def test_unknown_session_is_404(client, conn):
    seed_two(conn)
    r = client.post("/sessions/99999/result", json={"status": "skipped"}, headers=login(client, B_EMAIL))
    assert r.status_code == 404
    assert r.json() == {"detail": "Sesión no encontrada"}


# --- /registrar (AC-38) -------------------------------------------------------


@pytest.mark.anyio
async def test_bot_registers_only_own_session(conn, clock):
    a, b, a_ids, b_ids = seed_two(conn)
    text = await handle_registrar(conn, clock, CHAT_B, ["completada", "4"])
    assert text == "Registré tu sesión de hoy como Completada."
    assert [r["session_id"] for r in results_of(conn, b)] == b_ids
    assert [r["session_id"] for r in results_of(conn, a)] == [a_ids[0]]


@pytest.mark.anyio
async def test_bot_without_session_today_does_not_touch_others(conn, clock):
    a, b, a_ids, _ = seed_two(conn, b_has_session_today=False)
    before = results_of(conn, a)
    text = await handle_registrar(conn, clock, CHAT_B, ["completada", "4"])
    assert text == "No tenés una sesión planificada para hoy."
    assert_no_a_data(text, a_ids)
    assert results_of(conn, a) == before and results_of(conn, b) == []


# --- Lecturas con el token de B ----------------------------------------------


def test_profile_returns_only_own_data(client, conn):
    _, _, a_ids, _ = seed_two(conn)
    r = client.get("/profile", headers=login(client, B_EMAIL))
    assert r.status_code == 200 and r.json()["city"] == "Mendoza"
    assert_no_a_data(r.text, a_ids)


@needs_us7
def test_schedule_returns_only_own_plan(client, conn):
    _, _, a_ids, b_ids = seed_two(conn)
    r = client.get("/schedule", headers=login(client, B_EMAIL))
    assert r.status_code == 200
    assert [s["id"] for s in r.json()["sessions"]] == b_ids
    assert_no_a_data(r.text, a_ids)


@needs_us7
def test_history_returns_only_own_sessions(client, conn):
    _, _, a_ids, _ = seed_two(conn)
    r = client.get("/history", headers=login(client, B_EMAIL))
    assert r.status_code == 200 and r.json() == {"sessions": []}
    assert_no_a_data(r.text, a_ids)
