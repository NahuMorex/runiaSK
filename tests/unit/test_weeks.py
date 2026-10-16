from datetime import date

from app.domain import weeks

MON = date(2026, 10, 12)
THU = date(2026, 10, 15)
SUN = date(2026, 10, 18)


def test_week_bounds():
    assert weeks.week_start(THU) == MON
    assert weeks.week_end(THU) == SUN
    assert weeks.week_start(MON) == MON


def test_remaining_days():
    assert weeks.remaining_days(MON) == 7
    assert weeks.remaining_days(THU) == 4
    assert weeks.remaining_days(SUN) == 1


def test_sessions_required():
    assert weeks.sessions_required(6, MON) == 6
    assert weeks.sessions_required(6, THU) == 4
    assert weeks.sessions_required(3, THU) == 3
    assert weeks.sessions_required(5, SUN) == 1


def test_allowed_dates():
    assert weeks.allowed_dates(THU) == [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17), SUN]
    assert weeks.allowed_dates(SUN) == [SUN]


def test_is_closed():
    assert not weeks.is_closed(MON, SUN)
    assert weeks.is_closed(MON, date(2026, 10, 19))
    assert weeks.previous_week_start(MON) == date(2026, 10, 5)


def test_weekday_es():
    assert weeks.weekday_es(THU) == "jueves"
    assert weeks.weekday_es(date(2026, 10, 14)) == "miércoles"
