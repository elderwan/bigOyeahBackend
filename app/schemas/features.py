from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class BookingCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class ReviewCreateRequest(BaseModel):
    booking_id: int = Field(gt=0)
    rating_professional: int = Field(ge=1, le=5)
    rating_communication: int = Field(ge=1, le=5)
    rating_punctuality: int = Field(ge=1, le=5)
    rating_effectiveness: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class PackagePurchaseRequest(BaseModel):
    package_type: Literal["5+1", "10+3", "20+7"]
    payment_method: Literal["PROMPTPAY", "CARD", "CASH"] | None = None


class FitnessProfileUpdate(BaseModel):
    weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    body_fat_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    strongest_area: Literal[
        "UPPER_BODY", "CORE", "LOWER_BODY", "BACK", "SHOULDER", "FULL_BODY"
    ] | None = None
    weakest_area: Literal[
        "UPPER_BODY", "CORE", "LOWER_BODY", "BACK", "SHOULDER", "FULL_BODY"
    ] | None = None
    strongest_score: Decimal | None = Field(default=None, ge=1, le=5)
    weakest_score: Decimal | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def require_weight_for_measurement(self) -> "FitnessProfileUpdate":
        if self.body_fat_percent is not None and self.weight_kg is None:
            raise ValueError("weight_kg is required when body_fat_percent is provided")
        return self


class PaymentMethodUpdate(BaseModel):
    payment_method: Literal["PROMPTPAY", "CARD", "CASH"]
    label: str = Field(min_length=1, max_length=100)
    provider_token: str | None = Field(default=None, min_length=1, max_length=255)
    last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    is_default: bool = False


class PaymentMethodResponse(BaseModel):
    payment_method_id: int
    method_type: str
    label: str
    last_four: str | None
    is_default: bool
    status: str
    created_at: datetime


class MessageCreateRequest(BaseModel):
    coach_id: int = Field(gt=0)
    message_text: str = Field(min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    message_id: int
    coach_id: int
    coach_name: str
    member_id: int | None = None
    member_name: str | None = None
    sender_role: str
    message_text: str
    read_at: datetime | None
    created_at: datetime


class ProgressMetric(BaseModel):
    value: Decimal | None
    unit: str
    delta: Decimal | None = None
    category: str | None = None


class WeeklyActivitySlot(BaseModel):
    date: str
    day: str
    start_time: str
    end_time: str
    title: str
    coach_name: str
    status: str
    duration_minutes: int


class ProgressDashboardResponse(BaseModel):
    updated_at: str | None
    baseline: dict[str, ProgressMetric]
    weekly_activity: list[WeeklyActivitySlot]
    completed_sessions: int
