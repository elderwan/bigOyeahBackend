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
    districts: list[str] = []
    service_types: list[str] = []
    price_per_session: Decimal | None = None
    verified: bool = True


class CoachSearchResponse(BaseModel):
    items: list[CoachListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


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


class CoachMessageCreateRequest(BaseModel):
    member_id: int = Field(gt=0)
    message_text: str = Field(min_length=1, max_length=2000)


class CoachMemberReviewRequest(BaseModel):
    booking_id: int = Field(gt=0)
    completion_score: int = Field(ge=1, le=5)
    proficiency_score: int = Field(ge=1, le=5)
    training_area: str = Field(pattern="^(UPPER_BODY|CORE|LOWER_BODY|BACK|SHOULDER|FULL_BODY)$")
    training_type: str = Field(pattern="^(STRENGTH|CARDIO|FLEXIBILITY|BALANCE|POWER)$")
    coach_note: str | None = Field(default=None, max_length=1000)


class CoachScheduleBlockRequest(BaseModel):
    date: date
    start_time: str
    end_time: str
    reason: str = Field(min_length=1, max_length=100)
