"""Único archivo que importa google-genai (principio I)."""

import asyncio
import time

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app import audit, config
from app.ai.errors import AIUnavailableError
from app.ai.prompts import (
    MESSAGE_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    build_message_prompt,
    build_plan_prompt,
)
from app.ai.schemas import DailyMessageData, PlanRequest, WeekPlanProposal

MODEL = "gemini-3.5-flash-lite"
PLAN_TIMEOUT_S = 20
MESSAGE_TIMEOUT_S = 5

_client_instance: genai.Client | None = None


def _client() -> genai.Client:
    global _client_instance
    if _client_instance is None:
        _client_instance = genai.Client(api_key=config.google_api_key())
    return _client_instance


def _map_error(exc: BaseException) -> AIUnavailableError:
    if isinstance(exc, AIUnavailableError):
        return exc
    if isinstance(exc, asyncio.TimeoutError):
        return AIUnavailableError("timeout")
    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None) or 0
        if code == 429:
            return AIUnavailableError("rate_limit", str(code))
        if code >= 500:
            return AIUnavailableError("server_error", str(code))
        return AIUnavailableError("error", str(code))
    if isinstance(exc, (ValidationError, ValueError)):
        return AIUnavailableError("invalid_response", type(exc).__name__)
    return AIUnavailableError("error", type(exc).__name__)


async def _generate(operation: str, prompt: str, system: str, timeout: float, schema=None, parse=None):
    cfg = types.GenerateContentConfig(system_instruction=system)
    if schema is not None:
        cfg = types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json", response_schema=schema
        )
    started = time.monotonic()
    text = None
    outcome = "ok"
    try:
        resp = await asyncio.wait_for(
            _client().aio.models.generate_content(model=MODEL, contents=prompt, config=cfg), timeout
        )
        text = resp.text
        if not text or not text.strip():
            raise AIUnavailableError("invalid_response", "respuesta vacía")
        return parse(text) if parse is not None else text
    except BaseException as exc:
        err = _map_error(exc)
        outcome = err.reason
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise err from exc
    finally:
        audit.event(
            "llm_call",
            operation=operation,
            prompt_summary=audit.summarize(prompt),
            response_summary=audit.summarize(text),
            duration_ms=round((time.monotonic() - started) * 1000),
            outcome=outcome,
        )


async def propose_week_plan(req: PlanRequest) -> WeekPlanProposal:
    return await _generate(
        "plan",
        build_plan_prompt(req),
        PLAN_SYSTEM_PROMPT,
        PLAN_TIMEOUT_S,
        schema=WeekPlanProposal,
        parse=WeekPlanProposal.model_validate_json,
    )


async def draft_daily_message(data: DailyMessageData) -> str:
    return await _generate("daily_message", build_message_prompt(data), MESSAGE_SYSTEM_PROMPT, MESSAGE_TIMEOUT_S)
