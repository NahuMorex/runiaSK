"""Aplicación FastAPI: API + bot de Telegram + scheduler en un solo proceso."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import audit, config, db
from app.api import auth, profile
from app.clock import SystemClock


def create_app(
    *,
    db_path: str | None = None,
    clock=None,
    planner=None,
    writer=None,
    weather=None,
    notifier=None,
    start_background: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        audit.configure_logging()
        config.jwt_secret()  # sin JWT_SECRET la app no arranca (principio II)
        conn = db.connect(app.state.db_path)
        try:
            db.init_db(conn)
        finally:
            conn.close()
        yield

    app = FastAPI(title="Runia", lifespan=lifespan)
    app.state.db_path = db_path or config.db_path()
    app.state.clock = clock or SystemClock()
    app.state.planner = planner
    app.state.writer = writer
    app.state.weather = weather
    app.state.notifier = notifier
    app.state.start_background = start_background

    app.include_router(auth.router)
    app.include_router(profile.router)
    return app


app = create_app()
