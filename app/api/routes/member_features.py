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
    MessageCreateRequest,
    MessageResponse,
    PackagePurchaseRequest,
    PaymentMethodResponse,
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
    bookings = []
    for row in result.mappings().all():
        d = dict(row)
        if "start_time" in d and d["start_time"] is not None:
            d["start_time"] = _format_time_value(d["start_time"])
        if "end_time" in d and d["end_time"] is not None:
            d["end_time"] = _format_time_value(d["end_time"])
        bookings.append(d)
    return bookings


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
    d = dict(row)
    if "start_time" in d and d["start_time"] is not None:
        d["start_time"] = _format_time_value(d["start_time"])
    if "end_time" in d and d["end_time"] is not None:
        d["end_time"] = _format_time_value(d["end_time"])
    return d


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
    catalog_result = await db.execute(
        text(
            """
            SELECT paid_sessions, bonus_sessions, price, validity_days
            FROM package_catalog
            WHERE package_type = :package_type AND is_active = 1
            """
        ),
        {"package_type": payload.package_type},
    )
    catalog = catalog_result.mappings().one_or_none()
    if catalog is None:
        raise HTTPException(status_code=404, detail="Package offer not found")
    total_sessions = int(catalog["paid_sessions"] + catalog["bonus_sessions"])
    price = catalog["price"]
    expire_date = date.today() + timedelta(days=int(catalog["validity_days"]))
    try:
        result = await db.execute(
            text(
                """
                INSERT INTO member_package
                    (member_id, package_type, total_sessions, remaining_sessions,
                     price, purchase_date, expire_date, status)
                VALUES (:member_id, :package_type, :total_sessions, :remaining_sessions,
                         :price, CURDATE(), :expire_date, 'ACTIVE')
                """
            ),
            {
                "member_id": member_id,
                "package_type": payload.package_type,
                "total_sessions": total_sessions,
                "remaining_sessions": total_sessions,
                "price": price,
                "expire_date": expire_date,
            },
        )
        package_id = result.lastrowid
        order_res = await db.execute(
            text(
                """
                INSERT INTO orders
                    (order_type, package_id, total_amount, discount, final_amount,
                     payment_method, payment_status, payment_time)
                VALUES ('PACKAGE', :package_id, :price, 0, :price, :payment_method, 'PAID', NOW())
                """
            ),
            {"package_id": package_id, "price": price, "payment_method": payload.payment_method},
        )
        order_id = order_res.lastrowid
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Unable to create package order") from None
    result = await db.execute(
        text("SELECT * FROM member_package WHERE package_id = :package_id"),
        {"package_id": package_id},
    )
    res_dict = dict(result.mappings().one())
    res_dict["order_id"] = order_id
    res_dict["total_amount"] = str(price)
    res_dict["payment_method"] = payload.payment_method
    res_dict["payment_status"] = "PAID"
    return res_dict


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
    # Auto-complete past confirmed booking if it has already ended
    await db.execute(
        text(
            """
            UPDATE booking
            SET status = 'COMPLETED', completed_at = NOW()
            WHERE booking_id = :booking_id
              AND member_id = :member_id
              AND status = 'CONFIRMED'
              AND TIMESTAMP(booking_date, end_time) <= NOW()
            """
        ),
        {"booking_id": payload.booking_id, "member_id": member_id},
    )
    await db.commit()
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
        review_id = result.lastrowid

        # Auto-recalculate coach average rating and coach_kpi_record
        booking_info = await db.execute(
            text("SELECT coach_id FROM booking WHERE booking_id = :bid"),
            {"bid": payload.booking_id},
        )
        target_coach_id = booking_info.scalar_one_or_none()
        if target_coach_id is not None:
            await db.execute(
                text(
                    """
                    UPDATE coach
                    SET average_rating = (
                        SELECT ROUND(AVG((rc.rating_professional + rc.rating_communication + rc.rating_punctuality + rc.rating_effectiveness) / 4.0), 2)
                        FROM review_coach rc
                        JOIN booking b ON b.booking_id = rc.booking_id
                        WHERE b.coach_id = :cid
                    )
                    WHERE coach_id = :cid
                    """
                ),
                {"cid": target_coach_id},
            )
            # Update current month KPI
            today = date.today()
            avg_res = await db.execute(
                text(
                    """
                    SELECT ROUND(AVG((rc.rating_professional + rc.rating_communication + rc.rating_punctuality + rc.rating_effectiveness) / 4.0), 2)
                    FROM review_coach rc
                    JOIN booking b ON b.booking_id = rc.booking_id
                    WHERE b.coach_id = :cid
                      AND YEAR(rc.created_at) = :yr AND MONTH(rc.created_at) = :mo
                    """
                ),
                {"cid": target_coach_id, "yr": today.year, "mo": today.month},
            )
            m_avg = avg_res.scalar_one_or_none()
            if m_avg is not None:
                await db.execute(
                    text(
                        """
                        UPDATE coach_kpi_record
                        SET avg_rating = :avg_rating,
                            is_achieved = CASE
                                WHEN total_hours >= target_hours
                                 AND :avg_rating >= target_avg_rating
                                 AND (retention_rate IS NULL OR retention_rate >= target_retention_rate)
                                THEN 1 ELSE 0
                            END,
                            calculated_at = NOW()
                        WHERE coach_id = :cid AND kpi_year = :yr AND kpi_month = :mo
                        """
                    ),
                    {"cid": target_coach_id, "yr": today.year, "mo": today.month, "avg_rating": m_avg},
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
        {"review_id": review_id},
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
            SELECT m.height_cm, m.weight_kg AS member_weight_kg, fp.updated_at,
                   latest_measurement.weight_kg,
                   latest_measurement.body_fat_percent,
                   previous_measurement.weight_kg AS previous_weight_kg
            FROM member m
            LEFT JOIN fitness_profile fp ON fp.member_id = m.member_id
            LEFT JOIN member_body_measurement latest_measurement
                ON latest_measurement.measurement_id = (
                    SELECT latest.measurement_id
                    FROM member_body_measurement latest
                    WHERE latest.member_id = m.member_id
                    ORDER BY latest.measured_at DESC, latest.measurement_id DESC
                    LIMIT 1
                )
            LEFT JOIN member_body_measurement previous_measurement
                ON previous_measurement.measurement_id = (
                    SELECT older.measurement_id
                    FROM member_body_measurement older
                    WHERE older.member_id = m.member_id
                    ORDER BY older.measured_at DESC, older.measurement_id DESC
                    LIMIT 1 OFFSET 1
                )
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
    if weight is None:
        weight = profile_row.get("member_weight_kg")
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
            start_time=_format_time_value(row["start_time"]),
            end_time=_format_time_value(row["end_time"]),
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
            "weight": ProgressMetric(
                value=weight,
                unit="kg",
                delta=(
                    round(float(weight) - float(profile_row["previous_weight_kg"]), 1)
                    if weight is not None and profile_row.get("previous_weight_kg") is not None
                    else None
                ),
            ),
            "body_fat": ProgressMetric(
                value=profile_row.get("body_fat_percent"),
                unit="%",
            ),
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
    values = payload.model_dump(exclude_none=True)
    measurement_values = {
        key: values.pop(key)
        for key in ("weight_kg", "body_fat_percent")
        if key in values
    }
    if measurement_values:
        await db.execute(
            text(
                """
                INSERT INTO member_body_measurement
                    (member_id, weight_kg, body_fat_percent)
                VALUES (:member_id, :weight_kg, :body_fat_percent)
                """
            ),
            {
                "member_id": member_id,
                "weight_kg": measurement_values.get("weight_kg"),
                "body_fat_percent": measurement_values.get("body_fat_percent"),
            },
        )
        await db.execute(
            text(
                "UPDATE member SET weight_kg = :weight_kg WHERE member_id = :member_id"
            ),
            {"weight_kg": measurement_values["weight_kg"], "member_id": member_id},
        )
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


@router.get("/payment-methods", response_model=list[PaymentMethodResponse])
async def payment_methods(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT payment_method_id, method_type, label, last_four,
                   is_default, status, created_at
            FROM member_payment_method
            WHERE member_id = :member_id AND status = 'ACTIVE'
            ORDER BY is_default DESC, created_at DESC
            """
        ),
        {"member_id": member_id},
    )
    return [
        PaymentMethodResponse.model_validate(dict(row)).model_dump()
        for row in result.mappings().all()
    ]


@router.post(
    "/payment-methods",
    response_model=PaymentMethodResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_payment_method(
    payload: PaymentMethodUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    member_id = await _member_id(user, db)
    if payload.payment_method == "CARD" and not payload.provider_token:
        raise HTTPException(status_code=400, detail="Card provider token is required")
    try:
        if payload.is_default:
            await db.execute(
                text(
                    """
                    UPDATE member_payment_method
                    SET is_default = 0
                    WHERE member_id = :member_id AND status = 'ACTIVE'
                    """
                ),
                {"member_id": member_id},
            )
        result = await db.execute(
            text(
                """
                INSERT INTO member_payment_method
                    (member_id, method_type, label, provider_token, last_four, is_default)
                VALUES
                    (:member_id, :method_type, :label, :provider_token, :last_four, :is_default)
                """
            ),
            {
                "member_id": member_id,
                "method_type": payload.payment_method,
                "label": payload.label,
                "provider_token": payload.provider_token,
                "last_four": payload.last_four,
                "is_default": payload.is_default,
            },
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Payment method already exists") from None
    result = await db.execute(
        text(
            """
            SELECT payment_method_id, method_type, label, last_four,
                   is_default, status, created_at
            FROM member_payment_method WHERE payment_method_id = :payment_method_id
            """
        ),
        {"payment_method_id": result.lastrowid},
    )
    return PaymentMethodResponse.model_validate(dict(result.mappings().one()))


@router.delete("/payment-methods/{payment_method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_payment_method(
    payment_method_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> None:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            UPDATE member_payment_method
            SET status = 'REMOVED', is_default = 0
            WHERE payment_method_id = :payment_method_id
              AND member_id = :member_id AND status = 'ACTIVE'
            """
        ),
        {"payment_method_id": payment_method_id, "member_id": member_id},
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Payment method not found")
    await db.commit()


@router.get("/messages", response_model=list[MessageResponse])
async def list_messages(
    coach_id: int | None = Query(default=None, gt=0),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[MessageResponse]:
    member_id = await _member_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT mm.message_id, mm.coach_id, cu.display_name AS coach_name,
                   mm.sender_role, mm.message_text, mm.read_at, mm.created_at
            FROM member_message mm
            JOIN coach c ON c.coach_id = mm.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            WHERE mm.member_id = :member_id
              AND (:coach_id IS NULL OR mm.coach_id = :coach_id)
            ORDER BY mm.created_at
            """
        ),
        {"member_id": member_id, "coach_id": coach_id},
    )
    return [MessageResponse.model_validate(dict(row)) for row in result.mappings().all()]


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreateRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> MessageResponse:
    member_id = await _member_id(user, db)
    coach_result = await db.execute(
        text(
            """
            SELECT c.coach_id, u.display_name
            FROM coach c JOIN users u ON u.user_id = c.user_id
            WHERE c.coach_id = :coach_id AND c.status = 'ACTIVE'
            """
        ),
        {"coach_id": payload.coach_id},
    )
    coach = coach_result.mappings().one_or_none()
    if coach is None:
        raise HTTPException(status_code=404, detail="Coach not found")
    result = await db.execute(
        text(
            """
            INSERT INTO member_message (member_id, coach_id, sender_role, message_text)
            VALUES (:member_id, :coach_id, 'MEMBER', :message_text)
            """
        ),
        {
            "member_id": member_id,
            "coach_id": payload.coach_id,
            "message_text": payload.message_text,
        },
    )
    await db.commit()
    created = await db.execute(
        text(
            """
            SELECT mm.message_id, mm.coach_id, cu.display_name AS coach_name,
                   mm.sender_role, mm.message_text, mm.read_at, mm.created_at
            FROM member_message mm
            JOIN coach c ON c.coach_id = mm.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            WHERE mm.message_id = :message_id
            """
        ),
        {"message_id": result.lastrowid},
    )
    return MessageResponse.model_validate(dict(created.mappings().one()))
