from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_app_db

router = APIRouter()


@router.get("/courses", response_model=list[dict])
async def list_courses(
    search: str | None = Query(default=None, max_length=100),
    difficulty: str | None = Query(default=None),
    is_active: int | None = Query(default=None),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT c.course_id, c.course_name, c.description, c.equipment, c.difficulty,
                   c.default_duration, c.is_active,
                   COUNT(cc.coach_id) AS coach_count
            FROM course c
            LEFT JOIN coach_course cc ON cc.course_id = c.course_id AND cc.is_active = 1
            WHERE (:is_active IS NULL OR c.is_active = :is_active)
              AND (:difficulty IS NULL OR c.difficulty = :difficulty)
              AND (:search IS NULL OR c.course_name LIKE CONCAT('%', :search, '%')
                   OR c.description LIKE CONCAT('%', :search, '%')
                   OR c.equipment LIKE CONCAT('%', :search, '%'))
            GROUP BY c.course_id, c.course_name, c.description, c.equipment, c.difficulty,
                     c.default_duration, c.is_active
            ORDER BY c.course_name
            """
        ),
        {"search": search, "difficulty": difficulty, "is_active": is_active},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/courses/{course_id}", response_model=dict)
async def get_course(course_id: int, db: AsyncSession = Depends(get_app_db)) -> dict:
    result = await db.execute(
        text(
            """
            SELECT course_id, course_name, description, equipment, difficulty,
                   default_duration, is_active
            FROM course WHERE course_id = :course_id
            """
        ),
        {"course_id": course_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Course not found")
    data = dict(row)

    # Get assigned coaches
    coaches_result = await db.execute(
        text(
            """
            SELECT cc.coach_id, cc.price_per_session, u.display_name, c.coach_no
            FROM coach_course cc
            JOIN coach c ON c.coach_id = cc.coach_id
            JOIN users u ON u.user_id = c.user_id
            WHERE cc.course_id = :course_id AND cc.is_active = 1
            """
        ),
        {"course_id": course_id},
    )
    coaches = [dict(c) for c in coaches_result.mappings().all()]
    data["coaches"] = coaches
    data["assigned_coach_ids"] = [c["coach_id"] for c in coaches]
    return data


@router.get("/gyms", response_model=list[dict])
async def list_gyms(
    search: str | None = Query(default=None, max_length=100),
    district: str | None = Query(default=None),
    is_active: int | None = Query(default=None),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT g.gym_id, g.gym_name, g.address, g.district, g.phone, g.facilities,
                   g.opening_time, g.closing_time, g.latitude, g.longitude, g.is_active,
                   COUNT(cs.coach_id) AS coach_count
            FROM gym g
            LEFT JOIN coach_service cs ON cs.gym_id = g.gym_id AND cs.is_active = 1
            WHERE (:is_active IS NULL OR g.is_active = :is_active)
              AND (:district IS NULL OR g.district = :district)
              AND (:search IS NULL OR g.gym_name LIKE CONCAT('%', :search, '%')
                   OR g.address LIKE CONCAT('%', :search, '%')
                   OR g.facilities LIKE CONCAT('%', :search, '%'))
            GROUP BY g.gym_id, g.gym_name, g.address, g.district, g.phone, g.facilities,
                     g.opening_time, g.closing_time, g.latitude, g.longitude, g.is_active
            ORDER BY g.gym_name
            """
        ),
        {"search": search, "district": district, "is_active": is_active},
    )
    items = []
    for row in result.mappings().all():
        d = dict(row)
        if d.get("opening_time") is not None:
            d["opening_time"] = str(d["opening_time"])
        if d.get("closing_time") is not None:
            d["closing_time"] = str(d["closing_time"])
        items.append(d)
    return items


@router.get("/gyms/{gym_id}", response_model=dict)
async def get_gym(gym_id: int, db: AsyncSession = Depends(get_app_db)) -> dict:
    result = await db.execute(
        text(
            """
            SELECT gym_id, gym_name, address, district, phone, facilities,
                   opening_time, closing_time, latitude, longitude, is_active
            FROM gym WHERE gym_id = :gym_id
            """
        ),
        {"gym_id": gym_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Gym not found")
    data = dict(row)
    if data.get("opening_time") is not None:
        data["opening_time"] = str(data["opening_time"])
    if data.get("closing_time") is not None:
        data["closing_time"] = str(data["closing_time"])

    # Get assigned coaches
    coaches_result = await db.execute(
        text(
            """
            SELECT cs.coach_id, cs.is_home_service, cs.service_area, u.display_name, c.coach_no
            FROM coach_service cs
            JOIN coach c ON c.coach_id = cs.coach_id
            JOIN users u ON u.user_id = c.user_id
            WHERE cs.gym_id = :gym_id AND cs.is_active = 1
            """
        ),
        {"gym_id": gym_id},
    )
    coaches = [dict(c) for c in coaches_result.mappings().all()]
    data["coaches"] = coaches
    data["assigned_coach_ids"] = [c["coach_id"] for c in coaches]
    return data


@router.get("/packages", response_model=list[dict])
async def list_package_catalog(
    is_active: int | None = Query(default=None),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT package_type, paid_sessions, bonus_sessions, price,
                   validity_days, is_active, created_at, updated_at
            FROM package_catalog
            WHERE (:is_active IS NULL OR is_active = :is_active)
            ORDER BY paid_sessions
            """
        ),
        {"is_active": is_active},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/packages/{package_type}", response_model=dict)
async def get_package(package_type: str, db: AsyncSession = Depends(get_app_db)) -> dict:
    result = await db.execute(
        text(
            """
            SELECT package_type, paid_sessions, bonus_sessions, price,
                   validity_days, is_active, created_at, updated_at
            FROM package_catalog
            WHERE package_type = :package_type
            """
        ),
        {"package_type": package_type},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Package catalog item not found")
    return dict(row)


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
