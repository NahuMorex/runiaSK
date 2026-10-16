"""Todo el SQL de Runia vive en este archivo."""

import json
import sqlite3
from datetime import date, datetime

from app.clock import TZ, Clock
from app.domain.models import Block, PlannedSession

PROFILE_FIELDS = (
    "level",
    "frequency",
    "target_distance_hm",
    "current_pace_s",
    "city",
    "range_start_min",
    "range_end_min",
    "send_time_min",
)


def _iso(value) -> str:
    """Instantes en ISO con offset de Buenos Aires y precisión de segundos, para que comparen como texto."""
    if isinstance(value, datetime):
        return value.astimezone(TZ).isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def now_iso(clock: Clock) -> str:
    return _iso(clock.now())


# --- Usuarios y perfil -------------------------------------------------------


def create_user(conn: sqlite3.Connection, email: str, password_hash: str, now) -> int:
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email.strip().lower(), password_hash, _iso(now)),
    )
    user_id = cur.lastrowid
    conn.execute("INSERT INTO profiles (user_id, updated_at) VALUES (?, ?)", (user_id, _iso(now)))
    return user_id


def get_user_by_email(conn: sqlite3.Connection, email: str):
    return conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()


def get_user(conn: sqlite3.Connection, user_id: int):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_profile(conn: sqlite3.Connection, user_id: int) -> dict:
    row = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return {f: None for f in PROFILE_FIELDS}
    return {f: row[f] for f in PROFILE_FIELDS}


def update_profile(conn: sqlite3.Connection, user_id: int, fields: dict, now) -> None:
    cols = [f for f in PROFILE_FIELDS if f in fields]
    if not cols:
        return
    assignments = ", ".join(f"{c} = ?" for c in cols)
    conn.execute(
        f"UPDATE profiles SET {assignments}, updated_at = ? WHERE user_id = ?",
        (*[fields[c] for c in cols], _iso(now), user_id),
    )


def get_chat_id(conn: sqlite3.Connection, user_id: int) -> int | None:
    row = conn.execute("SELECT chat_id FROM telegram_links WHERE user_id = ?", (user_id,)).fetchone()
    return row["chat_id"] if row else None


# --- Códigos de un solo uso y vínculo de Telegram ---------------------------


def create_code(conn: sqlite3.Connection, user_id: int, purpose: str, code_hash: str, expires_at) -> None:
    conn.execute(
        "INSERT INTO one_time_codes (user_id, purpose, code_hash, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, purpose, code_hash, _iso(expires_at)),
    )


def consume_code(conn: sqlite3.Connection, purpose: str, code_hash: str, now) -> int | None:
    row = conn.execute(
        "UPDATE one_time_codes SET used_at = ? "
        "WHERE code_hash = ? AND purpose = ? AND used_at IS NULL AND expires_at > ? RETURNING user_id",
        (_iso(now), code_hash, purpose, _iso(now)),
    ).fetchone()
    return row["user_id"] if row else None


def find_valid_code(conn: sqlite3.Connection, purpose: str, code_hash: str, now) -> int | None:
    row = conn.execute(
        "SELECT user_id FROM one_time_codes "
        "WHERE code_hash = ? AND purpose = ? AND used_at IS NULL AND expires_at > ?",
        (code_hash, purpose, _iso(now)),
    ).fetchone()
    return row["user_id"] if row else None


def get_user_by_chat(conn: sqlite3.Connection, chat_id: int) -> int | None:
    row = conn.execute("SELECT user_id FROM telegram_links WHERE chat_id = ?", (chat_id,)).fetchone()
    return row["user_id"] if row else None


def create_link(conn: sqlite3.Connection, user_id: int, chat_id: int, now) -> None:
    conn.execute(
        "INSERT INTO telegram_links (user_id, chat_id, linked_at) VALUES (?, ?, ?)",
        (user_id, chat_id, _iso(now)),
    )
