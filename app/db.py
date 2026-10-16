"""Conexión sqlite3 y schema (data-model.md)."""

import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    level TEXT NULL CHECK (level IN ('novato', 'intermedio', 'avanzado')),
    frequency INTEGER NULL CHECK (frequency BETWEEN 1 AND 7),
    target_distance_hm INTEGER NULL CHECK (target_distance_hm BETWEEN 100 AND 4220),
    current_pace_s INTEGER NULL CHECK (current_pace_s BETWEEN 180 AND 600),
    city TEXT NULL CHECK (city IS NULL OR length(city) BETWEEN 1 AND 100),
    range_start_min INTEGER NULL CHECK (range_start_min BETWEEN 0 AND 1439),
    range_end_min INTEGER NULL CHECK (range_end_min BETWEEN 0 AND 1439),
    send_time_min INTEGER NULL CHECK (send_time_min BETWEEN 0 AND 1439),
    updated_at TEXT NOT NULL,
    CHECK (range_start_min IS NULL OR range_end_min IS NULL OR range_end_min - range_start_min >= 60),
    CHECK (send_time_min IS NULL OR range_end_min IS NULL OR send_time_min < range_end_min)
);

CREATE TABLE IF NOT EXISTS telegram_links (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL UNIQUE,
    linked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS one_time_codes (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL CHECK (purpose IN ('link', 'reset')),
    code_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,
    start_date TEXT NOT NULL,
    is_full INTEGER NOT NULL CHECK (is_full IN (0, 1)),
    is_deload INTEGER NOT NULL CHECK (is_deload IN (0, 1)),
    is_post_deload INTEGER NOT NULL CHECK (is_post_deload IN (0, 1)),
    source TEXT NOT NULL CHECK (source IN ('on_demand', 'monday', 'fallback')),
    adopted_from_plan_id INTEGER NULL REFERENCES plans(id) ON DELETE SET NULL,
    planned_volume_hm INTEGER NOT NULL CHECK (planned_volume_hm >= 0),
    profile_snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, week_start)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    reclassified INTEGER NOT NULL DEFAULT 0 CHECK (reclassified IN (0, 1)),
    system_status TEXT NULL CHECK (system_status IS NULL OR system_status = 'postponed_weather'),
    postponed_reason TEXT NULL,
    UNIQUE (plan_id, date)
);

CREATE TABLE IF NOT EXISTS blocks (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    kind TEXT NOT NULL CHECK (kind IN ('walk', 'run')),
    distance_hm INTEGER NOT NULL CHECK (distance_hm >= 0),
    target_pace_s INTEGER NULL,
    target_time_s INTEGER NULL,
    recovery_after_s INTEGER NULL CHECK (recovery_after_s IS NULL OR recovery_after_s >= 0),
    UNIQUE (session_id, position)
);

CREATE TABLE IF NOT EXISTS session_results (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('completed', 'partial', 'skipped')),
    rpe INTEGER NULL CHECK (rpe IS NULL OR rpe BETWEEN 1 AND 10),
    notes TEXT NULL CHECK (notes IS NULL OR length(notes) <= 500),
    recorded_at TEXT NOT NULL,
    CHECK ((status = 'skipped' AND rpe IS NULL) OR (status <> 'skipped' AND rpe IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS pending_reclassifications (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    remaining INTEGER NOT NULL CHECK (remaining BETWEEN 1 AND 2)
);

CREATE TABLE IF NOT EXISTS daily_dispatches (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('awaiting_fatigue', 'sent', 'postponed_sent')),
    weather_json TEXT NULL,
    asked_at TEXT NULL,
    fatigue INTEGER NULL CHECK (fatigue IS NULL OR fatigue BETWEEN 1 AND 10),
    sent_at TEXT NULL,
    delivered INTEGER NULL CHECK (delivered IS NULL OR delivered IN (0, 1)),
    used_template INTEGER NULL CHECK (used_template IS NULL OR used_template IN (0, 1)),
    UNIQUE (user_id, date)
);

CREATE TABLE IF NOT EXISTS weekly_generation_runs (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('generated', 'fallback', 'failed_no_previous',
                                             'skipped_existing', 'skipped_incomplete', 'error')),
    ran_at TEXT NOT NULL,
    PRIMARY KEY (user_id, week_start)
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


@contextmanager
def transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE; commit o rollback. Las transacciones anidadas se aplanan en la externa."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
