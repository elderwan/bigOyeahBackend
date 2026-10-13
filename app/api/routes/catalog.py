from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_app_db

router = APIRouter()


@router.get("/courses", response_model=list[dict])
async def list_courses(
    difficulty: str | None = Query(default=None),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT course_id, course_name, description, equipment, difficulty,
                   default_duration, is_active
            FROM course
            WHERE is_active = 1 AND (:difficulty IS NULL OR difficulty = :difficulty)
            ORDER BY course_name
            """
        ),
        {"difficulty": difficulty},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/courses/{course_id}", response_model=dict)
async def get_course(course_id: int, db: AsyncSession = Depends(get_app_db)) -> dict:
    result = await db.execute(
        text(
            """
            SELECT course_id, course_name, description, equipment, difficulty,
                   default_duration, is_active
            FROM course WHERE course_id = :course_id AND is_active = 1
            """
        ),
        {"course_id": course_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return dict(row)


@router.get("/gyms", response_model=list[dict])
async def list_gyms(
    district: str | None = Query(default=None),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT gym_id, gym_name, address, district, phone, facilities,
                   opening_time, closing_time, latitude, longitude
            FROM gym
            WHERE is_active = 1 AND (:district IS NULL OR district = :district)
            ORDER BY gym_name
            """
        ),
        {"district": district},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/coaches/{coach_id}/courses", response_model=list[dict])
async def list_coach_courses(coach_id: int, db: AsyncSession = Depends(get_app_db)) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT c.course_id, c.course_name, c.description, c.difficulty,
                   c.default_duration, cc.price_per_session
            FROM coach_course cc
            JOIN course c ON c.course_id = cc.course_id
            WHERE cc.coach_id = :coach_id AND cc.is_active = 1 AND c.is_active = 1
            ORDER BY c.course_name
            """
        ),
        {"coach_id": coach_id},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/coaches/{coach_id}/services", response_model=list[dict])
async def list_coach_services(coach_id: int, db: AsyncSession = Depends(get_app_db)) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT cs.coach_service_id, cs.gym_id, g.gym_name, g.address, g.district,
                   cs.is_home_service, cs.service_area
            FROM coach_service cs
            JOIN gym g ON g.gym_id = cs.gym_id
            WHERE cs.coach_id = :coach_id AND cs.is_active = 1 AND g.is_active = 1
            ORDER BY g.gym_name
            """
        ),
        {"coach_id": coach_id},
    )
    return [dict(row) for row in result.mappings().all()]
