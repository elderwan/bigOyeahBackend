from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_app_db
from app.schemas.booking import BookingCreateRequest, BookingResponse
from app.services.booking_service import BookingService

router = APIRouter()


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreateRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> BookingResponse:
    if user["role"] != "MEMBER":
        raise HTTPException(status_code=403, detail="Member access required")
    member_result = await db.execute(
        text("SELECT member_id FROM member WHERE user_id = :user_id"),
        {"user_id": user["user_id"]},
    )
    member_id = member_result.scalar_one_or_none()
    if member_id is None:
        raise HTTPException(status_code=404, detail="Member profile not found")
    try:
        booking = await BookingService(db).create_booking(payload, int(member_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BookingResponse.model_validate(booking)
