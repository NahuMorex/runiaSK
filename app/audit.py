"""Auditoría estructurada (R-18, FR-045): una línea JSON por evento en el logger `runia.audit`.

No importa nada de app.services, app.db ni app.ai.
"""

import json
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
_SENSITIVE = ("password", "token", "api_key", "authorization", "secret")
REDACTED = "[redacted]"

logger = logging.getLogger("runia.audit")


def _ensure_handler() -> None:
    if not any(getattr(h, "_runia_audit", False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._runia_audit = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


_ensure_handler()


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return k == "code" or any(s in k for s in _SENSITIVE)


def redact(obj):
    if isinstance(obj, dict):
        return {k: (REDACTED if isinstance(k, str) and _is_sensitive(k) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def summarize(text, limit: int = 500) -> str | None:
    if text is None:
        return None
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def event(type: str, **fields) -> dict:
    record = {"ts": datetime.now(_TZ).isoformat(), "type": type, **redact(fields)}
    logger.info(json.dumps(record, ensure_ascii=False, default=str))
    return record


def configure_logging() -> None:
    """httpx, httpcore y telegram registran en INFO URLs con el token del bot y `appid=` (SC-008)."""
    _ensure_handler()
    for name in ("httpx", "httpcore", "telegram"):
        logging.getLogger(name).setLevel(logging.WARNING)
