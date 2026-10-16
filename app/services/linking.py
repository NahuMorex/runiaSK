"""Códigos de vinculación y vínculo de chat (FR-011, R-16)."""

import sqlite3
from datetime import timedelta
from typing import Literal

from app import audit, security
from app.clock import Clock
from app.db import transaction
from app.services import repository

LINK_CODE_LENGTH = 8
LINK_CODE_TTL = timedelta(minutes=15)


class AlreadyLinkedError(Exception):
    pass


def create_link_code(conn: sqlite3.Connection, user_id: int, clock: Clock):
    if repository.get_chat_id(conn, user_id) is not None:
        raise AlreadyLinkedError()
    code = security.generate_code(LINK_CODE_LENGTH)
    expires_at = clock.now() + LINK_CODE_TTL
    with transaction(conn):
        repository.create_code(conn, user_id, "link", security.hash_code(code), expires_at)
    audit.event("tool_call", tool="db", op="create_link_code", user_id=user_id)
    return code, expires_at


def link_chat(conn: sqlite3.Connection, chat_id: int, code: str, clock: Clock) -> Literal["linked", "invalid", "already_linked"]:
    now = clock.now()
    code_hash = security.hash_code(code)
    with transaction(conn):
        user_id = repository.find_valid_code(conn, "link", code_hash, now)
        if user_id is None:
            outcome = "invalid"
        elif repository.get_user_by_chat(conn, chat_id) is not None or repository.get_chat_id(conn, user_id) is not None:
            outcome = "already_linked"
        else:
            repository.consume_code(conn, "link", code_hash, now)
            repository.create_link(conn, user_id, chat_id, now)
            outcome = "linked"
    audit.event("tool_call", tool="db", op="link_chat", outcome=outcome)
    return outcome
