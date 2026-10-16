"""Aplicación FastAPI: API + bot de Telegram + scheduler en un solo proceso."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import audit, config, db
from app.api import auth, profile, telegram_link
from app.clock import SystemClock


async def _start_bot(app: FastAPI, token: str):
    from app.bot.handlers import build_application
    from app.services.notifier import TelegramNotifier

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
        conn = db.connect(app.state.db_path)
        try:
            db.init_db(conn)
        finally:
            conn.close()

        application = None
        token = config.telegram_bot_token()
        if start_background and token is not None:
            application = await _start_bot(app, token)
        else:
            audit.event("startup", bot=False)
        try:
            yield
        finally:
            if application is not None:
                await _stop_bot(application)

    app = FastAPI(title="Runia", lifespan=lifespan)
    app.state.db_path = db_path or config.db_path()
    app.state.clock = clock or SystemClock()
    app.state.planner = planner
    app.state.writer = writer
    app.state.weather = weather
    app.state.notifier = notifier

    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(telegram_link.router)
    return app


app = create_app()
