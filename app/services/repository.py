"""Todo el SQL de Runia vive en este archivo."""

import json
import sqlite3
from datetime import date, datetime

from app.clock import Clock
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


def now_iso(clock: Clock) -> str:
    return clock.now().isoformat()


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


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
