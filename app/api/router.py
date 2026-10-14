from fastapi import APIRouter

from app.api.routes import (
    admin,
    auth,
    bookings,
    catalog,
    coaches,
    health,
    member_features,
    members,
    orders,
    schedules,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(members.router, prefix="/members", tags=["members"])
api_router.include_router(member_features.router, prefix="/members/me", tags=["member features"])
api_router.include_router(catalog.router, tags=["catalog"])
api_router.include_router(coaches.router, prefix="/coaches", tags=["coaches"])
api_router.include_router(schedules.router, prefix="/coaches", tags=["schedules"])
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
