"""POST /telegram/link-code."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.clock import Clock
from app.deps import get_clock, get_conn, get_current_user
from app.services import linking

router = APIRouter(prefix="/telegram")


@router.post("/link-code", status_code=201)
def create_link_code(
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
    clock: Clock = Depends(get_clock),
):
    try:
        code, expires_at = linking.create_link_code(conn, user_id, clock)
    except linking.AlreadyLinkedError:
        raise HTTPException(409, "Tu cuenta ya tiene un chat de Telegram vinculado") from None
    return {
        "code": code,
        "expires_at": expires_at.isoformat(),
        "instructions": f"Enviá /vincular {code} al bot dentro de los 15 minutos.",
    }
