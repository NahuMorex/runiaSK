from datetime import timedelta

import pytest

from app.bot.handlers import handle_start, handle_vincular
from app.services import linking
from tests.helpers import register_and_login, user_id_by_email

pytestmark = pytest.mark.anyio

OK = "Listo: tu cuenta quedó vinculada a este chat."
INVALID = "El código no es válido o ya venció."
ALREADY = "Este chat o tu cuenta ya tienen un vínculo y no se puede modificar."


def links(conn):
    return [tuple(r) for r in conn.execute("SELECT user_id, chat_id FROM telegram_links").fetchall()]


async def test_start_text():
    assert await handle_start() == (
        "Hola, soy Runia. Para vincular tu cuenta, generá un código en la API y enviá /vincular <código>."
    )


async def test_link_code_and_vincular(client, conn, clock):
    h = register_and_login(client, "milena@example.com")
    r = client.post("/telegram/link-code", headers=h)
    assert r.status_code == 201
    body = r.json()
    code = body["code"]
    assert len(code) == 8
    assert body["instructions"] == f"Enviá /vincular {code} al bot dentro de los 15 minutos."
    assert body["expires_at"] == (clock.now() + timedelta(minutes=15)).isoformat()

    assert await handle_vincular(conn, clock, 1001, [code]) == OK
    assert links(conn) == [(user_id_by_email(conn, "milena@example.com"), 1001)]
    assert client.get("/profile", headers=h).json()["telegram_linked"] is True

    # Reusar el código (AC-44)
    assert await handle_vincular(conn, clock, 2002, [code]) == INVALID
    assert links(conn) == [(1, 1001)]

    # La cuenta ya vinculada no puede pedir otro código
    r = client.post("/telegram/link-code", headers=h)
    assert r.status_code == 409
    assert r.json() == {"detail": "Tu cuenta ya tiene un chat de Telegram vinculado"}


async def test_invalid_or_expired_code(client, conn, clock):
    h = register_and_login(client, "milena@example.com")
    assert await handle_vincular(conn, clock, 1001, ["NOEXISTE"]) == INVALID
    assert await handle_vincular(conn, clock, 1001, []) == INVALID
    code = client.post("/telegram/link-code", headers=h).json()["code"]
    clock.advance(timedelta(minutes=15, seconds=1))
    assert await handle_vincular(conn, clock, 1001, [code]) == INVALID
    assert links(conn) == []


async def test_lowercase_code_accepted(client, conn, clock):
    h = register_and_login(client, "milena@example.com")
    code = client.post("/telegram/link-code", headers=h).json()["code"]
    assert await handle_vincular(conn, clock, 1001, [code.lower()]) == OK


async def test_second_code_from_other_chat_rejected_without_consuming(client, conn, clock):
    h = register_and_login(client, "milena@example.com")
    user_id = user_id_by_email(conn, "milena@example.com")
    code1 = client.post("/telegram/link-code", headers=h).json()["code"]
    code2, _ = linking.create_link_code(conn, user_id, clock)  # emitido antes de vincular
    assert await handle_vincular(conn, clock, 1001, [code1]) == OK
    assert await handle_vincular(conn, clock, 2002, [code2]) == ALREADY
    assert links(conn) == [(user_id, 1001)]
    used = conn.execute(
        "SELECT used_at FROM one_time_codes WHERE purpose='link' ORDER BY id"
    ).fetchall()
    assert used[0]["used_at"] is not None and used[1]["used_at"] is None


async def test_linked_chat_cannot_link_other_account(client, conn, clock):
    ha = register_and_login(client, "a@example.com")
    hb = register_and_login(client, "b@example.com")
    code_a = client.post("/telegram/link-code", headers=ha).json()["code"]
    code_b = client.post("/telegram/link-code", headers=hb).json()["code"]
    assert await handle_vincular(conn, clock, 1001, [code_a]) == OK
    assert await handle_vincular(conn, clock, 1001, [code_b]) == ALREADY
    assert links(conn) == [(user_id_by_email(conn, "a@example.com"), 1001)]
    assert client.get("/profile", headers=hb).json()["telegram_linked"] is False
