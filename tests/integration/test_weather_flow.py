import json
import logging
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app import scheduler
from app.bot.handlers import handle_text
from app.clock import FixedClock
from app.domain.models import Block, PlannedSession
from app.integrations.openweather import Forecast, Slot, WeatherUnavailableError
from app.services import repository
from tests.helpers import FakeNotifier, FakeWeather, FakeWriter, ba, seed_plan, seed_user

pytestmark = pytest.mark.anyio

WED = date(2026, 10, 14)
TODAY = date(2026, 10, 15)  # jueves
WEEK = date(2026, 10, 12)
CHAT = 42
QUESTION = "¿Cómo está tu fatiga hoy del 1 al 10? Respondé con un número."
NO_ALTERNATIVE = "No hay una alternativa disponible esta semana"
UNAVAILABLE = "Clima no disponible: seguí las pautas base de ritmo e hidratación."
EASY = [Block("run", 400)]


def slots_for(days: dict[date, dict]) -> Forecast:
    """Un intervalo 06:00–09:00 por día (cubre el rango 07:00–09:00 del perfil por defecto)."""
    slots = []
    for d, cond in days.items():
        slots.append(
            Slot(
                start=ba(d.year, d.month, d.day, 6),
                pop_pct=cond.get("pop", 10),
                temp_c=cond.get("temp", 20.0),
                thunderstorm=cond.get("thunder", False),
            )
        )
    return Forecast(slots=slots)


def week_days(start: date, **cond) -> dict[date, dict]:
    end = WEEK + timedelta(days=6)
    return {start + timedelta(days=i): dict(cond) for i in range((end - start).days + 1)}


def state(db_path, weather, notifier=None):
    return SimpleNamespace(db_path=db_path, planner=None, writer=FakeWriter(), weather=weather, notifier=notifier or FakeNotifier())


def seed(conn, days=(TODAY,)):
    uid = seed_user(conn, "a@example.com", chat_id=CHAT)
    plan_id = seed_plan(conn, uid, WEEK, [PlannedSession(d, "Rodaje", EASY) for d in days], start_date=WEEK)
    return uid, plan_id


def dispatch(conn, uid, day=TODAY):
    return conn.execute("SELECT * FROM daily_dispatches WHERE user_id = ? AND date = ?", (uid, day.isoformat())).fetchone()


def session_on(conn, uid, day=TODAY):
    return repository.get_session_for_user_on(conn, uid, day)


def audit_events(caplog, type_):
    out = []
    for r in caplog.records:
        if r.name == "runia.audit":
            ev = json.loads(r.getMessage())
            if ev["type"] == type_:
                out.append(ev)
    return out


async def ask_and_reply(conn, st, day=TODAY, fatigue="5"):
    await scheduler.tick(st, ba(day.year, day.month, day.day, 6, 0))
    await handle_text(conn, FixedClock(ba(day.year, day.month, day.day, 6, 10)), st.notifier, st.writer, CHAT, fatigue)


async def test_unfavorable_with_alternative_alerts_and_keeps_session(conn, db_path, caplog):
    caplog.set_level(logging.INFO, logger="runia.audit")
    uid, _ = seed(conn)
    days = {TODAY: {"pop": 70}, TODAY + timedelta(days=1): {}}
    st = state(db_path, FakeWeather(slots_for(days)))
    await ask_and_reply(conn, st)

    assert st.notifier.messages[0] == (CHAT, QUESTION)
    text = st.notifier.messages[1][1]
    assert "Alerta climática: lluvia probable (70%)." in text
    assert "Día alternativo: viernes." in text
    assert session_on(conn, uid)["system_status"] is None
    d = dispatch(conn, uid)
    assert d["state"] == "sent" and json.loads(d["weather_json"])["alternative_date"] == "2026-10-16"
    decision = audit_events(caplog, "weather_decision")[-1]
    assert decision["unfavorable"] is True and decision["postpone"] is False
    assert decision["alternative"] == "2026-10-16"


async def test_unfavorable_without_alternative_stays_executable(conn, db_path):
    uid, _ = seed(conn)
    st = state(db_path, FakeWeather(slots_for(week_days(TODAY, temp=34.0))))
    await ask_and_reply(conn, st)

    text = st.notifier.messages[1][1]
    assert "Alerta climática: calor extremo (34 °C)." in text and NO_ALTERNATIVE in text
    assert "Día alternativo" not in text
    assert session_on(conn, uid)["system_status"] is None


async def test_extreme_without_alternative_postpones(conn, db_path, caplog):
    caplog.set_level(logging.INFO, logger="runia.audit")
    uid, _ = seed(conn)
    st = state(db_path, FakeWeather(slots_for(week_days(TODAY, pop=90))))
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))

    s = session_on(conn, uid)
    assert s["system_status"] == "postponed_weather" and s["postponed_reason"] == "lluvia probable (90%)"
    assert len(st.notifier.messages) == 1
    chat, text = st.notifier.messages[0]
    assert chat == CHAT and text.startswith("Tu sesión de hoy quedó pospuesta por clima: lluvia probable (90%).")
    assert QUESTION not in text and len(text.split()) <= 150 and "sesiones pospuestas" not in text
    d = dispatch(conn, uid)
    assert d["state"] == "postponed_sent" and d["delivered"] == 1
    assert audit_events(caplog, "session_postponed")
    ops = [e["op"] for e in audit_events(caplog, "tool_call") if e.get("tool") == "db"]
    assert "set_session_postponed" in ops and "create_dispatch" in ops

    # Una respuesta posterior o los ticks siguientes no envían nada más.
    assert await handle_text(conn, FixedClock(ba(2026, 10, 15, 6, 10)), st.notifier, st.writer, CHAT, "5") is None
    await scheduler.tick(st, ba(2026, 10, 15, 6, 1))
    await scheduler.tick(st, ba(2026, 10, 15, 8, 30))
    assert len(st.notifier.messages) == 1


async def test_postponement_delivery_failure_is_recorded(conn, db_path):
    uid, _ = seed(conn)
    st = state(db_path, FakeWeather(slots_for(week_days(TODAY, thunder=True))), notifier=FakeNotifier(result=False))
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    d = dispatch(conn, uid)
    assert d["state"] == "postponed_sent" and d["delivered"] == 0


async def test_second_postponement_in_week_reports_count(conn, db_path):
    uid, _ = seed(conn, days=(WED, TODAY))
    st = state(db_path, FakeWeather(slots_for(week_days(WED, pop=90))))
    await scheduler.tick(st, ba(2026, 10, 14, 6, 0))
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))

    first, second = (text for _, text in st.notifier.messages)
    assert "sesiones pospuestas" not in first
    assert second.endswith(" Esta semana ya tenés 2 sesiones pospuestas por clima.")
    assert session_on(conn, uid, WED)["system_status"] == session_on(conn, uid)["system_status"] == "postponed_weather"


async def test_weather_failure_sends_without_adjustment(conn, db_path, caplog):
    caplog.set_level(logging.INFO, logger="runia.audit")
    uid, _ = seed(conn)
    st = state(db_path, FakeWeather(error=WeatherUnavailableError("timeout")))
    await ask_and_reply(conn, st)

    assert st.notifier.messages[0] == (CHAT, QUESTION)
    text = st.notifier.messages[1][1]
    assert UNAVAILABLE in text and "Alerta climática" not in text
    assert json.loads(dispatch(conn, uid)["weather_json"]) == {"available": False}
    errors = [e for e in audit_events(caplog, "external_error") if e["service"] == "openweather"]
    assert errors and errors[-1]["reason"] == "timeout"


async def test_city_change_is_used_in_next_query(conn, db_path, client, weather):
    seed(conn, days=(TODAY, TODAY + timedelta(days=1)))
    st = state(db_path, weather)
    await scheduler.tick(st, ba(2026, 10, 15, 6, 0))
    assert weather.cities == ["Rosario"]

    r = client.post("/auth/login", json={"email": "a@example.com", "password": "clave-segura-1"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.put("/profile", json={"city": "Córdoba"}, headers=headers).status_code == 200

    await scheduler.tick(st, ba(2026, 10, 16, 6, 0))
    assert weather.cities == ["Rosario", "Córdoba"]
