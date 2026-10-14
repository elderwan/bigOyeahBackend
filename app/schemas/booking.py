from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BookingCreateRequest(BaseModel):
    member_id: int | None = None
    coach_id: int
    course_id: int
    gym_id: int | None = None
    package_id: int | None = None
    booking_date: date
    start_time: time
    duration_minutes: int = Field(gt=0, multiple_of=10)
    break_minutes: Literal[10, 20, 30]
    service_mode: Literal["GYM", "HOME"]
    service_district: str | None = None
    service_address: str | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def validate_service_location(self) -> "BookingCreateRequest":
        if self.start_time.second != 0 or self.start_time.minute % 10 != 0:
            raise ValueError("start_time must align to a 10-minute grid")
        if self.service_mode == "GYM":
            if (
                self.gym_id is None
                or self.service_district is not None
                or self.service_address is not None
            ):
                raise ValueError("GYM bookings require gym_id and no home-service fields")
        elif self.gym_id is not None or not self.service_district or not self.service_address:
            raise ValueError("HOME bookings require service_district and service_address only")
        return self


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    booking_id: int
    member_id: int
    coach_id: int
    course_id: int
    gym_id: int | None
    package_id: int | None
    booking_date: date
    start_time: str
    end_time: str
    duration_minutes: int
    break_minutes: int
    service_mode: str
    service_district: str | None
    service_address: str | None
    price: Decimal
    status: str
    expires_at: datetime | None
    cancelled_by: str | None
    cancel_reason: str | None
    cancelled_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time_or_delta(cls, v) -> str:
        if isinstance(v, timedelta):
            total_seconds = int(v.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if isinstance(v, time):
            return v.strftime("%H:%M:%S")
        return str(v)
