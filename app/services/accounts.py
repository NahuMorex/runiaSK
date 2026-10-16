"""Registro, login, restablecimiento de contraseña y borrado de cuenta."""

import sqlite3
from datetime import timedelta

from app import audit, security
from app.clock import Clock
from app.db import transaction
from app.services import repository


class EmailTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidResetCode(Exception):
    pass


RESET_CODE_LENGTH = 10
RESET_CODE_TTL = timedelta(minutes=30)


def register(conn: sqlite3.Connection, email: str, password: str, now) -> int:
    with transaction(conn):
        if repository.get_user_by_email(conn, email) is not None:
            raise EmailTakenError(email)
        user_id = repository.create_user(conn, email, security.hash_password(password), now)
    audit.event("tool_call", tool="db", op="register", user_id=user_id)
    return user_id


def login(conn: sqlite3.Connection, email: str, password: str, clock: Clock):
    user = repository.get_user_by_email(conn, email)
    if user is None or not security.verify_password(user["password_hash"], password):
        audit.event("tool_call", tool="db", op="login", outcome="invalid")
        raise InvalidCredentialsError()
    now = clock.now()
    token, expires_at = security.create_token(user["id"], now, now)
    audit.event("tool_call", tool="db", op="login", outcome="ok", user_id=user["id"])
    return token, expires_at


def create_reset_code(conn: sqlite3.Connection, user_id: int, clock: Clock) -> str:
    """Código de 10 caracteres que vence en 30 min (R-16). Solo se guarda su hash y nunca se registra."""
    code = security.generate_code(RESET_CODE_LENGTH)
    with transaction(conn):
        repository.create_code(conn, user_id, "reset", security.hash_code(code), clock.now() + RESET_CODE_TTL)
    audit.event("tool_call", tool="db", op="create_reset_code", user_id=user_id)
    return code


def reset_password(conn: sqlite3.Connection, code: str, new_password: str, clock: Clock) -> None:
    """Consume el código y cambia el hash en la misma transacción."""
    outcome = "invalid"
    try:
        with transaction(conn):
            user_id = repository.consume_code(conn, "reset", security.hash_code(code), clock.now())
            if user_id is None:
                raise InvalidResetCode()
            repository.update_password_hash(conn, user_id, security.hash_password(new_password))
            outcome = "ok"
    finally:
        audit.event("tool_call", tool="db", op="reset_password", outcome=outcome)


def delete_account(conn: sqlite3.Connection, user_id: int) -> None:
    with transaction(conn):
        repository.delete_user(conn, user_id)
    audit.event("tool_call", tool="db", op="delete_account", user_id=user_id)
