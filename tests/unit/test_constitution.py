"""Principios de la constitución verificados sobre el código: IA aislada, dominio puro y sin secretos."""

import ast
import re
import subprocess
from pathlib import Path

import pytest

from app.ai.prompts import MESSAGE_SYSTEM_PROMPT, PLAN_SYSTEM_PROMPT, build_message_prompt, build_plan_prompt
from app.ai.schemas import PlanRequest
from app.clock import FixedClock
from app.domain import daily_message
from app.domain.models import DailyMessageData
from app.services import plan_service, repository
from tests.helpers import FakePlanner, ba, seed_user

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
GEMINI = APP / "ai" / "gemini.py"
FORBIDDEN_IN_DOMAIN = ("app.services", "app.ai", "app.integrations", "app.db")
CREDENTIAL_PATTERNS = [re.compile(r"AIza[0-9A-Za-z_-]{20,}"), re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}")]
EMAIL = "milena.privada@example.com"
CHAT_ID = 987654321


def _imported_modules(path: Path) -> set[str]:
    """Módulos importados, incluidos los de `from app import db` (que se cuentan como `app.db`)."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


# --- Principio I: IA aislada ----------------------------------------------------


def test_google_genai_only_in_gemini_module():
    offenders = [
        str(p.relative_to(ROOT))
        for p in APP.rglob("*.py")
        if p != GEMINI and re.search(r"google\.genai|from google import genai", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
    assert "from google import genai" in GEMINI.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", sorted((APP / "domain").glob("*.py")), ids=lambda p: p.name)
def test_domain_does_not_import_io_layers(path):
    bad = sorted(m for m in _imported_modules(path) if m.startswith(FORBIDDEN_IN_DOMAIN))
    assert bad == []


# --- Principio II y SC-009: sin secretos en el repo -------------------------------


def _versioned_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / name for name in out.decode().split("\0") if name]


def test_versioned_files_have_no_credentials():
    files = _versioned_files()
    assert files
    hits = []
    for path in files:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits += [f"{path.relative_to(ROOT)}: {m.group()[:6]}…" for rx in CREDENTIAL_PATTERNS for m in rx.finditer(text)]
    assert hits == []


def test_env_file_is_ignored():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    assert ".env" not in {p.name for p in _versioned_files()}


# --- Prompts: prohibición médica, entrada en calor y datos personales -------------


@pytest.mark.parametrize("prompt", [PLAN_SYSTEM_PROMPT, MESSAGE_SYSTEM_PROMPT], ids=["plan", "message"])
def test_system_prompts_forbid_medical_and_injury_advice(prompt):
    text = prompt.lower()
    assert "no des consejo médico" in text
    assert "lesiones" in text


def test_plan_prompt_asks_for_explicit_warmup_and_cooldown_blocks():
    text = PLAN_SYSTEM_PROMPT.lower()
    assert "entrada en calor" in text
    assert "vuelta a la calma" in text
    assert "bloques" in text and "explícitos" in text


def test_plan_prompt_keeps_target_pace_out_of_easy_runs():
    text = PLAN_SYSTEM_PROMPT.lower()
    assert "cuenta como sesión de calidad" in text
    assert "los rodajes suaves, la entrada en calor y la vuelta a la calma nunca llevan `target_pace_s`" in text


def test_prompt_schemas_have_no_personal_identifiers():
    for model in (PlanRequest, DailyMessageData):
        fields = {f.lower() for f in model.model_fields}
        assert not any("email" in f or "chat" in f for f in fields)


@pytest.mark.anyio
async def test_built_prompts_do_not_include_email_or_chat_id(conn):
    uid = seed_user(conn, EMAIL, chat_id=CHAT_ID)
    planner = FakePlanner()
    await plan_service.build_and_save_plan(conn, uid, FixedClock(ba(2026, 10, 15, 10)), planner, source="on_demand")
    plan_prompt = build_plan_prompt(planner.requests[0])

    session = repository.get_session_for_user_on(conn, uid, ba(2026, 10, 15).date())
    data = daily_message.build_message_data(session, repository.get_profile(conn, uid), 5, None, False)
    message_prompt = build_message_prompt(data)

    for prompt in (plan_prompt, message_prompt):
        assert EMAIL not in prompt and "@" not in prompt
        assert str(CHAT_ID) not in prompt
        assert "email" not in prompt.lower() and "chat_id" not in prompt.lower()
