from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.session import get_app_db, get_ddl_engine
from app.schemas.schedule import ScheduleCreateResponse, ScheduleSlot
from app.services.schedule_service import ScheduleService

router = APIRouter()


@router.post(
    "/{coach_id}/schedule",
    response_model=ScheduleCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a coach dynamic schedule table",
)
async def create_schedule(
    coach_id: int,
    db: AsyncSession = Depends(get_app_db),
    ddl_engine: AsyncEngine = Depends(get_ddl_engine),
) -> ScheduleCreateResponse:
    try:
        table_name = await ScheduleService(db, ddl_engine).create_schedule_table(coach_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScheduleCreateResponse(coach_id=coach_id, table_name=table_name)


@router.get(
    "/{coach_id}/schedule/slots",
    response_model=list[ScheduleSlot],
    summary="List slots from a coach dynamic schedule table",
)
async def list_schedule_slots(
    coach_id: int,
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    db: AsyncSession = Depends(get_app_db),
) -> list[ScheduleSlot]:
    if end_at <= start_at:
        raise HTTPException(status_code=400, detail="end_at must be later than start_at")
    try:
        rows = await ScheduleService(db).list_slots(coach_id, start_at, end_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [ScheduleSlot.model_validate(dict(row)) for row in rows]
