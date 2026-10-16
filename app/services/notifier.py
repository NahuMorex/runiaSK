"""Envíos salientes por Telegram (contracts/telegram-bot.md)."""

from typing import Protocol

from telegram import Bot
from telegram.error import TelegramError

from app import audit


class Notifier(Protocol):
    async def send_message(self, chat_id: int, text: str) -> bool: ...


class TelegramNotifier:
    def __init__(self, bot: Bot):
        self._bot = bot

    async def send_message(self, chat_id: int, text: str) -> bool:
        """Solo audita las fallas: `message_sent` lo emite el flujo diario, con plantilla o modelo (R-18)."""
        try:
            await self._bot.send_message(chat_id=chat_id, text=text)
        except TelegramError as exc:
            audit.event("external_error", service="telegram", reason=type(exc).__name__)
            return False
        return True
