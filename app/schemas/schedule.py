from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScheduleCreateResponse(BaseModel):
    coach_id: int
    table_name: str


class ScheduleSlot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot_start: datetime
    slot_year: int
    slot_month: int
    slot_day: int
    slot_hour: int
    slot_minute: int
    status: str
    booking_id: int | None
    remark: str | None
    created_at: datetime
    updated_at: datetime
