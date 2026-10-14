from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class MemberRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=20)
    gender: Literal["MALE", "FEMALE", "OTHER"] | None = None
    birth_date: date | None = None
    height_cm: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    fitness_goal: str | None = Field(default=None, max_length=200)

    @field_validator("gender", mode="before")
    @classmethod
    def normalize_gender(cls, value: object) -> object:
        if value in (None, "", "Prefer not to say", "PREFER_NOT_TO_SAY"):
            return None
        if isinstance(value, str):
            return value.upper()
        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    display_name: str
    email: str
    phone: str
    role: str
    status: str
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse


class MemberProfileResponse(BaseModel):
    member_id: int
    user_id: int
    username: str
    display_name: str
    email: str
    phone: str
    level_id: int
    level_code: str
    level_name: str
    discount_rate: Decimal
    total_spend: Decimal
    gender: str | None
    birth_date: date | None
    height_cm: Decimal | None
    weight_kg: Decimal | None
    fitness_goal: str | None


class MemberProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=6, max_length=20)
    gender: Literal["MALE", "FEMALE", "OTHER"] | None = None
    birth_date: date | None = None
    height_cm: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    fitness_goal: str | None = Field(default=None, max_length=200)


class MemberDashboardResponse(BaseModel):
    profile: MemberProfileResponse
    weekly_summary: "WeeklySummary"
    next_session: NextSession | None
    recommended_coaches: list["RecommendedCoach"]
    upcoming_bookings: list[dict]
    active_packages: list[dict]


class WeeklySummary(BaseModel):
    workouts_done: int
    workout_goal: int
    goal_percentage: int
    calories_burned: int
    active_minutes: int
    streak_days: int


class NextSession(BaseModel):
    booking_id: int
    booking_date: date
    start_time: str
    end_time: str
    duration_minutes: int
    service_mode: str
    price: Decimal
    coach_name: str
    course_name: str
    gym_name: str | None = None
    district: str | None = None

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time_or_delta(cls, v) -> str:
        if hasattr(v, "total_seconds"):
            total_seconds = int(v.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if isinstance(v, time):
            return v.strftime("%H:%M:%S")
        return str(v)


class RecommendedCoach(BaseModel):
    coach_id: int
    coach_no: str
    display_name: str
    avatar_url: str | None
    coach_level: str
    bio: str | None
    service_mode: str
    years_experience: int | None
    average_rating: Decimal
    review_count: int
    price_per_session: Decimal | None = None
