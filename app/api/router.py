from fastapi import APIRouter

from app.api.routes import bookings, coaches, health, schedules

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(coaches.router, prefix="/coaches", tags=["coaches"])
api_router.include_router(schedules.router, prefix="/coaches", tags=["schedules"])
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
