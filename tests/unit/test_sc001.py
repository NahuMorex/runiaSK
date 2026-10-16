from datetime import date, timedelta

import pytest

from app.domain import guardrails
from app.domain.models import Block, GuardrailContext, PlannedSession
from tests.sc001_check import check_sc001

MON = date(2026, 10, 19)
THU = MON + timedelta(days=3)


def ctx(**kw):
    base = dict(level="intermedio", frequency=4, target_distance_hm=2100, current_pace_s=360,
                start_date=MON, week_start=MON, is_full=True, initial_caps=False)
    base.update(kw)
    base["is_full"] = base["start_date"] == base["week_start"]
    return GuardrailContext(**base)


CONTEXTS = {
    "initial_novato": ctx(level="novato", current_pace_s=None, initial_caps=True),
    "initial_intermedio": ctx(initial_caps=True),
    "initial_avanzado": ctx(level="avanzado", initial_caps=True, current_pace_s=300),
    "ten_percent": ctx(base_10_hm=1500),
    "empty_week": ctx(base_10_hm=800, no_increase_hm=800),
    "deload": ctx(base_10_hm=2000, is_deload=True, deload_v4_hm=2000),
    "post_deload": ctx(base_10_hm=1400, is_post_deload=True, post_deload_target_hm=1800),
    "post_deload_no_completed": ctx(base_10_hm=1400, is_post_deload=True, no_increase_hm=1400),
    "ac66": ctx(base_10_hm=1500, floor_prev_hm=1500),
    "partial": ctx(start_date=THU, base_10_hm=1500, floor_prev_hm=1500),
    "full": ctx(base_10_hm=1200),
    "pending_1": ctx(base_10_hm=1500, pending_reclass=1),
    "pending_2": ctx(base_10_hm=1500, pending_reclass=2),
    "floor_blocked": ctx(target_distance_hm=400, base_10_hm=2500, floor_prev_hm=2500),
    "novice_quality_ok": ctx(level="novato", current_pace_s=420, novice_quality_allowed=True, base_10_hm=900),
}


def run(hm, pace=None, rec=None):
    return Block("run", hm, target_pace_s=pace, recovery_after_s=rec)


def proposals(c):
    days = [c.start_date + timedelta(days=i) for i in range(7 - c.start_date.weekday())][:4]
    p = c.current_pace_s or 360
    yield "long_sessions", [PlannedSession(d, "Largo", [run(3000)]) for d in days]
    yield "too_much_volume", [PlannedSession(d, "Rodaje", [run(900), Block("walk", 100), run(700)]) for d in days]
    yield "many_quality", [
        PlannedSession(d, "Intervalos", [run(200), run(150, p - 60, 120), run(150, p + 40, 90), run(150, p - 1)]) for d in days
    ]
    yield "novice_with_pace", [
        PlannedSession(d, "Caminata", [Block("walk", 50), run(120, 300), Block("walk", 50), run(120)]) for d in days
    ]
    yield "tiny", [PlannedSession(d, "Corto", [run(37), run(41)]) for d in days]
    yield "mixed", [PlannedSession(days[0], "Q", [run(500, p - 100, 60), run(500, p - 100)])] + [
        PlannedSession(d, "R", [run(1800)]) for d in days[1:]
    ]


CASES = [(cname, pname, c, p) for cname, c in CONTEXTS.items() for pname, p in proposals(c)]


@pytest.mark.parametrize("cname,pname,c,p", CASES, ids=[f"{a}-{b}" for a, b, _, _ in CASES])
def test_pipeline_output_satisfies_sc001(cname, pname, c, p):
    out, _ = guardrails.apply(p, c)
    assert check_sc001(out, c) == []
    assert len(out) == len(p)


def _ok_plan():
    return [PlannedSession(MON, "R", [run(300)]), PlannedSession(MON + timedelta(days=2), "R", [run(300)])]


@pytest.mark.parametrize(
    "plan,c,needle",
    [
        ([PlannedSession(MON, "R", [run(600)])], ctx(initial_caps=True), "tope por sesión"),
        ([PlannedSession(MON, "R", [run(2200)])], ctx(), "tope por sesión"),
        (_ok_plan(), ctx(base_10_hm=500), "tope semanal"),
        (_ok_plan(), ctx(no_increase_hm=500), "tope semanal"),
        (_ok_plan(), ctx(is_deload=True, deload_v4_hm=600), "tope semanal"),
        (_ok_plan(), ctx(is_post_deload=True, post_deload_target_hm=500), "tope semanal"),
        ([PlannedSession(MON, "Q", [run(100, 350)])], ctx(level="novato"), "novato no elegible"),
        ([PlannedSession(MON, "Q", [run(100, 350, None)]), PlannedSession(MON + timedelta(days=1), "Q", [run(100, 350)])],
         ctx(), "sesiones de calidad"),
        ([PlannedSession(MON, "Q", [Block("run", 100, 300, 300)])], ctx(), "fuera de rango"),
        ([PlannedSession(MON, "Q", [Block("run", 100, 350, 999)])], ctx(), "tiempo"),
        (_ok_plan(), ctx(pending_reclass=1), "reclasificación"),
        (_ok_plan(), ctx(floor_prev_hm=1500), "piso"),
    ],
)
def test_checker_detects_violations(plan, c, needle):
    assert any(needle in v for v in check_sc001(plan, c))


def test_checker_accepts_floor_blocked_by_cap():
    plan = [PlannedSession(MON + timedelta(days=i), "R", [run(400)]) for i in range(3)]
    assert check_sc001(plan, ctx(target_distance_hm=400, floor_prev_hm=2500)) == []
