import re
from datetime import date, timedelta

import pytest

from app.bot.handlers import handle_restablecer
from app.domain.models import Block, PlannedSession
from app.services import repository
from tests.helpers import DEFAULT_PASSWORD, ba, seed_plan, seed_result, seed_user, session_ids

EMAIL, OTHER = "milena@example.com", "otro@example.com"
CHAT = 4242
NEW_PASSWORD = "otra-clave-segura"
WEEK = date(2026, 10, 12)
INVALID_CODE = {"detail": "Código inválido o vencido"}
DELETE_WARNING = {
    "detail": "La eliminación es definitiva y no se puede deshacer. Repetí la solicitud con confirm=true para confirmar."
}
NOT_LINKED = "Este chat no está vinculado a ninguna cuenta."
RESET_TEXT_RE = re.compile(
    r"^Tu código para restablecer la contraseña es ([A-Z2-9]{10})\. Vence en 30 minutos\. "
    r"Envialo a POST /auth/password-reset junto con tu nueva contraseña\.$"
)


def login(client, email=EMAIL, password=DEFAULT_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def headers(client, email=EMAIL) -> dict:
    r = login(client, email)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def password_hash(conn, email=EMAIL) -> str:
    return repository.get_user_by_email(conn, email)["password_hash"]


async def reset_code(conn, clock) -> str:
    match = RESET_TEXT_RE.match(await handle_restablecer(conn, clock, CHAT))
    assert match, "texto de /restablecer distinto del contrato"
    return match.group(1)


def reset(client, code, new_password=NEW_PASSWORD):
    return client.post("/auth/password-reset", json={"code": code, "new_password": new_password})


# --- Restablecer la contraseña (AC-49, AC-50) --------------------------------


@pytest.mark.anyio
async def test_password_reset_flow(client, conn, clock):
    seed_user(conn, EMAIL, chat_id=CHAT)
    code = await reset_code(conn, clock)
    r = reset(client, code)
    assert r.status_code == 200 and r.json() == {"detail": "Contraseña actualizada"}
    assert login(client, password=NEW_PASSWORD).status_code == 200
    r = login(client)
    assert r.status_code == 401 and r.json() == {"detail": "Credenciales inválidas"}

    # El código es de un solo uso.
    r = reset(client, code, "una-tercera-clave")
    assert r.status_code == 400 and r.json() == INVALID_CODE
    assert login(client, password=NEW_PASSWORD).status_code == 200


@pytest.mark.anyio
async def test_expired_or_unknown_code_is_400_without_changes(client, conn, clock):
    seed_user(conn, EMAIL, chat_id=CHAT)
    before = password_hash(conn)
    code = await reset_code(conn, clock)

    assert reset(client, "ABCDEFGHJK").json() == INVALID_CODE
    clock.advance(timedelta(minutes=30, seconds=1))
    r = reset(client, code)
    assert r.status_code == 400 and r.json() == INVALID_CODE
    assert password_hash(conn) == before


@pytest.mark.anyio
async def test_code_still_valid_at_29_minutes(client, conn, clock):
    seed_user(conn, EMAIL, chat_id=CHAT)
    code = await reset_code(conn, clock)
    clock.advance(timedelta(minutes=29, seconds=59))
    assert reset(client, code).status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize("bad", ["corta12", "x" * 129])
async def test_invalid_new_password_is_422_and_does_not_consume_code(client, conn, clock, bad):
    seed_user(conn, EMAIL, chat_id=CHAT)
    before = password_hash(conn)
    code = await reset_code(conn, clock)
    assert reset(client, code, bad).status_code == 422
    assert password_hash(conn) == before
    assert reset(client, code).status_code == 200


@pytest.mark.anyio
async def test_restablecer_from_unlinked_chat(conn, clock):
    seed_user(conn, EMAIL)
    assert await handle_restablecer(conn, clock, CHAT) == NOT_LINKED
    assert conn.execute("SELECT COUNT(*) FROM one_time_codes").fetchone()[0] == 0


@pytest.mark.anyio
async def test_reset_code_is_stored_hashed(conn, clock):
    seed_user(conn, EMAIL, chat_id=CHAT)
    code = await reset_code(conn, clock)
    row = conn.execute("SELECT * FROM one_time_codes WHERE purpose = 'reset'").fetchone()
    assert row["code_hash"] != code and code not in row["code_hash"]
    assert row["expires_at"].startswith("2026-10-15T10:30:00")


# --- Eliminar la cuenta (AC-52, AC-53) ---------------------------------------

USER_TABLES = (
    "profiles",
    "plans",
    "sessions",
    "session_results",
    "telegram_links",
    "one_time_codes",
    "pending_reclassifications",
    "daily_dispatches",
    "weekly_generation_runs",
)


def seed_full_account(conn, email, chat_id) -> int:
    uid = seed_user(conn, email, chat_id=chat_id)
    plan_id = seed_plan(conn, uid, WEEK, [PlannedSession(date(2026, 10, 14), "Rodaje", [Block("run", 400)]), PlannedSession(date(2026, 10, 15), "Rodaje", [Block("run", 400)])])
    ids = session_ids(conn, plan_id)
    seed_result(conn, ids[0], uid, "completed", 5, "nota")
    repository.upsert_pending_reclass(conn, uid, 1)
    repository.create_dispatch(conn, uid, ids[1], date(2026, 10, 15), ba(2026, 10, 15, 6))
    repository.record_weekly_run(conn, uid, WEEK, "created", ba(2026, 10, 12))
    repository.create_code(conn, uid, "link", "hash-" + email, ba(2026, 10, 15, 11))
    return uid


def rows_of(conn, uid) -> dict[str, int]:
    out = {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id = ?", (uid,)).fetchone()[0] for t in USER_TABLES}
    out["users"] = conn.execute("SELECT COUNT(*) FROM users WHERE id = ?", (uid,)).fetchone()[0]
    out["blocks"] = conn.execute(
        "SELECT COUNT(*) FROM blocks b JOIN sessions s ON s.id = b.session_id WHERE s.user_id = ?", (uid,)
    ).fetchone()[0]
    return out


@pytest.mark.parametrize("query", ["", "?confirm=yes", "?confirm=TRUE", "?confirm="])
def test_delete_without_confirmation_is_400(client, conn, query):
    uid = seed_full_account(conn, EMAIL, CHAT)
    before = rows_of(conn, uid)
    r = client.delete(f"/profile{query}", headers=headers(client))
    assert r.status_code == 400 and r.json() == DELETE_WARNING
    assert rows_of(conn, uid) == before


def test_delete_with_confirmation_removes_everything(client, conn):
    uid = seed_full_account(conn, EMAIL, CHAT)
    other = seed_full_account(conn, OTHER, 777)
    other_before = rows_of(conn, other)
    h = headers(client)

    r = client.delete("/profile?confirm=true", headers=h)
    assert r.status_code == 204 and r.content == b""
    assert "x-session-token" not in r.headers
    assert all(n == 0 for n in rows_of(conn, uid).values()), rows_of(conn, uid)
    assert rows_of(conn, other) == other_before

    r = login(client)
    assert r.status_code == 401 and r.json() == {"detail": "Credenciales inválidas"}
    r = client.get("/profile", headers=h)
    assert r.status_code == 401 and r.json() == {"detail": "No autenticado"}


# --- Cambios de perfil con un plan vigente (AC-70) ---------------------------


def test_profile_change_applies_from_next_plan(client, conn, clock, planner):
    uid = seed_user(conn, EMAIL, chat_id=CHAT, frequency=4)
    h = headers(client)
    assert client.post("/plan", headers=h).status_code == 201
    plan = repository.get_plan_for_week(conn, uid, WEEK)
    before = repository.get_plan_sessions(conn, plan["id"])

    r = client.put("/profile", json={"frequency": 2}, headers=h)
    assert r.status_code == 200 and r.json()["frequency"] == 2
    assert repository.get_plan_sessions(conn, plan["id"]) == before

    clock.set(ba(2026, 10, 19, 10, 0))  # lunes siguiente
    r = client.post("/plan", headers=headers(client))
    assert r.status_code == 201, r.text
    assert planner.requests[-1].frequency == 2 and planner.requests[-1].sessions_required == 2
    assert len(r.json()["sessions"]) == 2
