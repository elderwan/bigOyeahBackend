from datetime import date, timedelta
from decimal import Decimal

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
                   m.height_cm, m.weight_kg, m.fitness_goal,
                   nxt.level_code AS next_tier_code,
                   nxt.level_name AS next_tier_name,
                   nxt.min_total_spend AS next_tier_threshold
            FROM member m
            JOIN users u ON u.user_id = m.user_id
            JOIN membership_level ml ON ml.level_id = m.level_id
            LEFT JOIN membership_level nxt ON nxt.level_id = (
                SELECT nl.level_id
                FROM membership_level nl
                WHERE nl.min_total_spend > m.total_spend
                ORDER BY nl.min_total_spend ASC, nl.sort_order ASC
                LIMIT 1
            )
            WHERE m.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    profile = result.mappings().one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Member profile not found")
    d = dict(profile)
    threshold = d.get("next_tier_threshold")
    total_spend = Decimal(str(d.get("total_spend") or 0))
    if threshold is not None:
        threshold_dec = Decimal(str(threshold))
        d["amount_to_next_tier"] = max(Decimal("0.00"), threshold_dec - total_spend)
    else:
        d["amount_to_next_tier"] = Decimal("0.00")
    return d


def _format_time_value(v) -> str:
    if hasattr(v, "total_seconds"):
        ts = int(v.total_seconds())
        hours = ts // 3600
        minutes = (ts % 3600) // 60
        seconds = ts % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M:%S")
    return str(v) if v is not None else ""


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
    next_session = await db.execute(
        text(
            """
            SELECT b.booking_id, b.booking_date, b.start_time, b.end_time,
                   b.duration_minutes, b.service_mode, b.price,
                   cu.display_name AS coach_name, co.course_name,
                   g.gym_name, g.district
            FROM booking b
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            LEFT JOIN gym g ON g.gym_id = b.gym_id
            WHERE b.member_id = :member_id
              AND b.status IN ('PENDING', 'CONFIRMED')
              AND TIMESTAMP(b.booking_date, b.start_time) >= NOW()
            ORDER BY b.booking_date, b.start_time
            LIMIT 1
            """
        ),
        {"member_id": member_id},
    )
    week_start = date.today() - timedelta(days=date.today().weekday())
    weekly = await db.execute(
        text(
            """
            SELECT COUNT(*) AS workouts_done,
                   COALESCE(SUM(duration_minutes), 0) AS active_minutes,
                   COALESCE(SUM(duration_minutes * 8), 0) AS calories_burned
            FROM booking
            WHERE member_id = :member_id
              AND status = 'COMPLETED'
              AND booking_date BETWEEN :week_start AND DATE_ADD(:week_start, INTERVAL 6 DAY)
            """
        ),
        {"member_id": member_id, "week_start": week_start},
    )
    recommended = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, u.display_name, c.avatar_url,
                   c.coach_level, c.bio, c.service_mode, c.years_experience,
                   COALESCE(AVG(rc.avg_rating), 0) AS average_rating,
                   COUNT(rc.review_coach_id) AS review_count,
                   MIN(cc.price_per_session) AS price_per_session
            FROM coach c
            JOIN users u ON u.user_id = c.user_id AND u.status = 'ACTIVE'
            LEFT JOIN booking rb ON rb.coach_id = c.coach_id
            LEFT JOIN review_coach rc ON rc.booking_id = rb.booking_id
            LEFT JOIN coach_course cc ON cc.coach_id = c.coach_id AND cc.is_active = 1
            WHERE c.status = 'ACTIVE'
            GROUP BY c.coach_id, c.coach_no, u.display_name, c.avatar_url,
                     c.coach_level, c.bio, c.service_mode, c.years_experience
            ORDER BY average_rating DESC, review_count DESC
            LIMIT 3
            """
        )
    )
    weekly_row = dict(weekly.mappings().one())
    workouts_done = int(weekly_row["workouts_done"])
    weekly_goal = 4

    next_session_dict = dict(next_session.mappings().one_or_none() or {})
    if next_session_dict:
        if "start_time" in next_session_dict:
            next_session_dict["start_time"] = _format_time_value(next_session_dict["start_time"])
        if "end_time" in next_session_dict:
            next_session_dict["end_time"] = _format_time_value(next_session_dict["end_time"])
    else:
        next_session_dict = None

    upcoming_list = []
    for row in bookings.mappings().all():
        d = dict(row)
        if "start_time" in d:
            d["start_time"] = _format_time_value(d["start_time"])
        if "end_time" in d:
            d["end_time"] = _format_time_value(d["end_time"])
        upcoming_list.append(d)

    return MemberDashboardResponse(
        profile=MemberProfileResponse.model_validate(profile),
        weekly_summary={
            "workouts_done": workouts_done,
            "workout_goal": weekly_goal,
            "goal_percentage": min(100, round(workouts_done / weekly_goal * 100)),
            "calories_burned": int(weekly_row["calories_burned"]),
            "active_minutes": int(weekly_row["active_minutes"]),
            "streak_days": 0,
        },
        next_session=next_session_dict,
        recommended_coaches=[dict(row) for row in recommended.mappings().all()],
        upcoming_bookings=upcoming_list,
        active_packages=[dict(row) for row in packages.mappings().all()],
    )
