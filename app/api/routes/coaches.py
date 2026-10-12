from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_app_db
from app.schemas.coaches import CoachSummary

router = APIRouter()


@router.get("/{coach_id}", response_model=CoachSummary)
async def get_coach(
    coach_id: int,
    db: AsyncSession = Depends(get_app_db),
) -> CoachSummary:
    result = await db.execute(
        text(
            """
            SELECT coach_id, coach_no, user_id, coach_level, bio, service_mode,
                   break_interval, years_experience, certifications, avatar_url,
                   status, hired_at
            FROM coach
            WHERE coach_id = :coach_id
            """
        ),
        {"coach_id": coach_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Coach not found")
    return CoachSummary.model_validate(dict(row))
