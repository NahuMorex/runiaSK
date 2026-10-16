"""Bot de Telegram (contracts/telegram-bot.md).

Las funciones núcleo (`handle_*`) reciben conexión, reloj y chat y devuelven el texto a responder;
los adaptadores PTB solo abren la conexión y responden con ese texto.
"""

import sqlite3

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from app import db
from app.clock import Clock
from app.services import linking

START_TEXT = "Hola, soy Runia. Para vincular tu cuenta, generá un código en la API y enviá /vincular <código>."
LINK_OK = "Listo: tu cuenta quedó vinculada a este chat."
LINK_INVALID = "El código no es válido o ya venció."
LINK_ALREADY = "Este chat o tu cuenta ya tienen un vínculo y no se puede modificar."


async def handle_start() -> str:
    return START_TEXT


async def handle_vincular(conn: sqlite3.Connection, clock: Clock, chat_id: int, args: list[str]) -> str:
    if not args:
        return LINK_INVALID
    outcome = linking.link_chat(conn, chat_id, args[0], clock)
    return {"linked": LINK_OK, "invalid": LINK_INVALID, "already_linked": LINK_ALREADY}[outcome]


# --- Adaptadores PTB --------------------------------------------------------


def build_application(token: str, app_state) -> Application:
    async def _reply(update: Update, text: str | None) -> None:
        if text is not None and update.message is not None:
            await update.message.reply_text(text)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply(update, await handle_start())

    async def vincular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        conn = db.connect(app_state.db_path)
        try:
            text = await handle_vincular(conn, app_state.clock, update.effective_chat.id, context.args or [])
        finally:
            conn.close()
        await _reply(update, text)

    application = ApplicationBuilder().token(token).concurrent_updates(True).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("vincular", vincular))
    return application
