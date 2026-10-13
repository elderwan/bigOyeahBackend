from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_app_db
from app.schemas.auth import MemberDashboardResponse, MemberProfileResponse, MemberProfileUpdate

router = APIRouter()


async def _get_member_profile(db: AsyncSession, user_id: int) -> dict:
    result = await db.execute(
        text(
            """
            SELECT m.member_id, m.user_id, u.username, u.display_name, u.email, u.phone,
                   m.level_id, ml.level_code, ml.level_name,
                   ml.discount_rate, m.total_spend, m.gender, m.birth_date,
                   m.height_cm, m.weight_kg, m.fitness_goal
            FROM member m
            JOIN users u ON u.user_id = m.user_id
            JOIN membership_level ml ON ml.level_id = m.level_id
            WHERE m.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    profile = result.mappings().one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Member profile not found")
    return dict(profile)


@router.get("/me", response_model=MemberProfileResponse)
async def get_member_profile(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> MemberProfileResponse:
    if user["role"] != "MEMBER":
        raise HTTPException(status_code=403, detail="Member access required")
    return MemberProfileResponse.model_validate(await _get_member_profile(db, user["user_id"]))


@router.patch("/me", response_model=MemberProfileResponse)
async def update_member_profile(
    payload: MemberProfileUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> MemberProfileResponse:
    if user["role"] != "MEMBER":
        raise HTTPException(status_code=403, detail="Member access required")
    values = payload.model_dump(exclude_unset=True)
    user_values = {
        key: values.pop(key)
        for key in ("display_name", "email", "phone")
        if key in values
    }
    try:
        if user_values:
            assignments = ", ".join(f"{key} = :{key}" for key in user_values)
            await db.execute(
                text(f"UPDATE users SET {assignments} WHERE user_id = :user_id"),
                {**user_values, "user_id": user["user_id"]},
            )
        if values:
            assignments = ", ".join(f"{key} = :{key}" for key in values)
            await db.execute(
                text(f"UPDATE member SET {assignments} WHERE user_id = :user_id"),
                {**values, "user_id": user["user_id"]},
            )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email or phone is already registered",
        ) from None
    return MemberProfileResponse.model_validate(await _get_member_profile(db, user["user_id"]))


@router.get("/me/dashboard", response_model=MemberDashboardResponse)
async def get_member_dashboard(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> MemberDashboardResponse:
    if user["role"] != "MEMBER":
        raise HTTPException(status_code=403, detail="Member access required")
    profile = await _get_member_profile(db, user["user_id"])
    member_id = profile["member_id"]
    bookings = await db.execute(
        text(
            """
            SELECT b.booking_id, b.booking_date, b.start_time, b.end_time, b.status,
                   b.price, c.coach_id, u.display_name AS coach_name, co.course_name
            FROM booking b
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users u ON u.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            WHERE b.member_id = :member_id
              AND b.status IN ('PENDING', 'CONFIRMED')
            ORDER BY b.booking_date, b.start_time
            LIMIT 10
            """
        ),
        {"member_id": member_id},
    )
    packages = await db.execute(
        text(
            """
            SELECT package_id, package_type, total_sessions, remaining_sessions,
                   price, purchase_date, expire_date, status
            FROM member_package
            WHERE member_id = :member_id AND status = 'ACTIVE'
            ORDER BY expire_date
            """
        ),
        {"member_id": member_id},
    )
    return MemberDashboardResponse(
        profile=MemberProfileResponse.model_validate(profile),
        upcoming_bookings=[dict(row) for row in bookings.mappings().all()],
        active_packages=[dict(row) for row in packages.mappings().all()],
    )
