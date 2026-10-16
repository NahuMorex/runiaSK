"""Dependencias de FastAPI: conexión, reloj, usuario actual y servicios inyectables."""

import sqlite3

from fastapi import Depends, Header, HTTPException, Request, Response

from app import db, security
from app.clock import Clock
from app.services import repository


def get_conn(request: Request):
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_current_user(
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
    clock: Clock = Depends(get_clock),
    authorization: str | None = Header(None),
) -> int:
    """Valida el JWT y emite uno renovado en X-Session-Token (R-15)."""
    unauthorized = HTTPException(status_code=401, detail="No autenticado")
    if not authorization or not authorization.startswith("Bearer "):
        raise unauthorized
    now = clock.now()
    try:
        user_id, auth_time = security.decode_token(authorization[len("Bearer "):].strip(), now)
    except security.InvalidToken:
        raise unauthorized from None
    if repository.get_user(conn, user_id) is None:
        raise unauthorized
    token, _ = security.create_token(user_id, auth_time, now)
    response.headers["X-Session-Token"] = token
    return user_id


def get_planner(request: Request):
    return request.app.state.planner


def get_writer(request: Request):
    return request.app.state.writer


def get_weather(request: Request):
    return request.app.state.weather


def get_notifier(request: Request):
    return request.app.state.notifier
