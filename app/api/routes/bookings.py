from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_app_db
from app.schemas.booking import BookingCreateRequest, BookingResponse
from app.services.booking_service import BookingService

router = APIRouter()


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreateRequest,
    db: AsyncSession = Depends(get_app_db),
) -> BookingResponse:
    try:
        booking = await BookingService(db).create_booking(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BookingResponse.model_validate(booking)
