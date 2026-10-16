"""Argon2id, JWT renovable y códigos de un solo uso (R-15, R-16)."""

import hashlib
import secrets
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app import config

TOKEN_TTL = timedelta(hours=2)
MAX_SESSION_AGE = timedelta(days=7)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)


class InvalidToken(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_token(user_id: int, auth_time: datetime, now: datetime) -> tuple[str, datetime]:
    expires_at = now + TOKEN_TTL
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "auth_time": int(auth_time.timestamp()),
    }
    return jwt.encode(payload, config.jwt_secret(), algorithm="HS256"), expires_at


def decode_token(token: str, now: datetime) -> tuple[int, datetime]:
    try:
        payload = jwt.decode(
            token,
            config.jwt_secret(),
            algorithms=["HS256"],
            options={"verify_exp": False, "verify_iat": False, "require": ["sub", "exp", "auth_time"]},
        )
        user_id = int(payload["sub"])
        exp = int(payload["exp"])
        auth_time = datetime.fromtimestamp(int(payload["auth_time"]), tz=now.tzinfo)
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise InvalidToken(str(exc)) from exc
    if now.timestamp() >= exp:
        raise InvalidToken("token vencido")
    if now - auth_time >= MAX_SESSION_AGE:
        raise InvalidToken("sesión de más de 7 días")
    return user_id, auth_time


def generate_code(length: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()
