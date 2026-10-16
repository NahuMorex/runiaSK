"""Pipeline determinista de guardarraíles de carga (R-06, FR-017..FR-026, FR-042).

`apply` es una función pura: recibe las sesiones propuestas y el contexto de la semana
y devuelve las sesiones seguras más un evento por cada regla que cambió algo.
"""

import math
from dataclasses import replace
from fractions import Fraction

from app.domain import units
from app.domain.models import (
    EASY_TITLE,
    Block,
    GuardrailContext,
    GuardrailEvent,
    PlannedSession,
    is_quality,
    reclassify,
    run_volume_hm,
    to_easy,
)

INITIAL_SESSION_CAP_HM = {"novato": 200, "intermedio": 500, "avanzado": 1000}


def planned_volume_hm(sessions: list[PlannedSession]) -> int:
    return sum(run_volume_hm(s.blocks) for s in sessions)


def session_cap(ctx: GuardrailContext) -> tuple[int, str]:
    """Tope por sesión efectivo: el menor entre el tope inicial (si aplica) y la distancia objetivo."""
    caps = [(ctx.target_distance_hm, "target_distance")]
    if ctx.initial_caps:
        caps.insert(0, (INITIAL_SESSION_CAP_HM[ctx.level], "initial_cap"))
    return min(caps, key=lambda c: c[0])


def weekly_caps(ctx: GuardrailContext) -> list[tuple[int, str]]:
    caps = []
    if ctx.initial_caps:
        caps.append((INITIAL_SESSION_CAP_HM[ctx.level] * ctx.frequency, "initial_weekly"))
    if ctx.base_10_hm is not None and not ctx.is_post_deload:
        caps.append((ctx.base_10_hm * 11 // 10, "ten_percent"))
    if ctx.no_increase_hm is not None:
        caps.append((ctx.no_increase_hm, "no_increase"))
    if ctx.is_deload and ctx.deload_v4_hm is not None:
        caps.append((ctx.deload_v4_hm * 8 // 10, "deload"))
    if ctx.post_deload_target_hm is not None:
        caps.append((ctx.post_deload_target_hm, "post_deload"))
    return caps


def weekly_cap(ctx: GuardrailContext) -> tuple[int, str] | None:
    caps = weekly_caps(ctx)
    return min(caps, key=lambda c: c[0]) if caps else None


def weekly_floor(ctx: GuardrailContext) -> int | None:
    """Piso efectivo (solo planes de semana completa): el mayor de los aplicables (R-10)."""
    if not ctx.is_full:
        return None
    floors = []
    if ctx.floor_prev_hm is not None:
        floors.append(ctx.floor_prev_hm)
    if ctx.is_deload and ctx.deload_v4_hm is not None:
        floors.append(math.ceil(Fraction(ctx.deload_v4_hm * 7, 10)))
    if ctx.post_deload_target_hm is not None:
        floors.append(ctx.post_deload_target_hm)
    return max(floors) if floors else None


def _with_times(blocks: list[Block]) -> list[Block]:
    return [
        replace(b, target_time_s=units.target_time_s(b.distance_hm, b.target_pace_s))
        if b.kind == "run" and b.target_pace_s is not None
        else replace(b, target_time_s=None)
        for b in blocks
    ]


def _scale_runs(blocks: list[Block], factor: Fraction) -> list[Block]:
    return _with_times(
        [replace(b, distance_hm=units.scale_floor(b.distance_hm, factor)) if b.kind == "run" else b for b in blocks]
    )


def _to_easy_session(s: PlannedSession) -> PlannedSession:
    return replace(s, blocks=to_easy(s.blocks), title=EASY_TITLE)


def apply(sessions: list[PlannedSession], ctx: GuardrailContext) -> tuple[list[PlannedSession], list[GuardrailEvent]]:
    events: list[GuardrailEvent] = []
    out = sorted(sessions, key=lambda s: s.date)

    # 1. Reclasificación pendiente (FR-042)
    for i in range(min(ctx.pending_reclass, len(out))):
        s = out[i]
        was_quality = is_quality(s.blocks)
        new = replace(s, blocks=reclassify(s.blocks), reclassified=True)
        if was_quality:
            new = replace(new, title=EASY_TITLE)
        out[i] = new
        events.append(
            GuardrailEvent("reclassification_pending", "session", s.date, "calidad" if was_quality else "suave", "suave")
        )

    # 2. Calidad para novatos (FR-022)
    if ctx.level == "novato" and not ctx.novice_quality_allowed:
        for i, s in enumerate(out):
            if is_quality(s.blocks):
                out[i] = _to_easy_session(s)
                events.append(GuardrailEvent("novice_quality", "session", s.date, "calidad", "suave"))

    # 3. Máximo una de calidad por semana (FR-023)
    seen_quality = False
    for i, s in enumerate(out):
        if is_quality(s.blocks):
            if seen_quality:
                out[i] = _to_easy_session(s)
                events.append(GuardrailEvent("max_one_quality", "session", s.date, "calidad", "suave"))
            seen_quality = True

    # 4. Ritmo de calidad (FR-024)
    if ctx.current_pace_s is not None:
        slow, fast = ctx.current_pace_s, units.fast_pace_limit(ctx.current_pace_s)
        for i, s in enumerate(out):
            blocks = []
            for b in s.blocks:
                if b.kind == "run" and b.target_pace_s is not None:
                    clamped = min(max(b.target_pace_s, fast), slow)
                    if clamped != b.target_pace_s:
                        events.append(GuardrailEvent("pace_clamp", "session", s.date, b.target_pace_s, clamped))
                        b = replace(b, target_pace_s=clamped)
                blocks.append(b)
            out[i] = replace(s, blocks=blocks)
    out = [replace(s, blocks=_with_times(s.blocks)) for s in out]

    # 5. Topes por sesión (FR-018 por sesión, FR-025)
    cap_s, cap_rule = session_cap(ctx)
    for i, s in enumerate(out):
        vol = run_volume_hm(s.blocks)
        if vol > cap_s:
            new_blocks = _scale_runs(s.blocks, Fraction(cap_s, vol))
            out[i] = replace(s, blocks=new_blocks)
            events.append(GuardrailEvent("session_cap", "session", s.date, vol, run_volume_hm(new_blocks), cap_rule))

    # 6. Topes semanales (FR-018..FR-021), sobre el volumen ya recortado
    wcap = weekly_cap(ctx)
    vol = planned_volume_hm(out)
    if wcap is not None and vol > wcap[0]:
        factor = Fraction(wcap[0], vol)
        out = [replace(s, blocks=_scale_runs(s.blocks, factor)) for s in out]
        events.append(GuardrailEvent("weekly_cap", "week", None, vol, planned_volume_hm(out), wcap[1]))

    # 7. Pisos (FR-026), solo en planes de semana completa; los topes prevalecen
    floor = weekly_floor(ctx)
    vol = planned_volume_hm(out)
    n_runs = sum(1 for s in out for b in s.blocks if b.kind == "run")
    if floor is not None and vol > 0 and vol < floor - n_runs:
        factors = [Fraction(floor, vol)]
        factors += [Fraction(cap_s, rv) for s in out if (rv := run_volume_hm(s.blocks)) > 0]
        if wcap is not None:
            factors.append(Fraction(wcap[0], vol))
        factor = min(factors)
        if factor > 1:
            out = [replace(s, blocks=_scale_runs(s.blocks, factor)) for s in out]
            events.append(GuardrailEvent("floor_scale", "week", None, vol, planned_volume_hm(out)))

    return out, events
