"""Tick del scheduler (R-03): corre cada 60 s y es idempotente gracias a las filas de control."""

import asyncio
from datetime import datetime

from app import audit, db
from app.clock import FixedClock
from app.services import weekly_job

TICK_SECONDS = 60


async def tick(state, now: datetime) -> None:
    clock = FixedClock(now)
    conn = db.connect(state.db_path)
    try:
        await weekly_job.run_monday(conn, clock, state.planner, state.notifier)
    finally:
        conn.close()


async def run_forever(state) -> None:
    while True:
        try:
            await tick(state, state.clock.now())
        except Exception as exc:
            audit.event("scheduler_error", reason=type(exc).__name__)
        await asyncio.sleep(TICK_SECONDS)
