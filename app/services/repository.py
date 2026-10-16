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


def update_password_hash(conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Borra el usuario; el resto de sus filas cae por ON DELETE CASCADE (RF-19)."""
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("PRAGMA foreign_keys está desactivado: el borrado no sería en cascada")
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


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


# --- Envío diario -------------------------------------------------------------


def get_session_for_user_on(conn: sqlite3.Connection, user_id: int, day: date) -> dict | None:
    row = conn.execute(
        "SELECT s.*, r.status AS result_status, r.rpe AS result_rpe, r.notes AS result_notes "
        "FROM sessions s LEFT JOIN session_results r ON r.session_id = s.id "
        "WHERE s.user_id = ? AND s.date = ?",
        (user_id, _iso(day)),
    ).fetchone()
    if row is None:
        return None
    return _session_dict(row, get_session_blocks(conn, row["id"]))


def users_due_for_dispatch(conn: sqlite3.Connection, today: date, now_min: int) -> list:
    """Usuarios vinculados cuya hora de envío ya llegó, con sesión hoy sin resultado, sin pospuesta y sin
    dispatch (FR-029, FR-038)."""
    return conn.execute(
        "SELECT l.user_id, l.chat_id, s.id AS session_id FROM telegram_links l "
        "JOIN profiles p ON p.user_id = l.user_id "
        "JOIN sessions s ON s.user_id = l.user_id AND s.date = ? "
        "LEFT JOIN session_results r ON r.session_id = s.id "
        "LEFT JOIN daily_dispatches d ON d.user_id = l.user_id AND d.date = ? "
        "WHERE p.send_time_min IS NOT NULL AND p.send_time_min <= ? AND r.session_id IS NULL AND d.id IS NULL "
        "AND s.system_status IS NULL "
        "ORDER BY l.user_id",
        (_iso(today), _iso(today), now_min),
    ).fetchall()


def create_dispatch(
    conn: sqlite3.Connection,
    user_id: int,
    session_id: int,
    day: date,
    now,
    *,
    state: str = "awaiting_fatigue",
    delivered: bool | None = None,
) -> int | None:
    """Crea el dispatch del día; devuelve None si ya había uno.

    `awaiting_fatigue` guarda `now` como hora de la pregunta; `postponed_sent` (FR-038), como hora de envío.
    """
    asked_at, sent_at = (_iso(now), None) if state == "awaiting_fatigue" else (None, _iso(now))
    row = conn.execute(
        "INSERT INTO daily_dispatches (user_id, session_id, date, state, asked_at, sent_at, delivered) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (user_id, date) DO NOTHING RETURNING id",
        (user_id, session_id, _iso(day), state, asked_at, sent_at, None if delivered is None else int(delivered)),
    ).fetchone()
    return row["id"] if row else None


def set_dispatch_weather(conn: sqlite3.Connection, dispatch_id: int, weather_json: dict) -> None:
    conn.execute(
        "UPDATE daily_dispatches SET weather_json = ? WHERE id = ?",
        (json.dumps(weather_json, ensure_ascii=False, sort_keys=True), dispatch_id),
    )


def set_session_postponed(conn: sqlite3.Connection, session_id: int, reason: str) -> None:
    """NULL → postponed_weather es terminal (FR-037)."""
    conn.execute(
        "UPDATE sessions SET system_status = 'postponed_weather', postponed_reason = ? "
        "WHERE id = ? AND system_status IS NULL",
        (reason, session_id),
    )


def count_postponed_in_week(conn: sqlite3.Connection, user_id: int, week_start: date) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM sessions s JOIN plans p ON p.id = s.plan_id "
        "WHERE s.user_id = ? AND p.week_start = ? AND s.system_status = 'postponed_weather'",
        (user_id, _iso(week_start)),
    ).fetchone()["n"]


def get_open_dispatch_by_chat(conn: sqlite3.Connection, chat_id: int, today: date):
    return conn.execute(
        "SELECT d.* FROM daily_dispatches d JOIN telegram_links l ON l.user_id = d.user_id "
        "WHERE l.chat_id = ? AND d.date = ? AND d.state = 'awaiting_fatigue'",
        (chat_id, _iso(today)),
    ).fetchone()


def claim_dispatch(conn: sqlite3.Connection, dispatch_id: int, fatigue: int | None) -> bool:
    """Pasa el dispatch a `sent` antes de redactar el mensaje, para que una respuesta concurrente
    o el cierre de la espera no lo envíen dos veces. Devuelve False si otro ya lo tomó."""
    cur = conn.execute(
        "UPDATE daily_dispatches SET state = 'sent', fatigue = ? WHERE id = ? AND state = 'awaiting_fatigue'",
        (fatigue, dispatch_id),
    )
    return cur.rowcount == 1


def set_dispatch_sent(
    conn: sqlite3.Connection, dispatch_id: int, fatigue: int | None, used_template: bool, delivered: bool, now
) -> None:
    conn.execute(
        "UPDATE daily_dispatches SET state = 'sent', fatigue = ?, used_template = ?, delivered = ?, sent_at = ? "
        "WHERE id = ?",
        (fatigue, int(used_template), int(delivered), _iso(now), dispatch_id),
    )


def expired_dispatches(conn: sqlite3.Connection, cutoff_iso: str) -> list:
    return conn.execute(
        "SELECT * FROM daily_dispatches WHERE state = 'awaiting_fatigue' AND asked_at <= ? ORDER BY id",
        (cutoff_iso,),
    ).fetchall()


# --- Resultados y reclasificación -------------------------------------------


def get_session(conn: sqlite3.Connection, session_id: int) -> dict | None:
    row = conn.execute(
        "SELECT s.*, r.status AS result_status, r.rpe AS result_rpe, r.notes AS result_notes "
        "FROM sessions s LEFT JOIN session_results r ON r.session_id = s.id WHERE s.id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return _session_dict(row, get_session_blocks(conn, row["id"]))


def get_result(conn: sqlite3.Connection, session_id: int):
    return conn.execute("SELECT * FROM session_results WHERE session_id = ?", (session_id,)).fetchone()


def insert_result(
    conn: sqlite3.Connection, session_id: int, user_id: int, status: str, rpe: int | None, notes: str | None, now
) -> None:
    conn.execute(
        "INSERT INTO session_results (session_id, user_id, status, rpe, notes, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, status, rpe, notes, _iso(now)),
    )


def upcoming_sessions(conn: sqlite3.Connection, user_id: int, after_date: date) -> list[tuple[int, date]]:
    """Sesiones ya guardadas posteriores a `after_date`, sin las pospuestas por clima, por fecha."""
    return [
        (r["id"], date.fromisoformat(r["date"]))
        for r in conn.execute(
            "SELECT id, date FROM sessions WHERE user_id = ? AND date > ? AND system_status IS NULL ORDER BY date",
            (user_id, _iso(after_date)),
        )
    ]


def replace_session_blocks(
    conn: sqlite3.Connection, session_id: int, blocks: list[Block], title: str, reclassified: bool = True
) -> None:
    conn.execute(
        "UPDATE sessions SET title = ?, reclassified = ? WHERE id = ?", (title, int(reclassified), session_id)
    )
    conn.execute("DELETE FROM blocks WHERE session_id = ?", (session_id,))
    _insert_blocks(conn, session_id, blocks)


def upsert_pending_reclass(conn: sqlite3.Connection, user_id: int, remaining: int) -> None:
    """Se queda con el mayor entre el pendiente guardado y el nuevo."""
    conn.execute(
        "INSERT INTO pending_reclassifications (user_id, remaining) VALUES (?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET remaining = MAX(remaining, excluded.remaining)",
        (user_id, remaining),
    )


# --- Cronograma e historial (R-19) -------------------------------------------


def history_sessions(conn: sqlite3.Connection, user_id: int, today: date) -> list[dict]:
    """Sesiones con fecha anterior a hoy, más las que ya tienen resultado, por fecha descendente."""
    rows = conn.execute(
        "SELECT s.*, r.status AS result_status, r.rpe AS result_rpe, r.notes AS result_notes "
        "FROM sessions s LEFT JOIN session_results r ON r.session_id = s.id "
        "WHERE s.user_id = ? AND (s.date < ? OR r.session_id IS NOT NULL) ORDER BY s.date DESC",
        (user_id, _iso(today)),
    ).fetchall()
    blocks = _blocks_for_sessions(conn, [r["id"] for r in rows])
    return [_session_dict(r, blocks[r["id"]]) for r in rows]
