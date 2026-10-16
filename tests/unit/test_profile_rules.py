import pytest
from pydantic import ValidationError

from app.domain.profile_rules import ProfileUpdate, ProfileValidationError, merge_and_validate, to_public

EMPTY = {
    "level": None,
    "frequency": None,
    "target_distance_hm": None,
    "current_pace_s": None,
    "city": None,
    "range_start_min": None,
    "range_end_min": None,
    "send_time_min": None,
}

FULL = {
    "level": "intermedio",
    "frequency": 4,
    "target_distance_km": 10,
    "current_pace": "6:00",
    "city": "Rosario",
    "preferred_range": {"start": "07:00", "end": "09:00"},
    "send_time": "06:00",
}


def merged(stored=None, **update):
    return merge_and_validate(stored or EMPTY, ProfileUpdate(**update))


def test_full_profile_converts_units():
    p = merged(**FULL)
    assert p == {
        "level": "intermedio",
        "frequency": 4,
        "target_distance_hm": 1000,
        "current_pace_s": 360,
        "city": "Rosario",
        "range_start_min": 420,
        "range_end_min": 540,
        "send_time_min": 360,
    }


@pytest.mark.parametrize(
    "update",
    [
        {"frequency": 1},
        {"frequency": 7},
        {"target_distance_km": 1},
        {"target_distance_km": 42.2},
        {"current_pace": "3:00"},
        {"current_pace": "10:00"},
        {"city": "x" * 100},
        {"preferred_range": {"start": "07:00", "end": "08:00"}, "send_time": "07:59"},
        {"current_pace": None},
    ],
)
def test_accepts_limits(update):
    merged(**update)


@pytest.mark.parametrize(
    "update",
    [
        {"frequency": 0},
        {"frequency": 8},
        {"target_distance_km": 0.99},
        {"target_distance_km": 42.21},
        {"current_pace": "2:59"},
        {"current_pace": "10:01"},
        {"current_pace": "6:60"},
        {"city": ""},
        {"city": "   "},
        {"city": "x" * 101},
        {"preferred_range": {"start": "09:00", "end": "09:00"}},
        {"preferred_range": {"start": "10:00", "end": "09:00"}},
        {"preferred_range": {"start": "07:00", "end": "07:59"}},
        {"preferred_range": {"start": "07:00", "end": "09:00"}, "send_time": "09:00"},
        {"preferred_range": {"start": "07:00", "end": "09:00"}, "send_time": "09:30"},
        {"level": None},
        {"frequency": None},
        {"city": None},
        {"send_time": None},
        {"preferred_range": None},
        {"target_distance_km": None},
    ],
)
def test_rejects(update):
    with pytest.raises(ProfileValidationError):
        merged(**update)


def test_rejects_unknown_level_and_extra_fields():
    with pytest.raises(ValidationError):
        ProfileUpdate(level="experto")
    with pytest.raises(ValidationError):
        ProfileUpdate(foo=1)


def test_partial_update_validates_against_stored():
    stored = merged(**FULL)
    # Rango guardado 07:00–09:00: un envío a las 09:00 combina mal con lo guardado.
    with pytest.raises(ProfileValidationError):
        merged(stored, send_time="09:00")
    # Cambiar el rango para que el envío guardado (06:00) siga siendo anterior al fin.
    p = merged(stored, preferred_range={"start": "05:00", "end": "06:30"})
    assert p["range_end_min"] == 390 and p["send_time_min"] == 360
    # Un rango que deja el envío guardado después del fin se rechaza.
    with pytest.raises(ProfileValidationError):
        merged(stored, preferred_range={"start": "04:00", "end": "05:00"})


def test_partial_update_keeps_other_fields():
    stored = merged(**FULL)
    p = merged(stored, frequency=6)
    assert p["frequency"] == 6
    assert p["city"] == "Rosario" and p["current_pace_s"] == 360


def test_to_public():
    p = merged(**FULL)
    assert to_public(p, linked=True) == {**FULL, "target_distance_km": 10.0, "telegram_linked": True}
    assert to_public(EMPTY, linked=False) == {
        "level": None,
        "frequency": None,
        "target_distance_km": None,
        "current_pace": None,
        "city": None,
        "preferred_range": None,
        "send_time": None,
        "telegram_linked": False,
    }
