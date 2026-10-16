from datetime import date, timedelta

from app.domain import guardrails
from app.domain.models import Block, GuardrailContext, PlannedSession, run_volume_hm

MON = date(2026, 10, 19)


def ctx(**kw):
    base = dict(
        level="intermedio",
        frequency=4,
        target_distance_hm=2000,
        current_pace_s=360,
        start_date=MON,
        week_start=MON,
        is_full=True,
        initial_caps=False,
    )
    base.update(kw)
    return GuardrailContext(**base)


def easy(i, hm, title="Rodaje"):
    return PlannedSession(MON + timedelta(days=i), title, [Block("run", hm)])


def quality(i, hm_rep=100, pace=345, warmup=100, title="Intervalos"):
    return PlannedSession(
        MON + timedelta(days=i),
        title,
        [Block("run", warmup), Block("run", hm_rep, target_pace_s=pace, recovery_after_s=120), Block("run", hm_rep, target_pace_s=pace)],
    )


def walkrun(i, run_hm=100, walk_hm=50):
    return PlannedSession(MON + timedelta(days=i), "Caminata y trote", [Block("walk", walk_hm), Block("run", run_hm), Block("walk", walk_hm), Block("run", run_hm)])


def rules(events):
    return [e.rule for e in events]


def find(events, rule):
    return [e for e in events if e.rule == rule]


def test_initial_caps_per_level():
    for level, cap in (("novato", 200), ("intermedio", 500), ("avanzado", 1000)):
        c = ctx(level=level, initial_caps=True, frequency=3, novice_quality_allowed=True)
        out, ev = guardrails.apply([easy(0, 3000), easy(2, 3000), easy(4, 3000)], c)
        assert all(run_volume_hm(s.blocks) == cap for s in out)
        assert guardrails.planned_volume_hm(out) <= cap * 3
        e = find(ev, "session_cap")[0]
        assert e.reason == "initial_cap" and e.before == 3000 and e.after == cap


def test_initial_weekly_cap():
    # 4 sesiones de 5 km con frecuencia 3 (adoptado): tope semanal 15 km
    c = ctx(initial_caps=True, frequency=3)
    out, ev = guardrails.apply([easy(i, 500) for i in range(4)], c)
    assert guardrails.planned_volume_hm(out) <= 1500
    assert find(ev, "weekly_cap")[0].reason == "initial_weekly"


def test_ten_percent_cap_without_floor_above():
    c = ctx(base_10_hm=1000, floor_prev_hm=1000)
    out, ev = guardrails.apply([easy(0, 800), easy(2, 800)], c)
    assert guardrails.planned_volume_hm(out) <= 1100
    e = find(ev, "weekly_cap")[0]
    assert e.reason == "ten_percent" and e.before == 1600 and e.after == guardrails.planned_volume_hm(out)


def test_ac76_session_then_weekly_scaling():
    c = ctx(target_distance_hm=500, base_10_hm=1000)
    s8 = PlannedSession(
        MON,
        "Intervalos",
        [Block("walk", 50), Block("run", 400), Block("run", 400, target_pace_s=350, recovery_after_s=90)],
    )
    out, ev = guardrails.apply([s8, easy(2, 500), easy(4, 500)], c)
    first = out[0]
    # 5/8 por sesión: 400 → 250, 400 → 250; total sesión 500
    # semanal: 500+500+500 = 1500 > 1100 → factor 1100/1500
    assert find(ev, "session_cap")[0].before == 800 and find(ev, "session_cap")[0].after == 500
    assert first.blocks[0] == Block("walk", 50)
    assert first.blocks[1].distance_hm == 250 * 1100 // 1500
    assert first.blocks[2].target_pace_s == 350 and first.blocks[2].recovery_after_s == 90
    assert first.blocks[2].target_time_s == (first.blocks[2].distance_hm * 350 * 2 + 100) // 200
    assert find(ev, "weekly_cap")[0].before == 1500
    assert guardrails.planned_volume_hm(out) <= 1100


def test_quality_not_allowed_for_novice_converted():
    c = ctx(level="novato", current_pace_s=None, novice_quality_allowed=False)
    out, ev = guardrails.apply([quality(0)], c)
    assert out[0].blocks == [Block("run", 300)]
    assert out[0].title == "Trote suave"
    assert rules(ev) == ["novice_quality"]


def test_second_quality_converted():
    out, ev = guardrails.apply([quality(0), easy(1, 300), quality(3)], ctx())
    assert out[0].blocks[1].target_pace_s == 345
    assert out[2].blocks == [Block("run", 300)] and out[2].title == "Trote suave"
    assert find(ev, "max_one_quality")[0].session_date == MON + timedelta(days=3)


def test_pace_clamped():
    out, ev = guardrails.apply([quality(0, pace=300)], ctx())
    rep = out[0].blocks[1]
    assert rep.target_pace_s == 340 and rep.distance_hm == 100 and rep.target_time_s == 340
    out, _ = guardrails.apply([quality(0, pace=400)], ctx())
    assert out[0].blocks[1].target_pace_s == 360 and out[0].blocks[1].target_time_s == 360
    assert find(ev, "pace_clamp")[0].before == 300 and find(ev, "pace_clamp")[0].after == 340


def test_target_distance_cap():
    c = ctx(target_distance_hm=300)
    out, ev = guardrails.apply([easy(0, 800)], c)
    assert run_volume_hm(out[0].blocks) == 300
    assert find(ev, "session_cap")[0].reason == "target_distance"
    # el menor entre tope inicial (500) y distancia (300)
    out, ev = guardrails.apply([easy(0, 800)], ctx(target_distance_hm=300, initial_caps=True))
    assert run_volume_hm(out[0].blocks) == 300 and find(ev, "session_cap")[0].reason == "target_distance"


def test_deload_band():
    c = ctx(is_deload=True, deload_v4_hm=2000, base_10_hm=2000)
    out, ev = guardrails.apply([easy(0, 1000), easy(2, 1000)], c)
    vol = guardrails.planned_volume_hm(out)
    assert 1400 - 2 <= vol <= 1600
    assert find(ev, "weekly_cap")[0].reason == "deload"
    # propuesta demasiado baja: se escala al piso del 70%
    out, ev = guardrails.apply([easy(0, 300), easy(2, 300)], c)
    vol = guardrails.planned_volume_hm(out)
    assert 1400 - 2 <= vol <= 1600
    assert find(ev, "floor_scale")


def test_post_deload_matches_v4():
    c = ctx(is_post_deload=True, post_deload_target_hm=1500, base_10_hm=1100)
    out, ev = guardrails.apply([easy(0, 500), easy(2, 500), easy(4, 500)], c)
    assert guardrails.planned_volume_hm(out) == 1500  # exento del 10%
    out, _ = guardrails.apply([easy(0, 300), easy(2, 300), easy(4, 300)], c)
    vol = guardrails.planned_volume_hm(out)
    assert 1500 - 3 <= vol <= 1500


def test_floor_ac66_respects_session_cap():
    c = ctx(base_10_hm=2000, floor_prev_hm=2000, target_distance_hm=600)
    out, ev = guardrails.apply([easy(0, 400), easy(2, 400), easy(4, 400)], c)
    assert all(run_volume_hm(s.blocks) <= 600 for s in out)
    assert guardrails.planned_volume_hm(out) == 1800  # el tope por sesión impide llegar a 20 km
    assert find(ev, "floor_scale")[0].after == 1800


def test_floor_reaches_target_when_possible():
    c = ctx(base_10_hm=1500, floor_prev_hm=1500)
    out, _ = guardrails.apply([easy(0, 333), easy(2, 333), easy(4, 334)], c)
    vol = guardrails.planned_volume_hm(out)
    assert 1500 - 3 <= vol <= 1650


def test_floors_not_applied_to_partial_plans():
    c = ctx(is_full=False, start_date=MON + timedelta(days=3), floor_prev_hm=2000, base_10_hm=2000)
    out, ev = guardrails.apply([easy(3, 300)], c)
    assert guardrails.planned_volume_hm(out) == 300
    assert not find(ev, "floor_scale")


def test_pending_reclass_two():
    s = [quality(0), walkrun(1), quality(3)]
    c = ctx(level="novato", pending_reclass=2, novice_quality_allowed=True)
    out, ev = guardrails.apply(s, c)
    assert out[0].blocks == [Block("run", 300)] and out[0].reclassified and out[0].title == "Trote suave"
    assert out[1].blocks == walkrun(1).blocks and out[1].reclassified and out[1].title == "Caminata y trote"
    assert not out[2].reclassified and out[2].blocks[1].target_pace_s is not None
    assert len(find(ev, "reclassification_pending")) == 2


def test_block_left_at_zero_is_kept():
    c = ctx(no_increase_hm=1)
    out, _ = guardrails.apply([easy(0, 300), easy(2, 300)], c)
    assert len(out) == 2 and all(len(s.blocks) == 1 for s in out)
    assert [s.blocks[0].distance_hm for s in out] == [0, 0]
