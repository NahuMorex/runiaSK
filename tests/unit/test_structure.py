from datetime import date, timedelta

import pytest

from app.domain.models import Block
from app.domain.structure import InvalidProposalError, validate_proposal

MON = date(2026, 10, 12)
THU = date(2026, 10, 15)


def run(km, pace=None, rec=None):
    return {"kind": "run", "distance_km": km, "target_pace_s": pace, "recovery_after_s": rec}


def walk(km):
    return {"kind": "walk", "distance_km": km}


def sess(d, blocks, title="Rodaje"):
    return {"date": d.isoformat(), "title": title, "blocks": blocks}


def prop(*sessions):
    return {"sessions": list(sessions)}


def validate(p, start=THU, n=None, novice=False):
    return validate_proposal(p, start_date=start, sessions_required=n if n is not None else len(p["sessions"]), first_week_novice=novice)


def test_valid_proposal_converts_to_hm():
    out = validate(prop(sess(THU, [run(2.35)]), sess(THU + timedelta(days=2), [run(1, 345, 120), run(1, 345)], "Intervalos")))
    assert out[0].blocks == [Block("run", 235)]
    assert out[1].blocks[0] == Block("run", 100, target_pace_s=345, recovery_after_s=120)
    assert out[1].blocks[0].target_time_s is None


@pytest.mark.parametrize(
    "p,n",
    [
        (prop(sess(THU, [run(2)])), 2),  # cantidad distinta
        (prop(sess(THU, [run(2)]), sess(THU, [run(2)])), 2),  # fecha repetida
        (prop(sess(THU - timedelta(days=1), [run(2)])), 1),  # antes de start_date
        (prop(sess(THU + timedelta(days=4), [run(2)])), 1),  # después del domingo
        (prop(sess(THU, [walk(2)])), 1),  # sin run
        (prop(sess(THU, [run(0)])), 1),  # km 0
        (prop(sess(THU, [run(-1)])), 1),  # km negativo
        (prop(sess(THU, [run(1, 59)])), 1),  # ritmo < 1:00
        (prop(sess(THU, [run(1, 1201)])), 1),  # ritmo > 20:00
        (prop(sess(THU, [run(1, 360, -5)])), 1),  # recuperación negativa
    ],
)
def test_general_rejections(p, n):
    with pytest.raises(InvalidProposalError):
        validate(p, n=n)


def test_novice_first_week_must_alternate():
    with pytest.raises(InvalidProposalError):
        validate(prop(sess(THU, [run(1)])), novice=True)
    with pytest.raises(InvalidProposalError):
        validate(prop(sess(THU, [walk(0.5), run(0.5), run(0.5)])), novice=True)
    out = validate(prop(sess(THU, [walk(0.5), run(0.5), walk(0.5), run(0.5)])), novice=True)
    assert [b.kind for b in out[0].blocks] == ["walk", "run", "walk", "run"]


def test_novice_first_week_rejects_paced_block():
    with pytest.raises(InvalidProposalError):
        validate(prop(sess(THU, [walk(0.5), run(0.5, 400), walk(0.5), run(0.5)])), novice=True)


@pytest.mark.parametrize("title", ["", "   ", "x" * 41, "Intervalos 4x1000"])
def test_title_normalized(title):
    easy, quality = validate(
        prop(sess(THU, [run(2)], title), sess(THU + timedelta(days=1), [run(1, 345, 60), run(1, 345)], title))
    )
    assert easy.title == "Trote suave"
    assert quality.title == "Calidad"


def test_valid_title_kept():
    assert validate(prop(sess(THU, [run(2)], "Rodaje largo")))[0].title == "Rodaje largo"
    assert validate(prop(sess(THU, [run(2)], "x" * 40)))[0].title == "x" * 40


def test_quality_with_two_reps_needs_recovery():
    with pytest.raises(InvalidProposalError):
        validate(prop(sess(THU, [run(1, 345), run(1, 345, 120)])))
    out = validate(prop(sess(THU, [run(1, 345, 120), run(1, 345)])))
    assert out[0].blocks[-1].recovery_after_s is None


def test_accepts_pydantic_like_objects():
    from app.ai.schemas import BlockOut, SessionOut, WeekPlanProposal

    p = WeekPlanProposal(sessions=[SessionOut(date=MON, title="Rodaje", blocks=[BlockOut(kind="run", distance_km=3)])])
    out = validate_proposal(p, start_date=MON, sessions_required=1, first_week_novice=False)
    assert out[0].date == MON
