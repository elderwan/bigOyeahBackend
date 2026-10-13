from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_app_db
from app.schemas.coach import (
    CoachListItem,
    CoachProfileResponse,
    CoachProfileUpdate,
    CoachSearchResponse,
)
from app.schemas.coaches import CoachSummary

router = APIRouter()


@router.get("/me", response_model=CoachProfileResponse)
async def get_my_coach_profile_route(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> CoachProfileResponse:
    if user["role"] != "COACH":
        raise HTTPException(status_code=403, detail="Coach access required")
    result = await db.execute(
        text("SELECT coach_id FROM coach WHERE user_id = :user_id"),
        {"user_id": user["user_id"]},
    )
    coach_id = result.scalar_one_or_none()
    if coach_id is None:
        raise HTTPException(status_code=404, detail="Coach profile not found")
    return await get_coach_profile(int(coach_id), db)


@router.patch("/me", response_model=CoachProfileResponse)
async def update_my_coach_profile_route(
    payload: CoachProfileUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> CoachProfileResponse:
    return await update_my_coach_profile(payload, user, db)


@router.get("", response_model=CoachSearchResponse)
async def list_coaches(
    search: str | None = Query(default=None, max_length=100),
    district: str | None = None,
    course_id: int | None = Query(default=None, gt=0),
    service_mode: str | None = Query(default=None, pattern="^(GYM|HOME|BOTH)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=50),
    db: AsyncSession = Depends(get_app_db),
) -> CoachSearchResponse:
    offset = (page - 1) * page_size
    result = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, u.display_name, c.avatar_url,
                   c.coach_level, c.bio, c.service_mode, c.years_experience,
                   COALESCE(AVG(rc.avg_rating), 0) AS average_rating,
                   COUNT(rc.review_coach_id) AS review_count,
                   GROUP_CONCAT(DISTINCT cs.service_area) AS districts,
                   GROUP_CONCAT(DISTINCT
                       CASE WHEN cs.is_home_service = 1 THEN 'HOME' ELSE 'GYM' END
                   ) AS service_types,
                   MIN(cc.price_per_session) AS price_per_session
            FROM coach c
            JOIN users u ON u.user_id = c.user_id AND u.status = 'ACTIVE'
            LEFT JOIN review_coach rc ON rc.booking_id IN (
                SELECT b.booking_id FROM booking b WHERE b.coach_id = c.coach_id
            )
            LEFT JOIN coach_service cs ON cs.coach_id = c.coach_id
            LEFT JOIN coach_course cc ON cc.coach_id = c.coach_id AND cc.is_active = 1
            WHERE c.status = 'ACTIVE'
              AND (:search IS NULL OR u.display_name LIKE CONCAT('%', :search, '%')
                   OR c.bio LIKE CONCAT('%', :search, '%')
                   OR cs.service_area LIKE CONCAT('%', :search, '%'))
              AND (:district IS NULL OR cs.service_area = :district)
              AND (:course_id IS NULL OR cc.course_id = :course_id)
              AND (:service_mode IS NULL OR c.service_mode = :service_mode
                   OR (:service_mode = 'HOME' AND cs.is_home_service = 1))
            GROUP BY c.coach_id, c.coach_no, u.display_name, c.avatar_url,
                     c.coach_level, c.bio, c.service_mode, c.years_experience
            ORDER BY average_rating DESC, review_count DESC, u.display_name
            LIMIT :page_size OFFSET :offset
            """
        ),
        {
            "search": search,
            "district": district,
            "course_id": course_id,
            "service_mode": service_mode,
            "page_size": page_size,
            "offset": offset,
        },
    )
    items = []
    for row in result.mappings().all():
        item = dict(row)
        item["districts"] = [value for value in (item.get("districts") or "").split(",") if value]
        item["service_types"] = [
            value for value in (item.get("service_types") or "").split(",") if value
        ]
        items.append(CoachListItem.model_validate(item))

    count_result = await db.execute(
        text(
            """
            SELECT COUNT(DISTINCT c.coach_id)
            FROM coach c
            JOIN users u ON u.user_id = c.user_id AND u.status = 'ACTIVE'
            LEFT JOIN coach_service cs ON cs.coach_id = c.coach_id
            LEFT JOIN coach_course cc ON cc.coach_id = c.coach_id AND cc.is_active = 1
            WHERE c.status = 'ACTIVE'
              AND (:search IS NULL OR u.display_name LIKE CONCAT('%', :search, '%')
                   OR c.bio LIKE CONCAT('%', :search, '%')
                   OR cs.service_area LIKE CONCAT('%', :search, '%'))
              AND (:district IS NULL OR cs.service_area = :district)
              AND (:course_id IS NULL OR cc.course_id = :course_id)
              AND (:service_mode IS NULL OR c.service_mode = :service_mode
                   OR (:service_mode = 'HOME' AND cs.is_home_service = 1))
            """
        ),
        {
            "search": search,
            "district": district,
            "course_id": course_id,
            "service_mode": service_mode,
        },
    )
    total = int(count_result.scalar_one() or 0)
    return CoachSearchResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


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


@router.get("/{coach_id}/profile", response_model=CoachProfileResponse)
async def get_coach_profile(
    coach_id: int,
    db: AsyncSession = Depends(get_app_db),
) -> CoachProfileResponse:
    result = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, c.user_id, u.display_name, u.email, u.phone,
                   c.avatar_url, c.coach_level, c.bio, c.service_mode,
                   c.years_experience, c.certifications, c.break_interval, c.status,
                   c.hired_at, AVG(rc.avg_rating) AS average_rating,
                   COUNT(rc.review_coach_id) AS review_count
            FROM coach c
            JOIN users u ON u.user_id = c.user_id
            LEFT JOIN booking b ON b.coach_id = c.coach_id
            LEFT JOIN review_coach rc ON rc.booking_id = b.booking_id
            WHERE c.coach_id = :coach_id AND c.status <> 'RESIGNED'
            GROUP BY c.coach_id, c.coach_no, c.user_id, u.display_name, u.email, u.phone,
                     c.avatar_url, c.coach_level, c.bio, c.service_mode,
                     c.years_experience, c.certifications, c.break_interval,
                     c.status, c.hired_at
            """
        ),
        {"coach_id": coach_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Coach not found")

    courses = await db.execute(
        text(
            """
            SELECT co.course_id, co.course_name, co.description, co.difficulty,
                   co.default_duration, cc.price_per_session
            FROM coach_course cc JOIN course co ON co.course_id = cc.course_id
            WHERE cc.coach_id = :coach_id AND cc.is_active = 1 AND co.is_active = 1
            ORDER BY co.course_name
            """
        ),
        {"coach_id": coach_id},
    )
    gyms = await db.execute(
        text(
            """
            SELECT g.gym_id, g.gym_name, g.address, g.district, g.latitude, g.longitude,
                   cs.is_home_service, cs.service_area
            FROM coach_service cs JOIN gym g ON g.gym_id = cs.gym_id
            WHERE cs.coach_id = :coach_id AND cs.is_active = 1 AND g.is_active = 1
            ORDER BY g.gym_name
            """
        ),
        {"coach_id": coach_id},
    )
    return CoachProfileResponse(
        **dict(row),
        courses=[dict(item) for item in courses.mappings().all()],
        gyms=[dict(item) for item in gyms.mappings().all()],
    )


async def update_my_coach_profile(
    payload: CoachProfileUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> CoachProfileResponse:
    if user["role"] != "COACH":
        raise HTTPException(status_code=403, detail="Coach access required")
    values = payload.model_dump(exclude_unset=True)
    user_values = {
        key: values.pop(key)
        for key in ("display_name", "email", "phone")
        if key in values
    }
    if user_values:
        assignments = ", ".join(f"{key} = :{key}" for key in user_values)
        await db.execute(
            text(f"UPDATE users SET {assignments} WHERE user_id = :user_id"),
            {**user_values, "user_id": user["user_id"]},
        )
    if values:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        await db.execute(
            text(f"UPDATE coach SET {assignments} WHERE user_id = :user_id"),
            {**values, "user_id": user["user_id"]},
        )
    await db.commit()
    result = await db.execute(
        text("SELECT coach_id FROM coach WHERE user_id = :user_id"),
        {"user_id": user["user_id"]},
    )
    coach_id = result.scalar_one_or_none()
    if coach_id is None:
        raise HTTPException(status_code=404, detail="Coach profile not found")
    return await get_coach_profile(coach_id, db)
