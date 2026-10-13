from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


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
    payment_method: Literal["PROMPTPAY", "CARD", "CASH"]


class FitnessProfileUpdate(BaseModel):
    strongest_area: Literal[
        "UPPER_BODY", "CORE", "LOWER_BODY", "BACK", "SHOULDER", "FULL_BODY"
    ] | None = None
    weakest_area: Literal[
        "UPPER_BODY", "CORE", "LOWER_BODY", "BACK", "SHOULDER", "FULL_BODY"
    ] | None = None
    strongest_score: Decimal | None = Field(default=None, ge=1, le=5)
    weakest_score: Decimal | None = Field(default=None, ge=1, le=5)


class PaymentMethodUpdate(BaseModel):
    payment_method: Literal["PROMPTPAY", "CARD", "CASH"]
    label: str = Field(min_length=1, max_length=100)
