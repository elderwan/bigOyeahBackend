from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class CoachListItem(BaseModel):
    coach_id: int
    coach_no: str
    display_name: str
    avatar_url: str | None
    coach_level: str
    bio: str | None
    service_mode: str
    years_experience: int | None
    average_rating: Decimal | None
    review_count: int


class CoachProfileResponse(CoachListItem):
    user_id: int
    email: str
    phone: str
    certifications: str | None
    break_interval: int
    status: str
    hired_at: date | None
    courses: list[dict]
    gyms: list[dict]


class CoachProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=100)
    phone: str | None = Field(default=None, min_length=6, max_length=20)
    bio: str | None = None
    service_mode: str | None = None
    years_experience: int | None = Field(default=None, ge=0, le=255)
    certifications: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=255)
