"""Validación estructural de la propuesta del modelo (FR-027, R-05).

No importa app.ai: recibe la propuesta por duck typing (atributos) o como dict.
"""

import re
from datetime import date

from app.domain import units, weeks
from app.domain.models import EASY_TITLE, QUALITY_TITLE, Block, PlannedSession, is_quality

MIN_PACE_S = 60
MAX_PACE_S = 1200
MAX_TITLE_LEN = 40
_DIGIT_RE = re.compile(r"\d")


class InvalidProposalError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise InvalidProposalError(f"fecha inválida: {value!r}") from None


def normalize_title(title, blocks: list[Block]) -> str:
    text = (title or "").strip() if isinstance(title, str) else ""
    if not text or len(text) > MAX_TITLE_LEN or _DIGIT_RE.search(text):
        return QUALITY_TITLE if is_quality(blocks) else EASY_TITLE
    return text


def _alternates_walk_run(blocks: list[Block]) -> bool:
    kinds = [b.kind for b in blocks]
    if "walk" not in kinds or "run" not in kinds:
        return False
    return all(a != b for a, b in zip(kinds, kinds[1:]))


def _convert_block(raw) -> Block:
    kind = _get(raw, "kind")
    if kind not in ("walk", "run"):
        raise InvalidProposalError(f"tipo de bloque inválido: {kind!r}")
    km = _get(raw, "distance_km")
    if km is None:
        raise InvalidProposalError("bloque sin km")
    hm = units.km_to_hm(float(km))
    if hm <= 0:
        raise InvalidProposalError("bloque con km ≤ 0")
    pace = _get(raw, "target_pace_s")
    if pace is not None:
        if kind != "run":
            raise InvalidProposalError("ritmo objetivo en un bloque de caminata")
        if not MIN_PACE_S <= int(pace) <= MAX_PACE_S:
            raise InvalidProposalError("ritmo fuera de 1:00–20:00 min/km")
        pace = int(pace)
    recovery = _get(raw, "recovery_after_s")
    if recovery is not None:
        if int(recovery) < 0:
            raise InvalidProposalError("recuperación negativa")
        recovery = int(recovery)
    return Block(kind, hm, target_pace_s=pace, recovery_after_s=recovery)


def validate_proposal(proposal, *, start_date: date, sessions_required: int, first_week_novice: bool) -> list[PlannedSession]:
    raw_sessions = _get(proposal, "sessions")
    if raw_sessions is None:
        raise InvalidProposalError("propuesta sin sesiones")
    raw_sessions = list(raw_sessions)
    if len(raw_sessions) != sessions_required:
        raise InvalidProposalError(f"cantidad de sesiones {len(raw_sessions)} ≠ {sessions_required}")

    end = weeks.week_end(start_date)
    seen: set[date] = set()
    result: list[PlannedSession] = []
    for raw in raw_sessions:
        d = _as_date(_get(raw, "date"))
        if d in seen:
            raise InvalidProposalError(f"dos sesiones el {d}")
        seen.add(d)
        if not start_date <= d <= end:
            raise InvalidProposalError(f"fecha {d} fuera del plan")

        blocks = [_convert_block(b) for b in (_get(raw, "blocks") or [])]
        if not any(b.kind == "run" for b in blocks):
            raise InvalidProposalError(f"sesión {d} sin bloques de trote")

        paced = [i for i, b in enumerate(blocks) if b.target_pace_s is not None]
        if len(paced) >= 2 and any(blocks[i].recovery_after_s is None for i in paced[:-1]):
            raise InvalidProposalError(f"sesión {d} sin recuperación entre tramos")

        if first_week_novice:
            if not _alternates_walk_run(blocks):
                raise InvalidProposalError(f"sesión {d} de novato sin alternar caminata y trote")
            if paced:
                raise InvalidProposalError(f"sesión {d} de novato con tramo con ritmo")

        result.append(PlannedSession(date=d, title=normalize_title(_get(raw, "title"), blocks), blocks=blocks))

    return sorted(result, key=lambda s: s.date)
