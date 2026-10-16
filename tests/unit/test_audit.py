"""Auditoría (R-18, FR-045) y ausencia de secretos en los logs (SC-008)."""

import json
import logging
import traceback
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from telegram.error import InvalidToken

from app import audit, main, scheduler
from app.ai import gemini
from app.ai.schemas import WeekPlanProposal
from app.bot.handlers import build_application, handle_restablecer, handle_text, handle_vincular
from app.clock import FixedClock
from app.domain.models import Block, PlannedSession
from app.integrations import openweather
from app.main import create_app
from tests.conftest import FAKE_GOOGLE_API_KEY, FAKE_OPENWEATHER_API_KEY
from tests.helpers import DEFAULT_PASSWORD, FakeNotifier, ba, easy_session, seed_plan, seed_user

FAKE_BOT_TOKEN = "000000:fake-telegram-bot-token"
NEW_PASSWORD = "otra-clave-segura"
EMAIL = "milena@example.com"
CHAT_A, CHAT_FAIL, CHAT_STORM = 101, 102, 103
WEEK = date(2026, 10, 12)
FRI = date(2026, 10, 16)
NEXT_MONDAY = date(2026, 10, 19)
DB_OPS = {
    "register",
    "login",
    "update_profile",
    "create_link_code",
    "link_chat",
    "save_plan",
    "adopt_plan",
    "register_result",
    "set_session_postponed",
    "create_dispatch",
    "set_dispatch_sent",
    "create_reset_code",
    "reset_password",
    "delete_account",
}


# --- redact -----------------------------------------------------------------


def test_redact_hides_sensitive_keys_also_nested():
    data = {
        "user_id": 7,
        "password": "p",
        "access_token": "t",
        "api_key": "k",
        "code": "c",
        "Authorization": "Bearer x",
        "nested": {"new_password": "p2", "items": [{"code": "c2", "keep": 1}], "headers": {"authorization": "y"}},
    }
    out = audit.redact(data)
    assert out == {
        "user_id": 7,
        "password": audit.REDACTED,
        "access_token": audit.REDACTED,
        "api_key": audit.REDACTED,
        "code": audit.REDACTED,
        "Authorization": audit.REDACTED,
        "nested": {
            "new_password": audit.REDACTED,
            "items": [{"code": audit.REDACTED, "keep": 1}],
            "headers": {"authorization": audit.REDACTED},
        },
    }


def test_event_writes_redacted_json(caplog):
    caplog.set_level(logging.INFO, logger="runia.audit")
    audit.event("tool_call", tool="db", op="login", password="secreta", user_id=1)
    record = json.loads(caplog.records[-1].getMessage())
    assert record["type"] == "tool_call" and record["password"] == audit.REDACTED
    assert "secreta" not in caplog.text


class RejectingApplication:
    """Aplicación de PTB cuyo initialize() falla como con un token rechazado por Telegram."""

    def __init__(self, token: str):
        self.token = token
        self.shutdown_called = False

    async def initialize(self):
        try:
            raise InvalidToken("Unauthorized: invalid token specified")
        except InvalidToken as exc:
            raise InvalidToken(f"The token `{self.token}` was rejected by the server.") from exc

    async def shutdown(self):
        self.shutdown_called = True


def test_rejected_bot_token_does_not_leak_on_startup(db_path, monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_BOT_TOKEN)
    rejecting = RejectingApplication(FAKE_BOT_TOKEN)
    monkeypatch.setattr(main, "build_application", lambda token, state: rejecting)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(main.BotStartupError) as excinfo:
        with TestClient(main.create_app(db_path=db_path, notifier=FakeNotifier(), weather=MockedOpenWeather())):
            pass

    rendered = "".join(traceback.format_exception(excinfo.value))
    assert "InvalidToken" in rendered
    assert FAKE_BOT_TOKEN not in rendered
    assert FAKE_BOT_TOKEN not in caplog.text
    assert rejecting.shutdown_called
    assert any(
        ev["type"] == "external_error" and ev["service"] == "telegram" and ev["reason"] == "InvalidToken"
        for ev in _events(caplog)
    )


# --- Dobles: cliente de google-genai y transporte de OpenWeatherMap -----------


class FakeGenaiClient:
    """Reemplaza a `genai.Client` para que corra el código real de app/ai/gemini.py."""

    def __init__(self):
        self.fail_plan = False
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, *, model, contents, config):
        if config.response_mime_type == "application/json":
            if self.fail_plan:
                raise RuntimeError("gemini caído")
            # Propuesta adversa: 4 sesiones de 20 km, que los guardarraíles recortan.
            days = [date(2026, 10, 15) + timedelta(days=i) for i in range(4)]
            return SimpleNamespace(text=WeekPlanProposal(sessions=[easy_session(d, 20.0) for d in days]).model_dump_json())
        return SimpleNamespace(text="Hoy toca un rodaje suave.")


def _slot(d: date, hour: int, *, thunder: bool) -> dict:
    start = datetime(d.year, d.month, d.day, hour, tzinfo=ba(2026, 1, 1).tzinfo).astimezone(timezone.utc)
    return {
        "dt": int(start.timestamp()),
        "pop": 0.1,
        "main": {"temp": 20.0},
        "weather": [{"id": 211 if thunder else 800}],
    }


def _openweather_handler(request: httpx.Request) -> httpx.Response:
    if request.url.params["q"].startswith("Fallalandia"):
        return httpx.Response(401, json={"cod": 401, "message": "Invalid API key"})
    return httpx.Response(200, json={"list": [_slot(FRI, 6, thunder=True)]})


class MockedOpenWeather:
    """El cliente real de app/integrations/openweather.py sobre un transporte httpx mockeado."""

    def __init__(self):
        self.transport = httpx.MockTransport(_openweather_handler)

    async def fetch_forecast(self, city: str):
        return await openweather.fetch_forecast(city, transport=self.transport)


# --- Flujos completos ----------------------------------------------------------


def _events(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "runia.audit"]


def _bearer(r) -> dict:
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.anyio
async def test_flows_emit_audit_events_without_secrets(conn, db_path, clock, caplog, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_BOT_TOKEN)
    audit.configure_logging()
    caplog.set_level(logging.DEBUG)

    genai_client = FakeGenaiClient()
    monkeypatch.setattr(gemini, "_client_instance", genai_client)
    notifier = FakeNotifier()
    app = create_app(
        db_path=db_path, clock=clock, weather=MockedOpenWeather(), notifier=notifier, start_background=False
    )
    build_application(FAKE_BOT_TOKEN, app.state)
    secrets = {DEFAULT_PASSWORD, NEW_PASSWORD, FAKE_BOT_TOKEN, FAKE_OPENWEATHER_API_KEY, FAKE_GOOGLE_API_KEY}

    # Cuenta, perfil, vínculo, plan con recorte, registro con reclasificación, reseteo y borrado (jueves 10:00).
    with TestClient(app) as client:
        assert client.post("/auth/register", json={"email": EMAIL, "password": DEFAULT_PASSWORD}).status_code == 201
        h = _bearer(client.post("/auth/login", json={"email": EMAIL, "password": DEFAULT_PASSWORD}))
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
        secrets |= {h["Authorization"].split()[1], r.headers["X-Session-Token"]}

        link_code = client.post("/telegram/link-code", headers=h).json()["code"]
        assert (await handle_vincular(conn, clock, CHAT_A, [link_code])).startswith("Listo")

        r = client.post("/plan", headers=h)
        assert r.status_code == 201
        assert max(s["run_km"] for s in r.json()["sessions"]) <= 5.0
        today_id = next(s["id"] for s in r.json()["sessions"] if s["status"] == "Hoy")

        r = client.post(f"/sessions/{today_id}/result", headers=h, json={"status": "partial", "rpe": 8})
        assert r.status_code == 201 and r.json()["reclassified_sessions"]

        reset_text = await handle_restablecer(conn, clock, CHAT_A)
        reset_code = reset_text.split("es ", 1)[1].split(".", 1)[0]
        r = client.post("/auth/password-reset", json={"code": reset_code, "new_password": NEW_PASSWORD})
        assert r.status_code == 200

        h = _bearer(client.post("/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}))
        secrets.add(h["Authorization"].split()[1])
        assert client.delete("/profile?confirm=true", headers=h).status_code == 204
    secrets |= {link_code, reset_code}

    # Dispatch del viernes: una ciudad con falla de clima y otra con tormenta sin alternativa (posposición).
    easy = [Block("run", 400)]
    fail_uid = seed_user(conn, "falla@example.com", chat_id=CHAT_FAIL, city="Fallalandia")
    storm_uid = seed_user(conn, "tormenta@example.com", chat_id=CHAT_STORM, city="Rosario")
    for uid in (fail_uid, storm_uid):
        seed_plan(conn, uid, WEEK, [PlannedSession(FRI, "Rodaje", easy)], start_date=WEEK)
    await scheduler.tick(app.state, ba(2026, 10, 16, 6, 0))
    await handle_text(conn, FixedClock(ba(2026, 10, 16, 6, 10)), notifier, app.state.writer, CHAT_FAIL, "5")

    # Lunes siguiente con Gemini caído: fallback al último plan válido.
    genai_client.fail_plan = True
    await scheduler.tick(app.state, ba(2026, 10, 19, 0, 1))

    events = _events(caplog)
    by_type: dict[str, list[dict]] = {}
    for ev in events:
        by_type.setdefault(ev["type"], []).append(ev)

    for t in ("llm_call", "tool_call", "guardrail", "session_postponed", "external_error", "weather_decision"):
        assert by_type.get(t), f"falta el evento {t}"

    assert {ev["operation"] for ev in by_type["llm_call"]} == {"plan", "daily_message"}
    assert {ev["outcome"] for ev in by_type["llm_call"] if ev["operation"] == "plan"} == {"ok", "error"}
    assert {ev["tool"] for ev in by_type["tool_call"]} == {"db", "weather"}
    assert {ev["op"] for ev in by_type["tool_call"] if ev["tool"] == "db"} == DB_OPS
    assert all("before" in ev and "after" in ev for ev in by_type["guardrail"])
    assert {ev["rule"] for ev in by_type["guardrail"]} >= {"reclassification"}
    assert len(by_type["guardrail"]) > 1  # además de la reclasificación, hubo recortes del plan
    assert any(ev["service"] == "openweather" for ev in by_type["external_error"])
    assert any(ev["postpone"] for ev in by_type["weather_decision"])
    assert by_type["session_postponed"][0]["user_id"] == storm_uid

    # SC-008: ningún registro de ningún logger contiene un secreto usado en el test.
    assert caplog.records
    for record in caplog.records:
        line = record.getMessage()
        for secret in secrets:
            assert secret not in line, f"{record.name} filtró un secreto"
    for secret in secrets:
        assert secret not in caplog.text
