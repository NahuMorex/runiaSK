"""Verificador independiente de SC-001: reimplementa la lista cerrada de reglas desde la spec.

No importa app.domain.guardrails a propósito: si el pipeline tuviera un error, este verificador no lo heredaría.
"""

import math
from fractions import Fraction

from app.domain import units
from app.domain.models import GuardrailContext, PlannedSession

_INITIAL = {"novato": 200, "intermedio": 500, "avanzado": 1000}


def _run_hm(session: PlannedSession) -> int:
    return sum(b.distance_hm for b in session.blocks if b.kind == "run")


def _n_runs(session: PlannedSession) -> int:
    return sum(1 for b in session.blocks if b.kind == "run")


def _is_quality(session: PlannedSession) -> bool:
    return any(b.kind == "run" and b.target_pace_s is not None for b in session.blocks)


def _session_cap(ctx: GuardrailContext) -> int:
    caps = [ctx.target_distance_hm]  # FR-025
    if ctx.initial_caps:
        caps.append(_INITIAL[ctx.level])  # FR-018
    return min(caps)


def _weekly_cap(ctx: GuardrailContext) -> int | None:
    caps = []
    if ctx.initial_caps:
        caps.append(_INITIAL[ctx.level] * ctx.frequency)  # FR-018
    if ctx.base_10_hm is not None and not ctx.is_post_deload:
        caps.append(math.floor(Fraction(ctx.base_10_hm * 11, 10)))  # FR-019
    if ctx.no_increase_hm is not None:
        caps.append(ctx.no_increase_hm)  # FR-020
    if ctx.is_deload and ctx.deload_v4_hm is not None:
        caps.append(math.floor(Fraction(ctx.deload_v4_hm * 8, 10)))  # FR-021 tope
    if ctx.post_deload_target_hm is not None:
        caps.append(ctx.post_deload_target_hm)  # FR-021 semana posterior
    return min(caps) if caps else None


def _floor(ctx: GuardrailContext) -> int | None:
    if not ctx.is_full:
        return None
    floors = []
    if ctx.floor_prev_hm is not None:
        floors.append(ctx.floor_prev_hm)  # AC-66
    if ctx.is_deload and ctx.deload_v4_hm is not None:
        floors.append(math.ceil(Fraction(ctx.deload_v4_hm * 7, 10)))  # FR-021 piso
    if ctx.post_deload_target_hm is not None:
        floors.append(ctx.post_deload_target_hm)
    return max(floors) if floors else None


def check_sc001(sessions: list[PlannedSession], ctx: GuardrailContext) -> list[str]:
    violations: list[str] = []
    ordered = sorted(sessions, key=lambda s: s.date)
    cap_s = _session_cap(ctx)
    volume = sum(_run_hm(s) for s in ordered)
    n_runs = sum(_n_runs(s) for s in ordered)

    for s in ordered:
        if _run_hm(s) > cap_s:
            violations.append(f"{s.date}: {_run_hm(s)} hm supera el tope por sesión {cap_s}")

    wcap = _weekly_cap(ctx)
    if wcap is not None and volume > wcap:
        violations.append(f"volumen {volume} supera el tope semanal {wcap}")

    quality = [s for s in ordered if _is_quality(s)]
    if ctx.level == "novato" and not ctx.novice_quality_allowed and quality:
        violations.append("novato no elegible con sesión de calidad")
    if len(quality) > 1:
        violations.append(f"{len(quality)} sesiones de calidad")

    for s in ordered:
        for b in s.blocks:
            if b.target_pace_s is None:
                continue
            if b.kind != "run":
                violations.append(f"{s.date}: ritmo en caminata")
                continue
            p = ctx.current_pace_s
            if p is None or not units.fast_pace_limit(p) <= b.target_pace_s <= p:
                violations.append(f"{s.date}: ritmo {b.target_pace_s} fuera de rango para {p}")
            expected = (2 * b.distance_hm * b.target_pace_s + 100) // 200
            if b.target_time_s != expected:
                violations.append(f"{s.date}: tiempo {b.target_time_s} ≠ {expected}")

    for s in ordered[: ctx.pending_reclass]:
        if not s.reclassified or _is_quality(s):
            violations.append(f"{s.date}: reclasificación pendiente no aplicada")

    floor = _floor(ctx)
    if floor is not None and volume < floor - n_runs:
        session_at_cap = any(_run_hm(s) >= cap_s - _n_runs(s) for s in ordered)
        week_at_cap = wcap is not None and volume >= wcap - n_runs
        if not (session_at_cap or week_at_cap):
            violations.append(f"volumen {volume} por debajo del piso {floor}")

    return violations
