from datetime import date, timedelta

from app.domain.summaries import (
    build_context,
    deload_streak,
    novice_quality_allowed,
    profile_snapshot,
    summarize_weeks,
)

CUR = date(2026, 10, 19)  # lunes de la semana actual
PROFILE = {
    "level": "intermedio",
    "frequency": 4,
    "target_distance_hm": 1000,
    "current_pace_s": 360,
}


def wk(n):
    """Lunes de n semanas antes de CUR."""
    return CUR - timedelta(days=7 * n)


class History:
    """Arma filas en memoria como las de history_rows_for_summaries."""

    def __init__(self):
        self.plans, self.sessions, self.results = [], [], []
        self._sid = 0

    def week(self, n, volume=1000, *, full=True, deload=False, post=False, completed=1, partial7=False, snapshot=None):
        pid = len(self.plans) + 1
        self.plans.append(
            {
                "id": pid,
                "week_start": wk(n).isoformat(),
                "is_full": int(full),
                "is_deload": int(deload),
                "is_post_deload": int(post),
                "planned_volume_hm": volume,
                "profile_snapshot": snapshot or profile_snapshot(PROFILE),
            }
        )
        statuses = ["completed"] * completed + (["partial"] if partial7 else []) + ["skipped"]
        for st in statuses:
            self._sid += 1
            self.sessions.append({"id": self._sid, "plan_id": pid})
            self.results.append({"session_id": self._sid, "status": st, "rpe": 7 if st == "partial" else (5 if st == "completed" else None)})
        return self

    def summaries(self):
        return summarize_weeks(self.plans, self.sessions, self.results)

    def ctx(self, start=CUR, profile=PROFILE, pending=0):
        return build_context(profile, self.summaries(), CUR, start, pending)


def test_summarize_counts():
    s = History().week(1, completed=2, partial7=True).summaries()[wk(1)]
    assert s.completed_count == 2 and s.has_partial_rpe7 and s.is_full and s.planned_volume_hm == 1000


def test_streak_of_four_gives_deload():
    h = History()
    for n in range(1, 5):
        h.week(n, volume=1000 + n)
    assert deload_streak(h.summaries(), CUR) == 4
    ctx = h.ctx()
    assert ctx.is_deload and ctx.deload_v4_hm == 1001


def test_week_without_plan_cuts_streak():
    h = History().week(1).week(2).week(4).week(5)
    assert deload_streak(h.summaries(), CUR) == 2


def test_week_without_completed_resets_streak():
    h = History().week(1).week(2, completed=0).week(3).week(4)
    assert deload_streak(h.summaries(), CUR) == 1
    assert not h.ctx().is_deload


def test_streak_restarts_after_deload():
    h = History().week(1).week(2).week(3, deload=True).week(4).week(5).week(6).week(7)
    assert deload_streak(h.summaries(), CUR) == 2


def test_partial_first_week_counts_for_streak():
    h = History().week(1).week(2).week(3).week(4, full=False)
    assert deload_streak(h.summaries(), CUR) == 4


def test_novice_quality_eligibility():
    good = History().week(1).week(2).week(3).summaries()
    assert novice_quality_allowed("novato", 400, good, CUR)
    assert not novice_quality_allowed("novato", None, good, CUR)
    assert not novice_quality_allowed("novato", 400, History().week(1).week(2).summaries(), CUR)
    assert not novice_quality_allowed("novato", 400, History().week(1).week(2, completed=0).week(3).summaries(), CUR)
    assert not novice_quality_allowed("novato", 400, History().week(1).week(2, partial7=True).week(3).summaries(), CUR)
    assert not novice_quality_allowed("novato", 400, History().week(1).week(2).week(4).summaries(), CUR)
    assert novice_quality_allowed("intermedio", None, {}, CUR)


def test_no_previous_week_initial_caps():
    ctx = History().ctx()
    assert ctx.initial_caps and ctx.base_10_hm is None and ctx.no_increase_hm is None


def test_previous_partial_without_full_initial_caps():
    ctx = History().week(1, full=False).ctx()
    assert ctx.initial_caps and ctx.base_10_hm is None


def test_previous_partial_with_full_before_uses_last_full():
    ctx = History().week(1, volume=600, full=False).week(3, volume=1500).ctx()
    assert not ctx.initial_caps and ctx.base_10_hm == 1500


def test_previous_without_completed_no_increase():
    ctx = History().week(1, volume=900, completed=0).ctx()
    assert ctx.no_increase_hm == 900 and ctx.base_10_hm == 900


def test_floor_prev_only_with_same_snapshot_full_completed_not_deload():
    assert History().week(1, volume=1200).ctx().floor_prev_hm == 1200
    other = {**profile_snapshot(PROFILE), "frequency": 5}
    assert History().week(1, snapshot=other).ctx().floor_prev_hm is None
    assert History().week(1, full=False).week(2).ctx().floor_prev_hm is None
    assert History().week(1, completed=0).ctx().floor_prev_hm is None
    assert History().week(1, deload=True).week(2).ctx().floor_prev_hm is None


def test_no_floor_prev_in_deload_week():
    h = History()
    for n in range(1, 5):
        h.week(n)
    assert h.ctx().floor_prev_hm is None


def test_post_deload_target():
    ctx = History().week(1, volume=750, deload=True).week(2, volume=1000).ctx()
    assert ctx.is_post_deload and ctx.post_deload_target_hm == 1000 and ctx.no_increase_hm is None


def test_post_deload_without_completed():
    ctx = History().week(1, volume=750, deload=True, completed=0).week(2, volume=1000).ctx()
    assert ctx.is_post_deload and ctx.post_deload_target_hm is None and ctx.no_increase_hm == 750


def test_postponed_session_does_not_discount_base():
    # AC-42: la base es el planned_volume_hm guardado; una sesión pospuesta no lo modifica.
    h = History().week(1, volume=1000)
    h.sessions.append({"id": 99, "plan_id": 1})  # sesión pospuesta: sin resultado
    ctx = h.ctx()
    assert ctx.base_10_hm == 1000


def test_is_full_and_pending():
    ctx = History().ctx(start=CUR + timedelta(days=3), pending=2)
    assert not ctx.is_full and ctx.pending_reclass == 2
