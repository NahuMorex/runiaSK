"""Registro, login, restablecimiento de contraseña y borrado de cuenta."""

import sqlite3

from app import audit, security
from app.clock import Clock
from app.db import transaction
from app.services import repository


class EmailTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


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
