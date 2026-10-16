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


# --- Planes, sesiones y bloques ---------------------------------------------


def _blocks_for_sessions(conn: sqlite3.Connection, session_ids: list[int]) -> dict[int, list[Block]]:
    out: dict[int, list[Block]] = {sid: [] for sid in session_ids}
    if not session_ids:
        return out
    marks = ",".join("?" * len(session_ids))
    for b in conn.execute(
        f"SELECT * FROM blocks WHERE session_id IN ({marks}) ORDER BY session_id, position", session_ids
    ):
        out[b["session_id"]].append(
            Block(b["kind"], b["distance_hm"], b["target_pace_s"], b["target_time_s"], b["recovery_after_s"])
        )
    return out


def get_session_blocks(conn: sqlite3.Connection, session_id: int) -> list[Block]:
    return _blocks_for_sessions(conn, [session_id])[session_id]


def get_plan(conn: sqlite3.Connection, plan_id: int):
    return conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()


def get_plan_sessions(conn: sqlite3.Connection, plan_id: int) -> list[dict]:
    """Sesiones del plan ordenadas por fecha, cada una con `blocks` y `result` (o None)."""
    rows = conn.execute(
        "SELECT s.*, r.status AS result_status, r.rpe AS result_rpe, r.notes AS result_notes "
        "FROM sessions s LEFT JOIN session_results r ON r.session_id = s.id "
        "WHERE s.plan_id = ? ORDER BY s.date",
        (plan_id,),
    ).fetchall()
    blocks = _blocks_for_sessions(conn, [r["id"] for r in rows])
    return [_session_dict(r, blocks[r["id"]]) for r in rows]


def _session_dict(row, blocks: list[Block]) -> dict:
    result = None
    if row["result_status"] is not None:
        result = {"status": row["result_status"], "rpe": row["result_rpe"], "notes": row["result_notes"]}
    return {
        "id": row["id"],
        "plan_id": row["plan_id"],
        "user_id": row["user_id"],
        "date": date.fromisoformat(row["date"]),
        "title": row["title"],
        "reclassified": bool(row["reclassified"]),
        "system_status": row["system_status"],
        "postponed_reason": row["postponed_reason"],
        "blocks": blocks,
        "result": result,
    }


def get_plan_for_week(conn: sqlite3.Connection, user_id: int, week_start: date):
    return conn.execute(
        "SELECT * FROM plans WHERE user_id = ? AND week_start = ?", (user_id, _iso(week_start))
    ).fetchone()


def get_last_plan(conn: sqlite3.Connection, user_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM plans WHERE user_id = ? ORDER BY week_start DESC LIMIT 1", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return {**dict(row), "sessions": get_plan_sessions(conn, row["id"])}


def save_plan(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    week_start: date,
    start_date: date,
    is_full: bool,
    is_deload: bool,
    is_post_deload: bool,
    source: str,
    adopted_from_plan_id: int | None,
    planned_volume_hm: int,
    profile_snapshot: dict,
    sessions: list[PlannedSession],
    now,
) -> int:
    plan_id = conn.execute(
        "INSERT INTO plans (user_id, week_start, start_date, is_full, is_deload, is_post_deload, source, "
        "adopted_from_plan_id, planned_volume_hm, profile_snapshot, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            _iso(week_start),
            _iso(start_date),
            int(is_full),
            int(is_deload),
            int(is_post_deload),
            source,
            adopted_from_plan_id,
            planned_volume_hm,
            json.dumps(profile_snapshot, sort_keys=True),
            _iso(now),
        ),
    ).lastrowid
    for s in sessions:
        session_id = conn.execute(
            "INSERT INTO sessions (plan_id, user_id, date, title, reclassified) VALUES (?, ?, ?, ?, ?)",
            (plan_id, user_id, _iso(s.date), s.title, int(s.reclassified)),
        ).lastrowid
        _insert_blocks(conn, session_id, s.blocks)
    return plan_id


def _insert_blocks(conn: sqlite3.Connection, session_id: int, blocks: list[Block]) -> None:
    conn.executemany(
        "INSERT INTO blocks (session_id, position, kind, distance_hm, target_pace_s, target_time_s, recovery_after_s) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (session_id, i, b.kind, b.distance_hm, b.target_pace_s, b.target_time_s, b.recovery_after_s)
            for i, b in enumerate(blocks)
        ],
    )


def history_rows_for_summaries(conn: sqlite3.Connection, user_id: int, before_week_start: date):
    """Planes, sesiones y resultados de semanas anteriores (para summaries.summarize_weeks)."""
    ws = _iso(before_week_start)
    plans = conn.execute(
        "SELECT * FROM plans WHERE user_id = ? AND week_start < ? ORDER BY week_start", (user_id, ws)
    ).fetchall()
    sessions = conn.execute(
        "SELECT s.id, s.plan_id FROM sessions s JOIN plans p ON p.id = s.plan_id "
        "WHERE p.user_id = ? AND p.week_start < ?",
        (user_id, ws),
    ).fetchall()
    results = conn.execute(
        "SELECT r.session_id, r.status, r.rpe FROM session_results r "
        "JOIN sessions s ON s.id = r.session_id JOIN plans p ON p.id = s.plan_id "
        "WHERE p.user_id = ? AND p.week_start < ?",
        (user_id, ws),
    ).fetchall()
    return plans, sessions, results


def get_pending_reclass(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute("SELECT remaining FROM pending_reclassifications WHERE user_id = ?", (user_id,)).fetchone()
    return row["remaining"] if row else 0


def consume_pending_reclass(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("DELETE FROM pending_reclassifications WHERE user_id = ?", (user_id,))


def eligible_users_for_monday(conn: sqlite3.Connection) -> list[int]:
    return [r["user_id"] for r in conn.execute("SELECT user_id FROM telegram_links ORDER BY user_id")]


def has_weekly_run(conn: sqlite3.Connection, user_id: int, week_start: date) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM weekly_generation_runs WHERE user_id = ? AND week_start = ?", (user_id, _iso(week_start))
        ).fetchone()
        is not None
    )


def record_weekly_run(conn: sqlite3.Connection, user_id: int, week_start: date, outcome: str, now) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO weekly_generation_runs (user_id, week_start, outcome, ran_at) VALUES (?, ?, ?, ?)",
        (user_id, _iso(week_start), outcome, _iso(now)),
    )
    return cur.rowcount == 1
