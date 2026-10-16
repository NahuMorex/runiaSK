"""POST /auth/register, /auth/login y /auth/password-reset."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.clock import Clock
from app.deps import get_clock, get_conn
from app.services import accounts

router = APIRouter(prefix="/auth")


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=201)
def register(body: RegisterBody, conn: sqlite3.Connection = Depends(get_conn), clock: Clock = Depends(get_clock)):
    email = str(body.email).lower()
    try:
        user_id = accounts.register(conn, email, body.password, clock.now())
    except accounts.EmailTakenError:
        raise HTTPException(409, "El email ya está registrado") from None
    return {"id": user_id, "email": email}


@router.post("/login")
def login(body: LoginBody, conn: sqlite3.Connection = Depends(get_conn), clock: Clock = Depends(get_clock)):
    try:
        token, expires_at = accounts.login(conn, body.email, body.password, clock)
    except accounts.InvalidCredentialsError:
        raise HTTPException(401, "Credenciales inválidas") from None
    return {"access_token": token, "token_type": "bearer", "expires_at": expires_at.isoformat()}


class PasswordResetBody(BaseModel):
    code: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/password-reset")
def password_reset(body: PasswordResetBody, conn: sqlite3.Connection = Depends(get_conn), clock: Clock = Depends(get_clock)):
    """El cuerpo se valida antes de tocar el código: una contraseña inválida no lo consume (AC-50)."""
    try:
        accounts.reset_password(conn, body.code, body.new_password, clock)
    except accounts.InvalidResetCode:
        raise HTTPException(400, "Código inválido o vencido") from None
    return {"detail": "Contraseña actualizada"}
