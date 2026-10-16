"""Lectura de variables de entorno (principio II): ninguna credencial lleva valor por defecto."""

import os


class MissingConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingConfigError(f"{name} no está definida")
    return value


def google_api_key() -> str:
    return _required("GOOGLE_API_KEY")


def openweather_api_key() -> str:
    return _required("OPENWEATHER_API_KEY")


def jwt_secret() -> str:
    return _required("JWT_SECRET")


def telegram_bot_token() -> str | None:
    """Sin token, la API arranca sin el bot ni el scheduler (AGENTS.md)."""
    return os.environ.get("TELEGRAM_BOT_TOKEN") or None


def db_path() -> str:
    """No es un secreto: tiene valor por defecto."""
    return os.environ.get("RUNIA_DB_PATH") or "runia.db"
