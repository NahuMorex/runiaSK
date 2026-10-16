"""POST /plan y GET /schedule."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.ai import AIUnavailableError
from app.clock import Clock
from app.deps import get_clock, get_conn, get_current_user, get_planner
from app.domain import weeks
from app.services import plan_service, repository

router = APIRouter()

AI_UNAVAILABLE = "No es posible generar un plan en este momento."
NO_PLAN = "No tenés un plan para la semana en curso"


@router.post("/plan", status_code=201)
async def create_plan(
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
    clock: Clock = Depends(get_clock),
    planner=Depends(get_planner),
):
    try:
        plan_id = await plan_service.build_and_save_plan(conn, user_id, clock, planner, source="on_demand")
    except plan_service.IncompleteProfileError as exc:
        raise HTTPException(422, exc.message) from None
    except plan_service.PlanExistsError:
        raise HTTPException(409, "Ya tenés un plan para la semana en curso") from None
    except AIUnavailableError:
        raise HTTPException(503, AI_UNAVAILABLE) from None
    return plan_service.serialize_plan(conn, plan_id, clock.now().date())


@router.get("/schedule")
def get_schedule(
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
    clock: Clock = Depends(get_clock),
):
    """Plan de la semana en curso con el estado y el resultado de cada sesión (R-19)."""
    today = clock.now().date()
    plan = repository.get_plan_for_week(conn, user_id, weeks.week_start(today))
    if plan is None:
        raise HTTPException(404, NO_PLAN)
    return plan_service.serialize_plan(conn, plan["id"], today, include_result=True)
