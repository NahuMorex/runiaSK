"""POST /sessions/{session_id}/result."""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.clock import Clock
from app.deps import get_clock, get_conn, get_current_user
from app.services import results

router = APIRouter()

ERRORS = {
    results.SessionNotFound: (404, "Sesión no encontrada"),
    results.Forbidden: (403, "Acceso denegado"),
    results.PostponedSession: (422, "La sesión fue pospuesta por clima y no admite registro"),
    results.NotToday: (422, "Solo podés registrar la sesión del día"),
    results.AlreadyRegistered: (409, "La sesión ya tiene un resultado registrado"),
    results.InvalidRpe: (422, "RPE inválido"),
}


class ResultBody(BaseModel):
    status: Literal["completed", "partial", "skipped"]
    rpe: int | None = Field(None, ge=1, le=10)
    notes: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _rpe_matches_status(self):
        if self.status == "skipped" and self.rpe is not None:
            raise ValueError("Una sesión salteada no lleva RPE")
        if self.status != "skipped" and self.rpe is None:
            raise ValueError("El RPE es obligatorio para una sesión completada o parcial")
        return self


@router.post("/sessions/{session_id}/result", status_code=201)
def post_result(
    session_id: int,
    body: ResultBody,
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
    clock: Clock = Depends(get_clock),
):
    try:
        return results.register_result(
            conn, user_id, session_id, body.status, body.rpe, body.notes, clock.now().date(), clock
        )
    except tuple(ERRORS) as exc:
        code, detail = ERRORS[type(exc)]
        raise HTTPException(code, detail) from None
