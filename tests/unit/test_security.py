from datetime import timedelta

import pytest

from app import config, security
from tests.helpers import ba

NOW = ba(2026, 10, 15, 10)


def test_argon2id_params():
    h = security.hash_password("clave-segura-1")
    assert h.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert security.verify_password(h, "clave-segura-1")
    assert not security.verify_password(h, "otra")
    assert not security.verify_password("no-es-un-hash", "otra")


def test_token_expires_after_2h():
    token, expires_at = security.create_token(7, NOW, NOW)
    assert expires_at == NOW + timedelta(hours=2)
    assert security.decode_token(token, NOW + timedelta(hours=1, minutes=59))[0] == 7
    with pytest.raises(security.InvalidToken):
        security.decode_token(token, NOW + timedelta(hours=2))


def test_token_rejected_after_7_days_from_login():
    later = NOW + timedelta(days=7)
    token, _ = security.create_token(7, NOW, later - timedelta(minutes=1))
    with pytest.raises(security.InvalidToken):
        security.decode_token(token, later)


def test_token_bad_signature():
    token, _ = security.create_token(7, NOW, NOW)
    with pytest.raises(security.InvalidToken):
        security.decode_token(token + "x", NOW)
    with pytest.raises(security.InvalidToken):
        security.decode_token("basura", NOW)


def test_hash_code_stable_and_case_insensitive():
    assert security.hash_code("abcd2345") == security.hash_code("ABCD2345")
    assert len(security.hash_code("X")) == 64


def test_generate_code_alphabet():
    code = security.generate_code(10)
    assert len(code) == 10
    assert set(code) <= set(security.CODE_ALPHABET)


def test_missing_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(config.MissingConfigError, match="JWT_SECRET"):
        config.jwt_secret()
    with pytest.raises(config.MissingConfigError):
        security.create_token(1, NOW, NOW)


def test_telegram_token_optional(monkeypatch):
    assert config.telegram_bot_token() is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    assert config.telegram_bot_token() == "x"
