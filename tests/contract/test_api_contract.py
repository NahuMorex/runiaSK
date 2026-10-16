"""Contrato de la API (contracts/api.md): códigos, claves exactas del cuerpo, `detail` fijos y X-Session-Token."""

import pytest

from app.ai.errors import AIUnavailableError
from app.bot.handlers import handle_restablecer
from tests.helpers import DEFAULT_PASSWORD, register_and_login, seed_link, seed_profile, seed_user, user_id_by_email

EMAIL, OTHER = "milena@example.com", "otro@example.com"
CHAT = 4242

PROFILE_KEYS = {
    "level",
    "frequency",
    "target_distance_km",
    "current_pace",
    "city",
    "preferred_range",
    "send_time",
    "telegram_linked",
}
PLAN_KEYS = {"id", "week_start", "start_date", "is_full", "is_deload", "planned_volume_km", "sessions"}
SESSION_KEYS = {"id", "date", "weekday", "title", "type", "run_km", "status", "blocks"}
BLOCK_REQUIRED = {"kind", "distance_km"}
BLOCK_OPTIONAL = {"target_pace", "target_time", "recovery_after"}
HISTORY_KEYS = {"session_id", "date", "title", "type", "run_km", "status", "rpe", "notes"}
RESULT_KEYS = {"session_id", "status", "rpe", "notes", "reclassified_sessions", "pending_reclassification"}
SESSION_STATUSES = {
    "Completada",
    "Parcial/Cortada",
    "Salteada",
    "Pospuesta por clima",
    "Sin registrar",
    "Hoy",
    "Proyectada",
}
HISTORY_STATUSES = SESSION_STATUSES - {"Hoy", "Proyectada"}

AUTHENTICATED = [
    ("get", "/profile"),
    ("put", "/profile"),
    ("delete", "/profile?confirm=true"),
    ("post", "/telegram/link-code"),
    ("post", "/plan"),
    ("get", "/schedule"),
    ("get", "/history"),
    ("post", "/sessions/1/result"),
]


def detail(r) -> str:
    return r.json()["detail"]


def has_renewed_token(r) -> bool:
    return bool(r.headers.get("X-Session-Token"))


def ready_user(client, conn, email=EMAIL, chat_id=CHAT) -> dict:
    """Usuario registrado por la API, con perfil completo y chat vinculado."""
    headers = register_and_login(client, email)
    user_id = user_id_by_email(conn, email)
    seed_profile(conn, user_id)
    seed_link(conn, user_id, chat_id)
    return headers


def create_plan(client, headers) -> dict:
    r = client.post("/plan", headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def today_session_id(plan: dict) -> int:
    return next(s["id"] for s in plan["sessions"] if s["status"] == "Hoy")


def assert_plan_shape(plan: dict, *, with_result: bool = False) -> None:
    assert set(plan) == PLAN_KEYS
    assert plan["sessions"]
    for s in plan["sessions"]:
        assert set(s) == SESSION_KEYS | ({"result"} if with_result else set())
        assert s["type"] in {"calidad", "suave"}
        assert s["status"] in SESSION_STATUSES
        for b in s["blocks"]:
            assert BLOCK_REQUIRED <= set(b) <= BLOCK_REQUIRED | BLOCK_OPTIONAL
            assert b["kind"] in {"trote", "caminata"}
        if with_result and s["result"] is not None:
            assert set(s["result"]) == {"status", "rpe", "notes"}


# --- 401 en todos los endpoints autenticados (AC-73) ---------------------------


@pytest.mark.parametrize("method,path", AUTHENTICATED)
@pytest.mark.parametrize("authorization", [None, "Bearer no-es-un-jwt", "Basic abc"])
def test_authenticated_endpoints_reject_missing_or_invalid_token(client, method, path, authorization):
    headers = {"Authorization": authorization} if authorization else {}
    r = client.request(method.upper(), path, headers=headers, json={} if method in ("put", "post") else None)
    assert r.status_code == 401
    assert r.json() == {"detail": "No autenticado"}
    assert "X-Session-Token" not in r.headers


# --- /auth ------------------------------------------------------------------


def test_register(client):
    r = client.post("/auth/register", json={"email": "Milena@Example.com", "password": DEFAULT_PASSWORD})
    assert r.status_code == 201
    assert set(r.json()) == {"id", "email"}
    assert r.json()["email"] == EMAIL

    r = client.post("/auth/register", json={"email": EMAIL.upper(), "password": DEFAULT_PASSWORD})
    assert r.status_code == 409
    assert r.json() == {"detail": "El email ya está registrado"}


@pytest.mark.parametrize(
    "body",
    [
        {"email": "no-es-un-email", "password": DEFAULT_PASSWORD},
        {"email": EMAIL, "password": "x" * 7},
        {"email": EMAIL, "password": "x" * 129},
    ],
)
def test_register_validation_is_422(client, body):
    r = client.post("/auth/register", json=body)
    assert r.status_code == 422
    assert isinstance(detail(r), list)


def test_login(client):
    client.post("/auth/register", json={"email": EMAIL, "password": DEFAULT_PASSWORD})
    r = client.post("/auth/login", json={"email": EMAIL, "password": DEFAULT_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"access_token", "token_type", "expires_at"}
    assert body["token_type"] == "bearer"
    assert body["expires_at"].endswith("-03:00")

    for email, password in [(EMAIL, "otra-clave-mala"), (OTHER, DEFAULT_PASSWORD)]:
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 401
        assert r.json() == {"detail": "Credenciales inválidas"}


@pytest.mark.anyio
async def test_password_reset(client, conn, clock):
    seed_user(conn, EMAIL, chat_id=CHAT)
    text = await handle_restablecer(conn, clock, CHAT)
    code = text.split("es ", 1)[1].split(".", 1)[0]

    r = client.post("/auth/password-reset", json={"code": code, "new_password": "x" * 7})
    assert r.status_code == 422
    assert isinstance(detail(r), list)

    r = client.post("/auth/password-reset", json={"code": code, "new_password": "otra-clave-segura"})
    assert r.status_code == 200
    assert r.json() == {"detail": "Contraseña actualizada"}

    r = client.post("/auth/password-reset", json={"code": code, "new_password": "otra-clave-segura"})
    assert r.status_code == 400
    assert r.json() == {"detail": "Código inválido o vencido"}


# --- /profile ---------------------------------------------------------------


def test_get_profile_new_account_has_nulls(client):
    h = register_and_login(client, EMAIL)
    r = client.get("/profile", headers=h)
    assert r.status_code == 200
    assert has_renewed_token(r)
    body = r.json()
    assert set(body) == PROFILE_KEYS
    assert body["telegram_linked"] is False
    assert all(body[k] is None for k in PROFILE_KEYS - {"telegram_linked"})


def test_put_profile(client):
    h = register_and_login(client, EMAIL)
    r = client.put(
        "/profile",
        headers=h,
        json={
            "level": "intermedio",
            "frequency": 4,
            "target_distance_km": 10,
            "current_pace": "6:00",
            "city": "Rosario",
            "preferred_range": {"start": "07:00", "end": "09:00"},
            "send_time": "06:00",
        },
    )
    assert r.status_code == 200
    assert has_renewed_token(r)
    assert r.json() == {
        "level": "intermedio",
        "frequency": 4,
        "target_distance_km": 10.0,
        "current_pace": "6:00",
        "city": "Rosario",
        "preferred_range": {"start": "07:00", "end": "09:00"},
        "send_time": "06:00",
        "telegram_linked": False,
    }

    r = client.put("/profile", headers=h, json={"send_time": "09:00"})
    assert r.status_code == 422
    assert client.get("/profile", headers=h).json()["send_time"] == "06:00"


def test_delete_profile(client):
    h = register_and_login(client, EMAIL)
    r = client.delete("/profile", headers=h)
    assert r.status_code == 400
    assert r.json() == {
        "detail": "La eliminación es definitiva y no se puede deshacer. "
        "Repetí la solicitud con confirm=true para confirmar."
    }

    r = client.delete("/profile?confirm=true", headers=h)
    assert r.status_code == 204
    assert r.content == b""
    assert "X-Session-Token" not in r.headers


# --- /telegram/link-code ----------------------------------------------------


def test_link_code(client, conn):
    h = register_and_login(client, EMAIL)
    r = client.post("/telegram/link-code", headers=h)
    assert r.status_code == 201
    assert has_renewed_token(r)
    body = r.json()
    assert set(body) == {"code", "expires_at", "instructions"}
    assert body["instructions"] == f"Enviá /vincular {body['code']} al bot dentro de los 15 minutos."

    seed_link(conn, user_id_by_email(conn, EMAIL), CHAT)
    r = client.post("/telegram/link-code", headers=h)
    assert r.status_code == 409
    assert r.json() == {"detail": "Tu cuenta ya tiene un chat de Telegram vinculado"}


# --- /plan y /schedule ------------------------------------------------------


def test_post_plan_and_conflict(client, conn):
    h = ready_user(client, conn)
    r = client.post("/plan", headers=h)
    assert r.status_code == 201
    assert has_renewed_token(r)
    assert_plan_shape(r.json())

    r = client.post("/plan", headers=h)
    assert r.status_code == 409
    assert r.json() == {"detail": "Ya tenés un plan para la semana en curso"}


def test_post_plan_fixed_422_messages(client, conn):
    h = register_and_login(client, EMAIL)
    user_id = user_id_by_email(conn, EMAIL)
    seed_profile(conn, user_id, current_pace_s=None)
    r = client.post("/plan", headers=h)
    assert r.status_code == 422
    assert r.json() == {"detail": "No hay datos sobre tu ritmo cargados en tu perfil"}

    seed_profile(conn, user_id, city=None)
    r = client.post("/plan", headers=h)
    assert r.json() == {"detail": "No hay datos sobre tu ciudad cargados en tu perfil"}

    seed_profile(conn, user_id)
    r = client.post("/plan", headers=h)
    assert r.status_code == 422
    assert r.json() == {"detail": "Tu cuenta no tiene un chat de Telegram vinculado"}


def test_post_plan_ai_unavailable_is_503(client, conn, planner):
    planner.error = AIUnavailableError("timeout", "sin respuesta")
    h = ready_user(client, conn)
    r = client.post("/plan", headers=h)
    assert r.status_code == 503
    assert r.json() == {"detail": "No es posible generar un plan en este momento."}


def test_schedule(client, conn):
    h = ready_user(client, conn)
    r = client.get("/schedule", headers=h)
    assert r.status_code == 404
    assert r.json() == {"detail": "No tenés un plan para la semana en curso"}

    create_plan(client, h)
    r = client.get("/schedule", headers=h)
    assert r.status_code == 200
    assert has_renewed_token(r)
    assert_plan_shape(r.json(), with_result=True)


# --- /sessions/{id}/result y /history ---------------------------------------


def test_post_result_and_history(client, conn):
    h = ready_user(client, conn)
    plan = create_plan(client, h)
    sid = today_session_id(plan)

    r = client.get("/history", headers=h)
    assert r.status_code == 200
    assert has_renewed_token(r)
    assert r.json() == {"sessions": []}

    r = client.post(f"/sessions/{sid}/result", headers=h, json={"status": "completed", "rpe": 6, "notes": "bien"})
    assert r.status_code == 201
    assert has_renewed_token(r)
    body = r.json()
    assert set(body) == RESULT_KEYS
    assert body["session_id"] == sid and body["status"] == "completed" and body["rpe"] == 6

    r = client.post(f"/sessions/{sid}/result", headers=h, json={"status": "completed", "rpe": 6})
    assert r.status_code == 409
    assert r.json() == {"detail": "La sesión ya tiene un resultado registrado"}

    r = client.get("/history", headers=h)
    items = r.json()["sessions"]
    assert len(items) == 1
    assert set(items[0]) == HISTORY_KEYS
    assert items[0]["status"] in HISTORY_STATUSES
    assert items[0]["status"] == "Completada"

    r = client.get("/schedule", headers=h)
    today = next(s for s in r.json()["sessions"] if s["id"] == sid)
    assert today["result"] == {"status": "completed", "rpe": 6, "notes": "bien"}


def test_post_result_fixed_errors(client, conn):
    h = ready_user(client, conn)
    plan = create_plan(client, h)
    sid = today_session_id(plan)
    future = next(s["id"] for s in plan["sessions"] if s["status"] == "Proyectada")

    r = client.post("/sessions/999999/result", headers=h, json={"status": "skipped"})
    assert r.status_code == 404
    assert r.json() == {"detail": "Sesión no encontrada"}

    r = client.post(f"/sessions/{future}/result", headers=h, json={"status": "skipped"})
    assert r.status_code == 422
    assert r.json() == {"detail": "Solo podés registrar la sesión del día"}

    other = ready_user(client, conn, OTHER, chat_id=CHAT + 1)
    r = client.post(f"/sessions/{sid}/result", headers=other, json={"status": "skipped"})
    assert r.status_code == 403
    assert r.json() == {"detail": "Acceso denegado"}

    for body in [{"status": "completed"}, {"status": "partial", "rpe": 11}, {"status": "skipped", "rpe": 3}]:
        r = client.post(f"/sessions/{sid}/result", headers=h, json=body)
        assert r.status_code == 422
        assert isinstance(detail(r), list)

    conn.execute("UPDATE sessions SET system_status = 'postponed_weather' WHERE id = ?", (sid,))
    r = client.post(f"/sessions/{sid}/result", headers=h, json={"status": "skipped"})
    assert r.status_code == 422
    assert r.json() == {"detail": "La sesión fue pospuesta por clima y no admite registro"}
