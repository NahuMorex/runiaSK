"""GET/PUT/DELETE /profile."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app import audit
from app.clock import Clock
from app.db import transaction
from app.deps import get_clock, get_conn, get_current_user
from app.domain.profile_rules import ProfileUpdate, ProfileValidationError, merge_and_validate, to_public
from app.services import repository

router = APIRouter(prefix="/profile")


def _public(conn, user_id: int) -> dict:
    linked = repository.get_chat_id(conn, user_id) is not None
    return to_public(repository.get_profile(conn, user_id), linked)


@router.get("")
def get_profile(user_id: int = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_conn)):
    return _public(conn, user_id)


@router.put("")
def put_profile(
    body: ProfileUpdate,
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
    clock: Clock = Depends(get_clock),
):
    with transaction(conn):
        try:
            merged = merge_and_validate(repository.get_profile(conn, user_id), body)
        except ProfileValidationError as exc:
            raise HTTPException(422, exc.errors) from None
        repository.update_profile(conn, user_id, merged, clock.now())
    audit.event("tool_call", tool="db", op="update_profile", user_id=user_id)
    return _public(conn, user_id)
