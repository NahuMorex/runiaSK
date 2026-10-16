"""Aplicación FastAPI: API + bot de Telegram + scheduler en un solo proceso."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app import audit, config, db, scheduler
from app.ai import draft_daily_message, propose_week_plan
from app.api import auth, plan, profile, sessions, telegram_link
from app.bot.handlers import build_application
from app.integrations import openweather
from app.clock import SystemClock
from app.services.notifier import TelegramNotifier


async def _start_bot(app: FastAPI, token: str):
    application = build_application(token, app.state)
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    if app.state.notifier is None:
        app.state.notifier = TelegramNotifier(application.bot)
    audit.event("startup", bot=True)
    return application


async def _stop_bot(application) -> None:
    await application.updater.stop()
    await application.stop()
    await application.shutdown()


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
        if app.state.uses_default_ai:
            config.google_api_key()
        if app.state.uses_default_weather:
            config.openweather_api_key()
        conn = db.connect(app.state.db_path)
        try:
            db.init_db(conn)
        finally:
            conn.close()

        application = None
        ticker = None
        token = config.telegram_bot_token()
        if start_background and token is not None:
            application = await _start_bot(app, token)
            ticker = asyncio.create_task(scheduler.run_forever(app.state))
        else:
            audit.event("startup", bot=False)
        try:
            yield
        finally:
            if ticker is not None:
                ticker.cancel()
                with suppress(asyncio.CancelledError):
                    await ticker
            if application is not None:
                await _stop_bot(application)

    app = FastAPI(title="Runia", lifespan=lifespan)
    app.state.db_path = db_path or config.db_path()
    app.state.clock = clock or SystemClock()
    app.state.uses_default_ai = planner is None or writer is None
    app.state.planner = planner or propose_week_plan
    app.state.writer = writer or draft_daily_message
    app.state.uses_default_weather = weather is None
    app.state.weather = weather or openweather
    app.state.notifier = notifier

    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(telegram_link.router)
    app.include_router(plan.router)
    app.include_router(sessions.router)
    return app


app = create_app()
