from datetime import date

from pydantic import BaseModel, ConfigDict


class CoachSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    coach_id: int
    coach_no: str
    user_id: int
    coach_level: str
    bio: str | None
    service_mode: str
    break_interval: int
    years_experience: int | None
    certifications: str | None
    avatar_url: str | None
    status: str
    hired_at: date | None
