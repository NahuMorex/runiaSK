"""Bot de Telegram (contracts/telegram-bot.md).

Las funciones núcleo (`handle_*`) reciben conexión, reloj y chat y devuelven el texto a responder;
los adaptadores PTB solo abren la conexión y responden con ese texto.
"""

import sqlite3

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from app import db
from app.clock import Clock
from app.services import daily_service, linking, plan_service, repository, results

START_TEXT = "Hola, soy Runia. Para vincular tu cuenta, generá un código en la API y enviá /vincular <código>."
LINK_OK = "Listo: tu cuenta quedó vinculada a este chat."
LINK_INVALID = "El código no es válido o ya venció."
LINK_ALREADY = "Este chat o tu cuenta ya tienen un vínculo y no se puede modificar."
NOT_LINKED = "Este chat no está vinculado a ninguna cuenta."
NO_SESSION_TODAY = "No tenés una sesión planificada para hoy."
POSTPONED_TODAY = "La sesión de hoy fue pospuesta por clima y no admite registro."
ALREADY_REGISTERED = "La sesión de hoy ya tiene un resultado registrado."
RPE_REQUIRED = "Indicá un RPE entero de 1 a 10. Ejemplo: /registrar completada 6"
INVALID_STATUS = "Estados válidos: completada, parcial, salteada."

STATUS_BY_WORD = {"completada": "completed", "parcial": "partial", "salteada": "skipped"}
MAX_NOTES = 500
# Ante Forbidden o SessionNotFound el texto es genérico: no revela datos de otros usuarios (AC-38).
REGISTRAR_ERRORS = {
    results.SessionNotFound: NO_SESSION_TODAY,
    results.Forbidden: NO_SESSION_TODAY,
    results.NotToday: NO_SESSION_TODAY,
    results.PostponedSession: POSTPONED_TODAY,
    results.AlreadyRegistered: ALREADY_REGISTERED,
    results.InvalidRpe: RPE_REQUIRED,
}


async def handle_start() -> str:
    return START_TEXT


async def handle_vincular(conn: sqlite3.Connection, clock: Clock, chat_id: int, args: list[str]) -> str:
    if not args:
        return LINK_INVALID
    outcome = linking.link_chat(conn, chat_id, args[0], clock)
    return {"linked": LINK_OK, "invalid": LINK_INVALID, "already_linked": LINK_ALREADY}[outcome]


def _parse_rpe(text: str | None) -> int | None:
    if text is None or not text.isdigit():
        return None
    value = int(text)
    return value if 1 <= value <= 10 else None


async def handle_registrar(conn: sqlite3.Connection, clock: Clock, chat_id: int, args: list[str]) -> str:
    """/registrar <estado> [rpe] [notas…] sobre la sesión de hoy del usuario vinculado al chat (R-08)."""
    user_id = repository.get_user_by_chat(conn, chat_id)
    if user_id is None:
        return NOT_LINKED
    status = STATUS_BY_WORD.get(args[0].lower()) if args else None
    if status is None:
        return INVALID_STATUS
    today = clock.now().date()
    session = repository.get_session_for_user_on(conn, user_id, today)
    if session is None:
        return NO_SESSION_TODAY

    if status == "skipped":
        rpe, note_words = None, args[1:]
    else:
        rpe = _parse_rpe(args[1] if len(args) > 1 else None)
        if rpe is None:
            return RPE_REQUIRED
        note_words = args[2:]
    notes = " ".join(note_words)[:MAX_NOTES] or None

    try:
        out = results.register_result(conn, user_id, session["id"], status, rpe, notes, today, clock)
    except tuple(REGISTRAR_ERRORS) as exc:
        return REGISTRAR_ERRORS[type(exc)]
    text = f"Registré tu sesión de hoy como {plan_service.RESULT_LABELS[status]}."
    affected = len(out["reclassified_sessions"]) + out["pending_reclassification"]
    if affected:
        text += f" Las próximas {affected} sesiones pasan a suave/recuperación."
    return text


async def handle_text(conn: sqlite3.Connection, clock: Clock, notifier, writer, chat_id: int, text: str) -> str | None:
    """Texto libre: si hay una pregunta de fatiga abierta, es la respuesta (FR-029). None = no responder."""
    return await daily_service.handle_fatigue_reply(conn, clock, notifier, writer, chat_id, text)


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

    async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        conn = db.connect(app_state.db_path)
        try:
            text = await handle_registrar(conn, app_state.clock, update.effective_chat.id, context.args or [])
        finally:
            conn.close()
        await _reply(update, text)

    async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        conn = db.connect(app_state.db_path)
        try:
            text = await handle_text(
                conn,
                app_state.clock,
                app_state.notifier,
                app_state.writer,
                update.effective_chat.id,
                update.message.text if update.message else "",
            )
        finally:
            conn.close()
        await _reply(update, text)

    application = ApplicationBuilder().token(token).concurrent_updates(True).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("vincular", vincular))
    application.add_handler(CommandHandler("registrar", registrar))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    return application
