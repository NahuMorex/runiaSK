from datetime import date, timedelta

import pytest

from app.ai.schemas import WeekPlanProposal
from app.bot.handlers import handle_registrar
from app.domain.models import EASY_TITLE, Block, PlannedSession
from app.services import repository
from tests.helpers import DEFAULT_PASSWORD, ba, easy_session, quality_session, seed_plan, seed_user, session_ids

EMAIL = "milena@example.com"
CHAT = 4242
WEEK = date(2026, 10, 12)
WED, THU, SAT, SUN = (WEEK + timedelta(days=i) for i in (2, 3, 5, 6))
EASY = [Block("run", 400)]
QUALITY = [Block("run", 100), Block("run", 100, 345, 345, 120), Block("run", 100, 345, 345)]
WALK_RUN = [Block("walk", 50), Block("run", 100), Block("walk", 50), Block("run", 100)]

RPE_TEXT = "Indicá un RPE entero de 1 a 10. Ejemplo: /registrar completada 6"
RECLASS_SUFFIX = " Las próximas 2 sesiones pasan a suave/recuperación."


def login(client, email=EMAIL) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": DEFAULT_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def setup(conn, sessions):
    """Usuario vinculado con un plan de la semana del 12/10; devuelve (user_id, {fecha: session_id})."""
    uid = seed_user(conn, EMAIL, chat_id=CHAT)
    plan_id = seed_plan(conn, uid, WEEK, sessions)
    ids = session_ids(conn, plan_id)
    return uid, {s.date: sid for s, sid in zip(sorted(sessions, key=lambda s: s.date), ids)}


def result_row(conn, session_id):
    return conn.execute("SELECT * FROM session_results WHERE session_id = ?", (session_id,)).fetchone()


def post_result(client, headers, session_id, **body):
    return client.post(f"/sessions/{session_id}/result", json=body, headers=headers)


# --- Registro válido (AC-29, AC-30, AC-34) -----------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"status": "completed", "rpe": 6, "notes": "buenas piernas"},
        {"status": "completed", "rpe": 6},
        {"status": "skipped"},
        {"status": "partial", "rpe": 5, "notes": None},
    ],
)
def test_valid_result_is_saved(client, conn, body):
    _, ids = setup(conn, [PlannedSession(THU, "Rodaje", EASY)])
    r = post_result(client, login(client), ids[THU], **body)
    assert r.status_code == 201, r.text
    assert r.json() == {
        "session_id": ids[THU],
        "status": body["status"],
        "rpe": body.get("rpe"),
        "notes": body.get("notes"),
        "reclassified_sessions": [],
        "pending_reclassification": 0,
    }
    row = result_row(conn, ids[THU])
    assert (row["status"], row["rpe"], row["notes"]) == (body["status"], body.get("rpe"), body.get("notes"))


# --- Rechazos (AC-31, AC-32, AC-33, AC-41, AC-69, AC-81) ---------------------


@pytest.mark.parametrize(
    "body",
    [
        {"status": "completed"},
        {"status": "partial"},
        {"status": "completed", "rpe": 0},
        {"status": "completed", "rpe": 11},
        {"status": "skipped", "rpe": 3},
        {"status": "completed", "rpe": 6, "notes": "x" * 501},
        {"status": "terminada", "rpe": 6},
    ],
)
def test_invalid_body_is_422_and_saves_nothing(client, conn, body):
    _, ids = setup(conn, [PlannedSession(THU, "Rodaje", EASY)])
    r = post_result(client, login(client), ids[THU], **body)
    assert r.status_code == 422
    assert result_row(conn, ids[THU]) is None


@pytest.mark.parametrize("day", [WED, date(2026, 10, 16)], ids=["ayer", "mañana"])
def test_session_not_today_is_422(client, conn, day):
    _, ids = setup(conn, [PlannedSession(day, "Rodaje", EASY)])
    r = post_result(client, login(client), ids[day], status="completed", rpe=6)
    assert r.status_code == 422
    assert r.json() == {"detail": "Solo podés registrar la sesión del día"}
    assert result_row(conn, ids[day]) is None


def test_postponed_session_is_422_and_keeps_state(client, conn):
    _, ids = setup(conn, [PlannedSession(THU, "Rodaje", EASY)])
    repository.set_session_postponed(conn, ids[THU], "tormenta eléctrica")
    r = post_result(client, login(client), ids[THU], status="partial", rpe=8)
    assert r.status_code == 422
    assert r.json() == {"detail": "La sesión fue pospuesta por clima y no admite registro"}
    assert result_row(conn, ids[THU]) is None
    row = conn.execute("SELECT system_status FROM sessions WHERE id = ?", (ids[THU],)).fetchone()
    assert row["system_status"] == "postponed_weather"
    assert conn.execute("SELECT COUNT(*) FROM pending_reclassifications").fetchone()[0] == 0


def test_second_result_is_409_and_first_is_kept(client, conn):
    _, ids = setup(conn, [PlannedSession(THU, "Rodaje", EASY)])
    h = login(client)
    assert post_result(client, h, ids[THU], status="completed", rpe=6, notes="bien").status_code == 201
    r = post_result(client, h, ids[THU], status="skipped")
    assert r.status_code == 409
    assert r.json() == {"detail": "La sesión ya tiene un resultado registrado"}
    row = result_row(conn, ids[THU])
    assert (row["status"], row["rpe"], row["notes"]) == ("completed", 6, "bien")


# --- Reclasificación (FR-042, AC-39) -----------------------------------------


def test_partial_rpe7_reclassifies_next_two_sessions(client, conn):
    uid, ids = setup(
        conn,
        [PlannedSession(THU, "Rodaje", EASY), PlannedSession(SAT, "Intervalos", QUALITY), PlannedSession(SUN, "Caminata y trote", WALK_RUN)],
    )
    r = post_result(client, login(client), ids[THU], status="partial", rpe=7)
    assert r.status_code == 201
    assert r.json()["reclassified_sessions"] == [ids[SAT], ids[SUN]]
    assert r.json()["pending_reclassification"] == 0

    sat = repository.get_session_for_user_on(conn, uid, SAT)
    assert sat["blocks"] == [Block("run", 300)] and sat["title"] == EASY_TITLE and sat["reclassified"]
    sun = repository.get_session_for_user_on(conn, uid, SUN)
    assert sun["blocks"] == WALK_RUN and sun["title"] == "Caminata y trote" and sun["reclassified"]
    assert conn.execute("SELECT COUNT(*) FROM pending_reclassifications").fetchone()[0] == 0


def test_partial_rpe6_does_not_reclassify(client, conn):
    uid, ids = setup(conn, [PlannedSession(THU, "Rodaje", EASY), PlannedSession(SAT, "Intervalos", QUALITY)])
    r = post_result(client, login(client), ids[THU], status="partial", rpe=6)
    assert r.status_code == 201 and r.json()["reclassified_sessions"] == []
    sat = repository.get_session_for_user_on(conn, uid, SAT)
    assert sat["blocks"] == QUALITY and not sat["reclassified"]


def test_pending_reclassification_is_applied_to_next_plan(client, conn, clock, planner):
    uid, ids = setup(conn, [PlannedSession(SAT, "Rodaje", EASY), PlannedSession(SUN, "Intervalos", QUALITY)])
    clock.set(ba(2026, 10, 17, 10, 0))  # sábado
    r = post_result(client, login(client), ids[SAT], status="partial", rpe=7)
    assert r.status_code == 201
    assert r.json()["reclassified_sessions"] == [ids[SUN]]
    assert r.json()["pending_reclassification"] == 1
    assert repository.get_pending_reclass(conn, uid) == 1
    assert repository.get_session_for_user_on(conn, uid, SUN)["blocks"] == [Block("run", 300)]

    mon = date(2026, 10, 19)
    planner.proposal = lambda req: WeekPlanProposal(
        sessions=[quality_session(mon, 345)] + [easy_session(mon + timedelta(days=i), 2.0) for i in (2, 4, 6)]
    )
    clock.set(ba(2026, 10, 19, 10, 0))
    r = client.post("/plan", headers=login(client))
    assert r.status_code == 201, r.text
    first, *rest = r.json()["sessions"]
    assert first["date"] == "2026-10-19" and first["type"] == "suave" and len(first["blocks"]) == 1
    flags = [s["reclassified"] for s in repository.get_plan_sessions(conn, r.json()["id"])]
    assert flags == [True, False, False, False]
    assert repository.get_pending_reclass(conn, uid) == 0


# --- /registrar (contracts/telegram-bot.md) ----------------------------------


@pytest.mark.anyio
async def test_registrar_from_bot(conn, clock):
    uid, ids = setup(conn, [PlannedSession(THU, "Rodaje", EASY)])
    assert await handle_registrar(conn, clock, CHAT, ["completada"]) == RPE_TEXT
    assert await handle_registrar(conn, clock, CHAT, ["completada", "11"]) == RPE_TEXT
    assert await handle_registrar(conn, clock, CHAT, ["terminada", "6"]) == "Estados válidos: completada, parcial, salteada."
    assert await handle_registrar(conn, clock, CHAT, []) == "Estados válidos: completada, parcial, salteada."
    assert result_row(conn, ids[THU]) is None

    text = await handle_registrar(conn, clock, CHAT, ["Completada", "6", "buenas", "piernas"])
    assert text == "Registré tu sesión de hoy como Completada."
    row = result_row(conn, ids[THU])
    assert (row["status"], row["rpe"], row["notes"]) == ("completed", 6, "buenas piernas")
    assert await handle_registrar(conn, clock, CHAT, ["salteada"]) == "La sesión de hoy ya tiene un resultado registrado."


@pytest.mark.anyio
async def test_registrar_partial_with_reclassification(conn, clock):
    uid, ids = setup(conn, [PlannedSession(THU, "Rodaje", EASY), PlannedSession(SAT, "Intervalos", QUALITY)])
    text = await handle_registrar(conn, clock, CHAT, ["parcial", "8", "me", "dolió", "el", "flato"])
    assert text == "Registré tu sesión de hoy como Parcial/Cortada." + RECLASS_SUFFIX
    assert repository.get_pending_reclass(conn, uid) == 1


@pytest.mark.anyio
async def test_registrar_skipped_and_postponed(conn, clock):
    uid, ids = setup(conn, [PlannedSession(THU, "Rodaje", EASY)])
    repository.set_session_postponed(conn, ids[THU], "lluvia probable (90%)")
    assert await handle_registrar(conn, clock, CHAT, ["salteada"]) == "La sesión de hoy fue pospuesta por clima y no admite registro."
    conn.execute("UPDATE sessions SET system_status = NULL WHERE id = ?", (ids[THU],))
    assert await handle_registrar(conn, clock, CHAT, ["salteada", "no", "pude"]) == "Registré tu sesión de hoy como Salteada."
    row = result_row(conn, ids[THU])
    assert (row["status"], row["rpe"], row["notes"]) == ("skipped", None, "no pude")


@pytest.mark.anyio
async def test_registrar_unlinked_chat_or_no_session(conn, clock):
    setup(conn, [PlannedSession(SAT, "Rodaje", EASY)])
    assert await handle_registrar(conn, clock, 999, ["completada", "6"]) == "Este chat no está vinculado a ninguna cuenta."
    assert await handle_registrar(conn, clock, CHAT, ["completada", "6"]) == "No tenés una sesión planificada para hoy."
