from datetime import date

import pytest

from app.domain import daily_message as dm
from app.domain.models import EASY_TITLE, Block, DailyMessageData

PROFILE = {"range_start_min": 7 * 60, "range_end_min": 9 * 60}
QUALITY_BLOCKS = [
    Block("run", 150),
    Block("run", 100, 345, 345, 120),
    Block("run", 100, 345, 345),
    Block("walk", 50),
]
WALK_RUN_BLOCKS = [Block("walk", 50), Block("run", 50), Block("walk", 50), Block("run", 50)]


def session(blocks, title="Intervalos"):
    return {"date": date(2026, 10, 15), "title": title, "blocks": blocks}


def data_for(blocks, title="Intervalos", fatigue=None):
    return dm.build_message_data(session(blocks, title), PROFILE, fatigue, None, False)


def words(text):
    return len(text.split())


# --- Plantilla (AC-27, AC-28) -------------------------------------------------


def test_render_sequence_matches_contract():
    seq = dm.render_sequence(QUALITY_BLOCKS)
    assert seq == (
        "trote 1,50 km; trote 1,00 km a 5:45 min/km (5:45), recuperación 2:00; "
        "trote 1,00 km a 5:45 min/km (5:45); caminata 0,50 km"
    )


def test_template_quality_includes_type_range_pace_and_sequence():
    text = dm.render_template(data_for(QUALITY_BLOCKS))
    assert words(text) <= 150
    assert "Hoy: calidad (Intervalos)." in text
    assert "Horario sugerido: 07:00–09:00." in text
    assert "Ritmo objetivo: 5:45 min/km." in text
    assert "Secuencia: " + dm.render_sequence(QUALITY_BLOCKS) + "." in text


def test_template_walk_run_includes_sequence_without_pace():
    data = data_for(WALK_RUN_BLOCKS, title="Caminata y trote")
    text = dm.render_template(data)
    assert "suave" in text and "07:00–09:00" in text
    assert "caminata 0,50 km; trote 0,50 km; caminata 0,50 km; trote 0,50 km" in text
    assert data.target_pace is None and "Ritmo objetivo" not in text


def test_template_easy_has_type_and_range():
    text = dm.render_template(data_for([Block("run", 500)], title="Rodaje"))
    assert text.startswith("Hoy: suave (Rodaje).") and "07:00–09:00" in text and "trote 5,00 km" in text


def test_template_truncates_long_sequence_to_150_words():
    blocks = [Block("run", 100)] + [Block("run", 40, 345, 138, 90) for _ in range(40)]
    data = data_for(blocks)
    text = dm.render_template(data)
    assert words(text) <= 150
    assert "bloques más" in text
    assert "Ritmo objetivo: 5:45 min/km." in text and "07:00–09:00" in text
    assert dm.validate_draft(text, data)


# --- Fatiga (AC-48, AC-80) ----------------------------------------------------


def test_high_fatigue_turns_quality_into_single_easy_block():
    blocks, label, title, kept_easy = dm.apply_fatigue(QUALITY_BLOCKS, "Intervalos", 8)
    assert blocks == [Block("run", 350)]
    assert label == "suave/recuperación" and title == EASY_TITLE and kept_easy is False
    data = data_for(QUALITY_BLOCKS, fatigue=9)
    text = dm.render_template(data)
    assert data.session_type_label == "suave/recuperación" and data.target_pace is None
    assert data.sequence == "trote 3,50 km"
    assert "min/km" not in text and "suave/recuperación" in text


def test_high_fatigue_keeps_easy_session_and_says_so():
    blocks, label, title, kept_easy = dm.apply_fatigue(WALK_RUN_BLOCKS, "Caminata y trote", 10)
    assert blocks == WALK_RUN_BLOCKS and title == "Caminata y trote" and kept_easy is True
    assert label == "suave/recuperación"
    data = data_for(WALK_RUN_BLOCKS, title="Caminata y trote", fatigue=8)
    assert data.fatigue_kept_easy_text == "La sesión se mantiene suave por la fatiga."
    assert "La sesión se mantiene suave por la fatiga." in dm.render_template(data)


@pytest.mark.parametrize("fatigue", [None, 1, 7])
def test_low_or_missing_fatigue_does_not_adjust(fatigue):
    blocks, label, title, kept_easy = dm.apply_fatigue(QUALITY_BLOCKS, "Intervalos", fatigue)
    assert blocks == QUALITY_BLOCKS and label == "calidad" and title == "Intervalos" and not kept_easy


# --- Validación del borrador (AC-78) ------------------------------------------

VALID = (
    "Buen día. Tu sesión de hoy es de calidad, Intervalos, con ritmo objetivo 5:45 min/km. "
    "Te sugiero salir en el horario 07:00–09:00. "
    "Secuencia: trote 1,50 km; trote 1,00 km a 5:45 min/km (5:45), recuperación 2:00; "
    "trote 1,00 km a 5:45 min/km (5:45); caminata 0,50 km. Disfrutala."
)


def test_valid_reordered_draft_is_accepted():
    data = data_for(QUALITY_BLOCKS)
    assert dm.validate_draft(VALID, data)
    assert dm.validate_draft(dm.render_template(data), data)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        VALID + " palabra" * 150,
        VALID.replace("07:00–09:00", "por la mañana"),
        VALID + " Hoy son 12 km en total.",
        VALID + " ¿Listo",
        VALID + " Listo?",
        VALID.replace("Buen día.", "**Buen día.**"),
        "# Hoy\n" + VALID,
        "- " + VALID,
        VALID + " Mirá [x](y)",
    ],
    ids=[
        "vacio",
        "espacios",
        "151_palabras",
        "sin_rango",
        "numero_ajeno",
        "apertura_pregunta",
        "cierre_pregunta",
        "negrita",
        "titulo",
        "lista",
        "enlace",
    ],
)
def test_invalid_drafts_are_rejected(text):
    assert not dm.validate_draft(text, data_for(QUALITY_BLOCKS))


def test_missing_pace_is_rejected():
    data = DailyMessageData(
        session_type_label="calidad", title="Intervalos", suggested_range="07:00–09:00", target_pace="5:45 min/km"
    )
    assert dm.validate_draft("Hoy: calidad. Horario 07:00–09:00. Ritmo objetivo 5:45 min/km.", data)
    assert not dm.validate_draft("Hoy: calidad. Horario 07:00–09:00. Ritmo cómodo.", data)


def test_exactly_150_words_passes_and_151_fails():
    data = data_for(QUALITY_BLOCKS)
    filler = 150 - words(VALID)
    assert dm.validate_draft(VALID + " bien" * filler, data)
    assert not dm.validate_draft(VALID + " bien" * (filler + 1), data)


def test_allowed_numbers_are_normalized():
    data = data_for(QUALITY_BLOCKS)
    nums = dm.allowed_numbers(data)
    assert {"7:00", "9:00", "5:45", "1,50", "2:00"} <= nums
    assert dm.validate_draft(VALID.replace("trote 1,50 km;", "trote 1.50 km; trote 1,50 km;"), data)
    assert dm.validate_draft(VALID + " Arrancá a las 7:00.", data)


def test_kept_easy_text_is_required():
    data = data_for(WALK_RUN_BLOCKS, title="Caminata y trote", fatigue=9)
    assert "La sesión se mantiene suave por la fatiga." in dm.required_fragments(data)
    text = dm.render_template(data)
    assert dm.validate_draft(text, data)
    assert not dm.validate_draft(text.replace("La sesión se mantiene suave por la fatiga.", ""), data)
