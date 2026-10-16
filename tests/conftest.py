import pytest
from fastapi.testclient import TestClient

from app import db
from app.clock import FixedClock
from app.main import create_app
from tests.helpers import (  # noqa: F401  (reexportados para los tests)
    FakeNotifier,
    FakePlanner,
    FakeWeather,
    FakeWriter,
    ba,
    register_and_login,
    seed_link,
    seed_profile,
    seed_user,
)

FAKE_JWT_SECRET = "test-jwt-secret-no-real-0123456789abcdef"
FAKE_GOOGLE_API_KEY = "fake-google-key"
FAKE_OPENWEATHER_API_KEY = "fake-openweather-key"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", FAKE_JWT_SECRET)
    monkeypatch.setenv("GOOGLE_API_KEY", FAKE_GOOGLE_API_KEY)
    monkeypatch.setenv("OPENWEATHER_API_KEY", FAKE_OPENWEATHER_API_KEY)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "runia-test.db")


@pytest.fixture
def conn(db_path):
    c = db.connect(db_path)
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def clock():
    """Jueves 2026-10-15 10:00 en Buenos Aires."""
    return FixedClock(ba(2026, 10, 15, 10, 0))


@pytest.fixture
def planner():
    return FakePlanner()


@pytest.fixture
def writer():
    return FakeWriter()


@pytest.fixture
def weather():
    return FakeWeather()


@pytest.fixture
def notifier():
    return FakeNotifier()


@pytest.fixture
def app(db_path, conn, clock, planner, writer, weather, notifier):
    return create_app(
        db_path=db_path,
        clock=clock,
        planner=planner,
        writer=writer,
        weather=weather,
        notifier=notifier,
        start_background=False,
    )


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
