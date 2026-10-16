"""Reclasificación por una Parcial/Cortada con RPE ≥ 7 (FR-042). Funciones puras."""

from datetime import date

SESSIONS_TO_RECLASSIFY = 2
RPE_THRESHOLD = 7


def triggers(status: str, rpe: int | None) -> bool:
    return status == "partial" and rpe is not None and rpe >= RPE_THRESHOLD


def targets_after(session_date: date, upcoming_sessions: list[tuple[int, date]]) -> tuple[list[int], int]:
    """Las 2 primeras sesiones posteriores a `session_date` y cuántas quedan para el plan siguiente.

    `upcoming_sessions` no incluye las pospuestas por clima: no cuentan como objetivo (AC-41).
    """
    later = sorted((d, sid) for sid, d in upcoming_sessions if d > session_date)
    ids = [sid for _, sid in later[:SESSIONS_TO_RECLASSIFY]]
    return ids, SESSIONS_TO_RECLASSIFY - len(ids)
