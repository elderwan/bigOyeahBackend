from datetime import date, datetime
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
    upcoming_bookings: list[dict]
    active_packages: list[dict]
