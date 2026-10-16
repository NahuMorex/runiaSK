"""Resúmenes semanales, racha de descarga, elegibilidad de calidad y contexto de guardarraíles (R-11)."""

import json
from datetime import date

from app.domain import weeks
from app.domain.models import GuardrailContext, WeekSummary

STREAK_FOR_DELOAD = 4
NOVICE_QUALITY_WEEKS = 3


def _get(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _snapshot(value) -> dict | None:
    if value is None:
        return None
    return value if isinstance(value, dict) else json.loads(value)


def profile_snapshot(profile: dict) -> dict:
    return {
        "level": profile.get("level"),
        "frequency": profile.get("frequency"),
        "target_distance_hm": profile.get("target_distance_hm"),
        "current_pace_s": profile.get("current_pace_s"),
    }


def summarize_weeks(plans_rows, sessions_rows, results_rows) -> dict[date, WeekSummary]:
    session_plan = {_get(s, "id"): _get(s, "plan_id") for s in sessions_rows}
    completed: dict[int, int] = {}
    partial7: set[int] = set()
    for r in results_rows:
        plan_id = session_plan.get(_get(r, "session_id"))
        if plan_id is None:
            continue
        if _get(r, "status") == "completed":
            completed[plan_id] = completed.get(plan_id, 0) + 1
        elif _get(r, "status") == "partial" and (_get(r, "rpe") or 0) >= 7:
            partial7.add(plan_id)

    out: dict[date, WeekSummary] = {}
    for p in plans_rows:
        pid = _get(p, "id")
        ws = _as_date(_get(p, "week_start"))
        out[ws] = WeekSummary(
            week_start=ws,
            has_plan=True,
            is_full=bool(_get(p, "is_full")),
            is_deload=bool(_get(p, "is_deload")),
            planned_volume_hm=int(_get(p, "planned_volume_hm") or 0),
            completed_count=completed.get(pid, 0),
            has_partial_rpe7=pid in partial7,
            profile_snapshot=_snapshot(_get(p, "profile_snapshot")),
            is_post_deload=bool(_get(p, "is_post_deload", 0)),
        )
    return out


def deload_streak(summaries: dict[date, WeekSummary], current_week_start: date) -> int:
    """Semanas cerradas consecutivas con plan y al menos 1 Completada; corta en una descarga (AC-19c)."""
    streak = 0
    ws = weeks.previous_week_start(current_week_start)
    while True:
        s = summaries.get(ws)
        if s is None or not s.has_plan or s.completed_count < 1 or s.is_deload:
            return streak
        streak += 1
        ws = weeks.previous_week_start(ws)


def novice_quality_allowed(level, current_pace_s, summaries: dict[date, WeekSummary], current_week_start: date) -> bool:
    if level != "novato":
        return True
    if current_pace_s is None:
        return False
    ws = current_week_start
    for _ in range(NOVICE_QUALITY_WEEKS):
        ws = weeks.previous_week_start(ws)
        s = summaries.get(ws)
        if s is None or not s.has_plan or s.completed_count < 1 or s.has_partial_rpe7:
            return False
    return True


def _last_full_before(summaries: dict[date, WeekSummary], before: date) -> WeekSummary | None:
    candidates = [s for ws, s in summaries.items() if ws < before and s.has_plan and s.is_full]
    return max(candidates, key=lambda s: s.week_start) if candidates else None


def build_context(
    profile: dict,
    summaries: dict[date, WeekSummary],
    current_week_start: date,
    start_date: date,
    pending_reclass: int,
) -> GuardrailContext:
    prev_ws = weeks.previous_week_start(current_week_start)
    prev = summaries.get(prev_ws)

    if prev is None:
        initial_caps = True
        base_10 = None
    elif prev.is_full:
        initial_caps = False
        base_10 = prev.planned_volume_hm
    else:
        last_full = _last_full_before(summaries, prev_ws)
        initial_caps = last_full is None
        base_10 = None if last_full is None else last_full.planned_volume_hm

    no_increase = prev.planned_volume_hm if prev is not None and prev.completed_count == 0 else None

    is_deload = deload_streak(summaries, current_week_start) >= STREAK_FOR_DELOAD
    deload_v4 = prev.planned_volume_hm if is_deload else None

    is_post_deload = prev is not None and prev.is_deload
    post_deload_target = None
    if is_post_deload and prev.completed_count >= 1:
        v4 = summaries.get(weeks.previous_week_start(prev_ws))
        post_deload_target = v4.planned_volume_hm if v4 is not None else None

    floor_prev = None
    if (
        prev is not None
        and prev.is_full
        and prev.completed_count >= 1
        and not prev.is_deload
        and not is_deload
        and prev.profile_snapshot == profile_snapshot(profile)
    ):
        floor_prev = prev.planned_volume_hm

    return GuardrailContext(
        level=profile["level"],
        frequency=profile["frequency"],
        target_distance_hm=profile["target_distance_hm"],
        current_pace_s=profile.get("current_pace_s"),
        start_date=start_date,
        week_start=current_week_start,
        is_full=start_date == current_week_start,
        is_deload=is_deload,
        is_post_deload=is_post_deload,
        initial_caps=initial_caps,
        base_10_hm=base_10,
        no_increase_hm=no_increase,
        deload_v4_hm=deload_v4,
        post_deload_target_hm=post_deload_target,
        floor_prev_hm=floor_prev,
        novice_quality_allowed=novice_quality_allowed(
            profile["level"], profile.get("current_pace_s"), summaries, current_week_start
        ),
        pending_reclass=pending_reclass,
    )


def first_week_novice(level, summaries: dict[date, WeekSummary]) -> bool:
    """FR-015: todo plan de un novato hasta su primer plan de semana completa como novato, inclusive."""
    if level != "novato":
        return False
    return not any(
        s.has_plan and s.is_full and (s.profile_snapshot or {}).get("level") == "novato" for s in summaries.values()
    )


def recent_summaries_for_ai(summaries: dict[date, WeekSummary], n: int = 4) -> list[WeekSummary]:
    return [summaries[ws] for ws in sorted(summaries, reverse=True)[:n]]
