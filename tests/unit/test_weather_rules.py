from datetime import date, timedelta

import pytest

from app.domain import weather_rules as wr
from app.integrations.openweather import Slot
from tests.helpers import ba

THU = date(2026, 10, 15)
START, END = 8 * 60, 10 * 60  # rango preferido 08:00–10:00


def slot(day: date, hour: int, pop=10, temp=20.0, thunder=False) -> Slot:
    return Slot(start=ba(day.year, day.month, day.day, hour), pop_pct=pop, temp_c=temp, thunderstorm=thunder)


def good_day(day: date) -> list[Slot]:
    return [slot(day, 6), slot(day, 9)]


# --- day_conditions -----------------------------------------------------------


def test_day_conditions_takes_max_of_overlapping_slots():
    slots = [
        slot(THU, 3, pop=95, temp=40.0, thunder=True),  # 03:00–06:00: no se solapa
        slot(THU, 6, pop=40, temp=22.0),  # 06:00–09:00: se solapa con 08:00–10:00
        slot(THU, 9, pop=70, temp=25.5),  # 09:00–12:00: se solapa
        slot(THU, 10, pop=99, temp=45.0, thunder=True),  # 10:00–13:00: no se solapa
    ]
    c = wr.day_conditions(slots, THU, START, END)
    assert c == wr.DayConditions(max_pop=70, max_temp=25.5, thunder=False)


def test_day_conditions_slot_ending_at_range_start_does_not_overlap():
    c = wr.day_conditions([slot(THU, 5, pop=90)], THU, START, END)  # 05:00–08:00
    assert c is None


def test_day_conditions_without_slots_is_none():
    assert wr.day_conditions([], THU, START, END) is None
    assert wr.day_conditions(good_day(THU + timedelta(days=1)), THU, START, END) is None


# --- Umbrales -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("pop", "temp", "thunder", "unfavorable", "extreme"),
    [
        (60, 20.0, False, False, False),
        (61, 20.0, False, True, False),
        (10, 32.0, False, False, False),
        (10, 32.1, False, True, False),
        (10, 38.0, False, True, False),
        (10, 38.1, False, True, True),
        (80, 20.0, False, True, False),
        (81, 20.0, False, True, True),
        (10, 20.0, True, True, True),
    ],
)
def test_thresholds(pop, temp, thunder, unfavorable, extreme):
    c = wr.DayConditions(max_pop=pop, max_temp=temp, thunder=thunder)
    assert wr.is_unfavorable(c) is unfavorable
    assert wr.is_extreme(c) is extreme


def test_thunderstorm_slot_from_weather_id_211_is_extreme():
    c = wr.day_conditions([slot(THU, 6, thunder=True)], THU, START, END)
    assert wr.is_extreme(c)


# --- Motivos ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("c", "text"),
    [
        (wr.DayConditions(70, 20.0, False), "lluvia probable (70%)"),
        (wr.DayConditions(10, 35.4, False), "calor extremo (35 °C)"),
        (wr.DayConditions(10, 34.5, False), "calor extremo (35 °C)"),
        (wr.DayConditions(10, 20.0, True), "tormenta eléctrica"),
        (wr.DayConditions(85, 39.0, True), "lluvia probable (85%) y calor extremo (39 °C) y tormenta eléctrica"),
    ],
)
def test_reasons_text(c, text):
    assert wr.reasons_text(c) == text


# --- assess -------------------------------------------------------------------


def test_favorable_day_has_no_alert():
    a = wr.assess(good_day(THU), THU, START, END)
    assert a.available and not a.unfavorable and not a.extreme and not a.postpone
    assert a.reasons == [] and a.alternative_date is None


def test_alternative_is_first_favorable_day_within_three():
    fri, sat = THU + timedelta(days=1), THU + timedelta(days=2)
    slots = [slot(THU, 6, pop=70), slot(fri, 6, temp=33.0), *good_day(sat)]
    a = wr.assess(slots, THU, START, END)
    assert a.unfavorable and not a.extreme and not a.postpone
    assert a.reasons == ["lluvia probable (70%)"]
    assert a.alternative_date == sat


def test_day_without_forecast_cannot_be_alternative():
    sat = THU + timedelta(days=2)
    slots = [slot(THU, 6, pop=70), *good_day(sat)]  # el viernes no tiene datos
    assert wr.assess(slots, THU, START, END).alternative_date == sat


def test_alternative_never_after_sunday():
    sat = date(2026, 10, 17)
    mon = date(2026, 10, 19)
    slots = [slot(sat, 6, pop=70), slot(sat + timedelta(days=1), 6, pop=90), *good_day(mon)]
    a = wr.assess(slots, sat, START, END)
    assert a.unfavorable and a.alternative_date is None


def test_alternative_window_is_three_days():
    mon = date(2026, 10, 12)
    slots = [slot(mon + timedelta(days=i), 6, pop=70) for i in range(4)] + good_day(mon + timedelta(days=4))
    assert wr.assess(slots, mon, START, END).alternative_date is None


def test_extreme_without_alternative_postpones():
    slots = [slot(THU + timedelta(days=i), 6, pop=90) for i in range(4)]
    a = wr.assess(slots, THU, START, END)
    assert a.extreme and a.postpone and a.alternative_date is None


def test_extreme_with_alternative_only_alerts():
    fri = THU + timedelta(days=1)
    slots = [slot(THU, 6, thunder=True), *good_day(fri)]
    a = wr.assess(slots, THU, START, END)
    assert a.extreme and not a.postpone and a.alternative_date == fri
    assert a.reasons == ["tormenta eléctrica"]


def test_assessment_roundtrip_through_dict():
    fri = THU + timedelta(days=1)
    a = wr.assess([slot(THU, 6, pop=70), *good_day(fri)], THU, START, END)
    assert wr.assessment_from_dict(wr.assessment_to_dict(a)) == a
    assert wr.assessment_from_dict({"available": False}) == wr.unavailable()


# --- Textos fijos -------------------------------------------------------------


def test_fixed_texts():
    assert wr.NO_ALTERNATIVE_TEXT == "No hay una alternativa disponible esta semana"
    assert wr.WEATHER_UNAVAILABLE_TEXT == "Clima no disponible: seguí las pautas base de ritmo e hidratación."


def test_postponement_message():
    base = (
        "Tu sesión de hoy quedó pospuesta por clima: lluvia probable (90%). "
        "No hay un día alternativo libre de condiciones desfavorables esta semana."
    )
    assert wr.postponement_message("lluvia probable (90%)", 1) == base
    assert wr.postponement_message("lluvia probable (90%)", 2) == base + " Esta semana ya tenés 2 sesiones pospuestas por clima."
    assert len(wr.postponement_message("tormenta eléctrica", 7).split()) <= 150
