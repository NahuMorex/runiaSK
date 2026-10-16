"""Dobles de prueba y helpers compartidos (los reexporta tests/conftest.py)."""

import asyncio
from datetime import date, datetime, timedelta

from app.ai.errors import AIUnavailableError
from app.ai.schemas import BlockOut, SessionOut, WeekPlanProposal
from app.clock import TZ

DEFAULT_PASSWORD = "clave-segura-1"


class FakePlanner:
    """`proposal` puede ser una WeekPlanProposal o un callable(req) -> WeekPlanProposal."""

    def __init__(self, proposal=None, error: Exception | None = None):
        self.proposal = proposal
        self.error = error
        self.requests = []

    async def __call__(self, req):
        self.requests.append(req)
        if self.error is not None:
            raise self.error
        proposal = self.proposal
        if callable(proposal) and not isinstance(proposal, WeekPlanProposal):
            proposal = proposal(req)
        if proposal is None:
            proposal = default_proposal(req)
        return proposal


class FakeWriter:
    def __init__(self, text: str | None = None, error: Exception | None = None, delay: float = 0):
        self.text = text
        self.error = error
        self.delay = delay
        self.calls = []

    async def __call__(self, data):
        self.calls.append(data)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        if self.text is None:
            raise AIUnavailableError("error", "FakeWriter sin texto")
        return self.text


class FakeWeather:
    def __init__(self, forecast=None, error: Exception | None = None):
        self.forecast = forecast
        self.error = error
        self.cities = []

    async def fetch_forecast(self, city: str):
        self.cities.append(city)
        if self.error is not None:
            raise self.error
        if self.forecast is None:
            from app.integrations.openweather import Forecast

            return Forecast(slots=[])
        return self.forecast


class FakeNotifier:
    def __init__(self, result: bool = True, delay: float = 0):
        self.result = result
        self.delay = delay
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> bool:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.messages.append((chat_id, text))
        return self.result


def easy_session(d: date, km: float, title: str = "Rodaje") -> SessionOut:
    return SessionOut(date=d, title=title, blocks=[BlockOut(kind="run", distance_km=km)])


def walk_run_session(d: date, run_km: float = 0.5, walk_km: float = 0.5, reps: int = 2) -> SessionOut:
    blocks = []
    for _ in range(reps):
        blocks.append(BlockOut(kind="walk", distance_km=walk_km))
        blocks.append(BlockOut(kind="run", distance_km=run_km))
    return SessionOut(date=d, title="Caminata y trote", blocks=blocks)


def quality_session(d: date, pace_s: int, reps: int = 2, rep_km: float = 1.0, warmup_km: float = 1.0) -> SessionOut:
    blocks = [BlockOut(kind="run", distance_km=warmup_km)]
    for i in range(reps):
        blocks.append(
            BlockOut(
                kind="run",
                distance_km=rep_km,
                target_pace_s=pace_s,
                recovery_after_s=120 if i < reps - 1 else None,
            )
        )
    return SessionOut(date=d, title="Intervalos", blocks=blocks)


def default_proposal(req) -> WeekPlanProposal:
    """Propuesta válida y moderada para cualquier PlanRequest."""
    dates = req.allowed_dates
    n = req.sessions_required
    step = max(1, len(dates) // n) if n else 1
    chosen = [dates[i * step] for i in range(n)] if n * step <= len(dates) else dates[:n]
    sessions = []
    for d in chosen:
        if req.first_week_novice:
            sessions.append(walk_run_session(d))
        else:
            sessions.append(easy_session(d, 2.0))
    return WeekPlanProposal(sessions=sessions)


def adverse_proposal(req, session_km: float = 20.0, quality_count: int = 3, pace_offset: int = -60) -> WeekPlanProposal:
    """Propuesta adversa: sesiones largas, varias de calidad y ritmos fuera de rango."""
    dates = req.allowed_dates[: req.sessions_required]
    if len(dates) < req.sessions_required:
        dates = req.allowed_dates
    pace = (req.current_pace_s or 360) + pace_offset
    sessions = []
    for i, d in enumerate(dates[: req.sessions_required]):
        if req.first_week_novice:
            sessions.append(walk_run_session(d, run_km=session_km / 2, walk_km=0.5, reps=2))
        elif i < quality_count:
            sessions.append(quality_session(d, pace, reps=2, rep_km=session_km / 4, warmup_km=session_km / 2))
        else:
            sessions.append(easy_session(d, session_km))
    return WeekPlanProposal(sessions=sessions)


def ba(y, m, d, hh=0, mm=0, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=TZ)


def register_and_login(client, email: str, password: str = DEFAULT_PASSWORD) -> dict:
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def user_id_by_email(conn, email: str) -> int:
    return conn.execute("SELECT id FROM users WHERE email = ?", (email.lower(),)).fetchone()["id"]


DEFAULT_PROFILE = {
    "level": "intermedio",
    "frequency": 4,
    "target_distance_hm": 1000,
    "current_pace_s": 360,
    "city": "Rosario",
    "range_start_min": 7 * 60,
    "range_end_min": 9 * 60,
    "send_time_min": 6 * 60,
}


def seed_profile(conn, user_id: int, **overrides) -> dict:
    profile = {**DEFAULT_PROFILE, **overrides}
    cols = list(profile)
    conn.execute(
        f"UPDATE profiles SET {', '.join(f'{c} = ?' for c in cols)} WHERE user_id = ?",
        (*[profile[c] for c in cols], user_id),
    )
    return profile


def seed_user(conn, email: str, *, chat_id: int | None = None, now: datetime | None = None, **profile) -> int:
    """Crea un usuario directo en la DB, con perfil completo y opcionalmente un vínculo."""
    from app import security
    from app.services import repository

    now = now or ba(2026, 10, 1)
    user_id = repository.create_user(conn, email, security.hash_password(DEFAULT_PASSWORD), now)
    seed_profile(conn, user_id, **profile)
    if chat_id is not None:
        seed_link(conn, user_id, chat_id, now)
    return user_id


def seed_link(conn, user_id: int, chat_id: int, now: datetime | None = None) -> None:
    conn.execute(
        "INSERT INTO telegram_links (user_id, chat_id, linked_at) VALUES (?, ?, ?)",
        (user_id, chat_id, (now or ba(2026, 10, 1)).isoformat()),
    )


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def seed_plan(
    conn,
    user_id: int,
    week_start: date,
    sessions,
    *,
    start_date: date | None = None,
    is_deload: bool = False,
    is_post_deload: bool = False,
    source: str = "monday",
    profile: dict | None = None,
) -> int:
    """Guarda un plan ya armado (lista de PlannedSession) con save_plan."""
    from app.domain import guardrails
    from app.domain.summaries import profile_snapshot
    from app.services import repository

    start_date = start_date or week_start
    profile = profile or repository.get_profile(conn, user_id)
    return repository.save_plan(
        conn,
        user_id,
        week_start=week_start,
        start_date=start_date,
        is_full=start_date == week_start,
        is_deload=is_deload,
        is_post_deload=is_post_deload,
        source=source,
        adopted_from_plan_id=None,
        planned_volume_hm=guardrails.planned_volume_hm(sessions),
        profile_snapshot=profile_snapshot(profile),
        sessions=sessions,
        now=ba(week_start.year, week_start.month, week_start.day),
    )


def seed_result(conn, session_id: int, user_id: int, status: str = "completed", rpe: int | None = 5, notes=None) -> None:
    conn.execute(
        "INSERT INTO session_results (session_id, user_id, status, rpe, notes, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, status, rpe, notes, ba(2026, 10, 1).isoformat()),
    )


def session_ids(conn, plan_id: int) -> list[int]:
    return [r["id"] for r in conn.execute("SELECT id FROM sessions WHERE plan_id = ? ORDER BY date", (plan_id,))]
