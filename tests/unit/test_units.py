from fractions import Fraction

import pytest

from app.domain import units


def test_km_hm_roundtrip():
    assert units.km_to_hm(2.35) == 235
    assert units.km_to_hm(42.2) == 4220
    assert units.hm_to_km(235) == 2.35


@pytest.mark.parametrize("hm,text", [(235, "2,35"), (0, "0,00"), (1000, "10,00"), (5, "0,05")])
def test_format_km(hm, text):
    assert units.format_km(hm) == text


def test_parse_and_format_pace():
    assert units.parse_pace("6:00") == 360
    assert units.parse_pace("10:00") == 600
    assert units.parse_pace("05:45") == 345
    assert units.format_pace(345) == "5:45"


@pytest.mark.parametrize("text", ["6:60", "6", "abc", "6:5", ":30", "100:00", ""])
def test_parse_pace_invalid(text):
    with pytest.raises(ValueError):
        units.parse_pace(text)


def test_hhmm():
    assert units.parse_hhmm("00:00") == 0
    assert units.parse_hhmm("23:59") == 1439
    assert units.format_hhmm(420) == "07:00"
    for bad in ("24:00", "7:00", "12:60", "x"):
        with pytest.raises(ValueError):
            units.parse_hhmm(bad)


def test_format_duration():
    assert units.format_duration(345) == "5:45"
    assert units.format_duration(3599) == "59:59"
    assert units.format_duration(3600) == "1:00:00"
    assert units.format_duration(3725) == "1:02:05"


def test_fast_pace_limit():
    assert units.fast_pace_limit(360) == 340
    assert units.fast_pace_limit(300) == 284  # 283,2 → 284


def test_target_time():
    assert units.target_time_s(100, 345) == 345
    assert units.target_time_s(150, 345) == 518  # 517,5 → 518
    assert units.target_time_s(33, 300) == 99


def test_scale_floor():
    assert units.scale_floor(800, Fraction(5, 8)) == 500
    assert units.scale_floor(333, Fraction(5, 8)) == 208  # 208,125
    assert units.scale_floor(1, Fraction(5, 8)) == 0
