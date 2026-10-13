from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_app_db
from app.schemas.features import (
    BookingCancelRequest,
    FitnessProfileUpdate,
    PackagePurchaseRequest,
    PaymentMethodUpdate,
    ProgressDashboardResponse,
    ProgressMetric,
    ReviewCreateRequest,
    WeeklyActivitySlot,
)

router = APIRouter()


async def _member_id(user: dict, db: AsyncSession) -> int:
    if user["role"] != "MEMBER":
        raise HTTPException(status_code=403, detail="Member access required")
    result = await db.execute(
        text("SELECT member_id FROM member WHERE user_id = :user_id"),
        {"user_id": user["user_id"]},
    )
    value = result.scalar_one_or_none()
    if value is None:
        raise HTTPException(status_code=404, detail="Member profile not found")
    return int(value)


@router.get("/bookings", response_model=list[dict])
async def list_my_bookings(
    booking_status: str | None = Query(default=None, alias="status"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT b.booking_id, b.booking_date, b.start_time, b.end_time,
                   b.duration_minutes, b.service_mode, b.service_district,
                   b.service_address, b.price, b.status, b.expires_at,
                   b.cancel_reason, b.created_at, c.coach_id,
                   cu.display_name AS coach_name, co.course_name,
                   g.gym_name
            FROM booking b
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            LEFT JOIN gym g ON g.gym_id = b.gym_id
            WHERE b.member_id = :member_id
              AND (:booking_status IS NULL OR b.status = :booking_status)
            ORDER BY b.booking_date DESC, b.start_time DESC
            """
        ),
        {"member_id": member_id, "booking_status": booking_status},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/bookings/{booking_id}", response_model=dict)
async def get_my_booking(
    booking_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT b.*, cu.display_name AS coach_name, co.course_name, g.gym_name
            FROM booking b
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            LEFT JOIN gym g ON g.gym_id = b.gym_id
            WHERE b.booking_id = :booking_id AND b.member_id = :member_id
            """
        ),
        {"booking_id": booking_id, "member_id": member_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return dict(row)


@router.post("/bookings/{booking_id}/cancel", response_model=dict)
async def cancel_my_booking(
    booking_id: int,
    payload: BookingCancelRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT booking_id, status, booking_date, start_time
            FROM booking
            WHERE booking_id = :booking_id AND member_id = :member_id
            FOR UPDATE
            """
        ),
        {"booking_id": booking_id, "member_id": member_id},
    )
    booking = result.mappings().one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] not in ("PENDING", "CONFIRMED"):
        raise HTTPException(
            status_code=409,
            detail="Only pending or confirmed bookings can be cancelled",
        )
    await db.execute(
        text(
            """
            UPDATE booking
            SET status = 'CANCELLED', cancelled_by = 'MEMBER',
                cancel_reason = :reason, cancelled_at = NOW()
            WHERE booking_id = :booking_id
            """
        ),
        {"reason": payload.reason, "booking_id": booking_id},
    )
    await db.commit()
    return await get_my_booking(booking_id, user, db)


@router.get("/packages", response_model=list[dict])
async def list_my_packages(
    include_inactive: bool = False,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT package_id, package_type, total_sessions, remaining_sessions,
                   price, purchase_date, expire_date, status
            FROM member_package
            WHERE member_id = :member_id
              AND (:include_inactive = 1 OR status = 'ACTIVE')
            ORDER BY purchase_date DESC
            """
        ),
        {"member_id": member_id, "include_inactive": include_inactive},
    )
    return [dict(row) for row in result.mappings().all()]


@router.post("/packages/purchase", response_model=dict, status_code=status.HTTP_201_CREATED)
async def purchase_package(
    payload: PackagePurchaseRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    member_id = await _member_id(user, db)
    packages = {
        "5+1": (6, 3400),
        "10+3": (13, 8970),
        "20+7": (27, 17550),
    }
    total_sessions, price = packages[payload.package_type]
    try:
        result = await db.execute(
            text(
                """
                INSERT INTO member_package
                    (member_id, package_type, total_sessions, remaining_sessions,
                     price, purchase_date, expire_date, status)
                VALUES (:member_id, :package_type, :total_sessions, :remaining_sessions,
                        :price, CURDATE(), DATE_ADD(CURDATE(), INTERVAL 180 DAY), 'ACTIVE')
                """
            ),
            {
                "member_id": member_id,
                "package_type": payload.package_type,
                "total_sessions": total_sessions,
                "remaining_sessions": total_sessions,
                "price": price,
            },
        )
        package_id = result.lastrowid
        await db.execute(
            text(
                """
                INSERT INTO orders
                    (order_type, package_id, total_amount, discount, final_amount,
                     payment_method, payment_status)
                VALUES ('PACKAGE', :package_id, :price, 0, :price, :payment_method, 'UNPAID')
                """
            ),
            {"package_id": package_id, "price": price, "payment_method": payload.payment_method},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Unable to create package order") from None
    result = await db.execute(
        text("SELECT * FROM member_package WHERE package_id = :package_id"),
        {"package_id": package_id},
    )
    return dict(result.mappings().one())


@router.get("/reviews", response_model=list[dict])
async def list_my_reviews(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT rc.review_coach_id, rc.booking_id, rc.avg_rating, rc.comment,
                   rc.created_at, cu.display_name AS coach_name, co.course_name
            FROM review_coach rc
            JOIN booking b ON b.booking_id = rc.booking_id
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            WHERE rc.reviewer_id = :member_id
            ORDER BY rc.created_at DESC
            """
        ),
        {"member_id": member_id},
    )
    return [dict(row) for row in result.mappings().all()]


@router.post("/reviews", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_review(
    payload: ReviewCreateRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    member_id = await _member_id(user, db)
    try:
        result = await db.execute(
            text(
                """
                INSERT INTO review_coach
                    (booking_id, reviewer_id, rating_professional,
                     rating_communication, rating_punctuality,
                     rating_effectiveness, comment)
                VALUES (:booking_id, :member_id, :professional, :communication,
                        :punctuality, :effectiveness, :comment)
                """
            ),
            {
                "booking_id": payload.booking_id,
                "member_id": member_id,
                "professional": payload.rating_professional,
                "communication": payload.rating_communication,
                "punctuality": payload.rating_punctuality,
                "effectiveness": payload.rating_effectiveness,
                "comment": payload.comment,
            },
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The booking is not reviewable or already has a review",
        ) from None
    result = await db.execute(
        text("SELECT * FROM review_coach WHERE review_coach_id = :review_id"),
        {"review_id": result.lastrowid},
    )
    return dict(result.mappings().one())


@router.get("/progress", response_model=ProgressDashboardResponse)
async def get_progress(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> ProgressDashboardResponse:
    member_id = await _member_id(user, db)
    profile = await db.execute(
        text(
            """
            SELECT m.weight_kg, m.height_cm, fp.updated_at
            FROM member m
            LEFT JOIN fitness_profile fp ON fp.member_id = m.member_id
            WHERE m.member_id = :member_id
            """
        ),
        {"member_id": member_id},
    )
    week_start = date.today() - timedelta(days=date.today().weekday())
    activity = await db.execute(
        text(
            """
            SELECT b.booking_date, b.start_time, b.end_time, b.duration_minutes,
                   cu.display_name AS coach_name, co.course_name, status
            FROM booking b
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            WHERE b.member_id = :member_id
              AND b.booking_date BETWEEN :week_start
                  AND DATE_ADD(:week_start, INTERVAL 6 DAY)
              AND b.status = 'COMPLETED'
            ORDER BY b.booking_date, b.start_time
            """
        ),
        {"member_id": member_id, "week_start": week_start},
    )
    profile_row = dict(profile.mappings().one_or_none() or {})
    weight = profile_row.get("weight_kg")
    height = profile_row.get("height_cm")
    bmi = None
    if weight and height:
        bmi = round(float(weight) / (float(height) / 100) ** 2, 1)
    bmi_category = (
        None
        if bmi is None
        else "Underweight" if bmi < 18.5
        else "Healthy range" if bmi < 25
        else "Overweight" if bmi < 30
        else "Obesity"
    )
    slots = [
        WeeklyActivitySlot(
            date=row["booking_date"].isoformat(),
            day=row["booking_date"].strftime("%a"),
            start_time=str(row["start_time"]),
            end_time=str(row["end_time"]),
            title=row["course_name"],
            coach_name=row["coach_name"],
            status=row["status"],
            duration_minutes=row["duration_minutes"],
        )
        for row in activity.mappings().all()
    ]
    return ProgressDashboardResponse(
        updated_at=profile_row.get("updated_at").isoformat()
        if profile_row.get("updated_at")
        else None,
        baseline={
            "weight": ProgressMetric(value=weight, unit="kg"),
            "body_fat": ProgressMetric(value=None, unit="%"),
            "bmi": ProgressMetric(value=bmi, unit="kg/m2", category=bmi_category),
        },
        weekly_activity=slots,
        completed_sessions=len(slots),
    )


@router.put("/progress", response_model=dict)
async def update_progress(
    payload: FitnessProfileUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    member_id = await _member_id(user, db)
    values = payload.model_dump()
    await db.execute(
        text(
            """
            INSERT INTO fitness_profile
                (member_id, strongest_area, weakest_area, strongest_score, weakest_score)
            VALUES (:member_id, :strongest_area, :weakest_area,
                    :strongest_score, :weakest_score)
            ON DUPLICATE KEY UPDATE
                strongest_area = VALUES(strongest_area),
                weakest_area = VALUES(weakest_area),
                strongest_score = VALUES(strongest_score),
                weakest_score = VALUES(weakest_score)
            """
        ),
        {"member_id": member_id, **values},
    )
    await db.commit()
    return await get_progress(user, db)


@router.get("/payment-history", response_model=list[dict])
async def payment_history(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT o.order_id, o.order_type, o.total_amount, o.discount,
                   o.final_amount, o.payment_method, o.payment_status,
                   o.payment_time, o.created_at
            FROM orders o
            LEFT JOIN booking b ON b.booking_id = o.booking_id
            LEFT JOIN member_package mp ON mp.package_id = o.package_id
            WHERE b.member_id = :member_id OR mp.member_id = :member_id
            ORDER BY o.created_at DESC
            """
        ),
        {"member_id": member_id},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/payment-methods", response_model=list[dict])
async def payment_methods(user: dict = Depends(get_current_user)) -> list[dict]:
    if user["role"] != "MEMBER":
        raise HTTPException(status_code=403, detail="Member access required")
    return []


@router.post("/payment-methods", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_payment_method(
    payload: PaymentMethodUpdate,
    user: dict = Depends(get_current_user),
) -> dict:
    if user["role"] != "MEMBER":
        raise HTTPException(status_code=403, detail="Member access required")
    raise HTTPException(
        status_code=501,
        detail="Payment methods require a payment-provider integration",
    )
