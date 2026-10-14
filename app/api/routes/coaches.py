from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_app_db
from app.schemas.coach import (
    CoachConversationSummary,
    CoachListItem,
    CoachMemberReviewRequest,
    CoachMessageCreateRequest,
    CoachProfileResponse,
    CoachProfileUpdate,
    CoachScheduleBlockRequest,
    CoachScheduleUnblockRequest,
    CoachSearchResponse,
)
from app.schemas.coaches import CoachSummary
from app.schemas.features import MessageResponse
from app.services.schedule_service import ScheduleService

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


async def _coach_id(user: dict, db: AsyncSession) -> int:
    if user["role"] != "COACH":
        raise HTTPException(status_code=403, detail="Coach access required")
    result = await db.execute(
        text("SELECT coach_id FROM coach WHERE user_id = :user_id"),
        {"user_id": user["user_id"]},
    )
    coach_id = result.scalar_one_or_none()
    if coach_id is None:
        raise HTTPException(status_code=404, detail="Coach profile not found")
    return int(coach_id)


@router.get("/me/messages", response_model=list[MessageResponse])
async def list_coach_messages(
    member_id: int | None = Query(default=None, gt=0),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[MessageResponse]:
    coach_id = await _coach_id(user, db)
    # Mark incoming unread member messages as read
    if member_id is not None:
        await db.execute(
            text(
                """
                UPDATE member_message
                SET read_at = NOW()
                WHERE coach_id = :coach_id AND member_id = :member_id
                  AND sender_role = 'MEMBER' AND read_at IS NULL
                """
            ),
            {"coach_id": coach_id, "member_id": member_id},
        )
        await db.commit()
    result = await db.execute(
        text(
            """
            SELECT mm.message_id, mm.coach_id, mm.member_id,
                   cu.display_name AS coach_name,
                   mu.display_name AS member_name,
                   mm.sender_role, mm.message_text, mm.read_at, mm.created_at
            FROM member_message mm
            JOIN coach c ON c.coach_id = mm.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN member m ON m.member_id = mm.member_id
            JOIN users mu ON mu.user_id = m.user_id
            WHERE mm.coach_id = :coach_id
              AND (:member_id IS NULL OR mm.member_id = :member_id)
            ORDER BY mm.created_at
            """
        ),
        {"coach_id": coach_id, "member_id": member_id},
    )
    return [MessageResponse.model_validate(dict(row)) for row in result.mappings().all()]


@router.post("/me/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_coach_message(
    payload: CoachMessageCreateRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> MessageResponse:
    coach_id = await _coach_id(user, db)
    member_result = await db.execute(
        text(
            """
            SELECT m.member_id
            FROM member m JOIN users u ON u.user_id = m.user_id
            WHERE m.member_id = :member_id AND u.status = 'ACTIVE'
            """
        ),
        {"member_id": payload.member_id},
    )
    if member_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Member not found")

    res = await db.execute(
        text(
            """
            INSERT INTO member_message (member_id, coach_id, sender_role, message_text)
            VALUES (:member_id, :coach_id, 'COACH', :message_text)
            """
        ),
        {
            "member_id": payload.member_id,
            "coach_id": coach_id,
            "message_text": payload.message_text,
        },
    )
    message_id = res.lastrowid
    await db.commit()

    created = await db.execute(
        text(
            """
            SELECT mm.message_id, mm.coach_id, mm.member_id,
                   cu.display_name AS coach_name,
                   mu.display_name AS member_name,
                   mm.sender_role, mm.message_text, mm.read_at, mm.created_at
            FROM member_message mm
            JOIN coach c ON c.coach_id = mm.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN member m ON m.member_id = mm.member_id
            JOIN users mu ON mu.user_id = m.user_id
            WHERE mm.message_id = :message_id
            """
        ),
        {"message_id": message_id},
    )
    return MessageResponse.model_validate(dict(created.mappings().one()))


@router.post("/me/member-reviews", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_member_review(
    payload: CoachMemberReviewRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    coach_id = await _coach_id(user, db)
    booking_res = await db.execute(
        text(
            """
            SELECT booking_id, coach_id, member_id, status
            FROM booking
            WHERE booking_id = :booking_id
            """
        ),
        {"booking_id": payload.booking_id},
    )
    booking = booking_res.mappings().one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["coach_id"] != coach_id:
        raise HTTPException(status_code=403, detail="Cannot review a booking assigned to another coach")
    if booking["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Cannot review an incomplete booking")

    existing = await db.execute(
        text("SELECT review_member_id FROM review_member WHERE booking_id = :bid"),
        {"bid": payload.booking_id},
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A review for this booking already exists")

    try:
        ins = await db.execute(
            text(
                """
                INSERT INTO review_member
                    (booking_id, coach_id, member_id, completion_score,
                     proficiency_score, training_area, training_type, coach_note)
                VALUES
                    (:booking_id, :coach_id, :member_id, :completion_score,
                     :proficiency_score, :training_area, :training_type, :coach_note)
                """
            ),
            {
                "booking_id": payload.booking_id,
                "coach_id": coach_id,
                "member_id": booking["member_id"],
                "completion_score": payload.completion_score,
                "proficiency_score": payload.proficiency_score,
                "training_area": payload.training_area,
                "training_type": payload.training_type,
                "coach_note": payload.coach_note,
            },
        )
        review_id = ins.lastrowid

        # Update fitness_profile for member
        area_stats = await db.execute(
            text(
                """
                SELECT training_area,
                       AVG((completion_score + proficiency_score) / 2.0) AS avg_score,
                       COUNT(*) AS cnt
                FROM review_member
                WHERE member_id = :member_id
                GROUP BY training_area
                ORDER BY avg_score DESC
                """
            ),
            {"member_id": booking["member_id"]},
        )
        stats = area_stats.mappings().all()
        if stats:
            strongest = stats[0]
            weakest = stats[-1]
            total_reviews = sum(s["cnt"] for s in stats)
            await db.execute(
                text(
                    """
                    INSERT INTO fitness_profile
                        (member_id, strongest_area, weakest_area, strongest_score, weakest_score, review_count, updated_at)
                    VALUES
                        (:mid, :s_area, :w_area, :s_score, :w_score, :cnt, NOW())
                    ON DUPLICATE KEY UPDATE
                        strongest_area = VALUES(strongest_area),
                        weakest_area = VALUES(weakest_area),
                        strongest_score = VALUES(strongest_score),
                        weakest_score = VALUES(weakest_score),
                        review_count = VALUES(review_count),
                        updated_at = NOW()
                    """
                ),
                {
                    "mid": booking["member_id"],
                    "s_area": strongest["training_area"],
                    "w_area": weakest["training_area"],
                    "s_score": strongest["avg_score"],
                    "w_score": weakest["avg_score"],
                    "cnt": total_reviews,
                },
            )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A review for this booking already exists")
    except Exception:
        await db.rollback()
        raise

    review = await db.execute(
        text("SELECT * FROM review_member WHERE review_member_id = :rid"),
        {"rid": review_id},
    )
    return dict(review.mappings().one())


@router.get("/me/member-reviews", response_model=list[dict])
async def list_my_member_reviews(
    booking_id: int | None = Query(default=None, gt=0),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    coach_id = await _coach_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT rm.*, u.display_name AS member_name, co.course_name
            FROM review_member rm
            JOIN member m ON m.member_id = rm.member_id
            JOIN users u ON u.user_id = m.user_id
            JOIN booking b ON b.booking_id = rm.booking_id
            JOIN course co ON co.course_id = b.course_id
            WHERE rm.coach_id = :coach_id
              AND (:booking_id IS NULL OR rm.booking_id = :booking_id)
            ORDER BY rm.created_at DESC
            """
        ),
        {"coach_id": coach_id, "booking_id": booking_id},
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/me/conversations", response_model=list[CoachConversationSummary])
async def list_coach_conversations(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> list[CoachConversationSummary]:
    coach_id = await _coach_id(user, db)
    result = await db.execute(
        text(
            """
            SELECT m.member_id,
                   u.display_name AS member_name,
                   NULL AS avatar_url,
                   latest.message_text AS last_message,
                   latest.created_at AS last_message_time,
                   COALESCE(unread.cnt, 0) AS unread_count
            FROM (
                SELECT DISTINCT member_id
                FROM member_message
                WHERE coach_id = :coach_id
            ) active_members
            JOIN member m ON m.member_id = active_members.member_id
            JOIN users u ON u.user_id = m.user_id
            JOIN member_message latest ON latest.message_id = (
                SELECT lm.message_id
                FROM member_message lm
                WHERE lm.coach_id = :coach_id AND lm.member_id = active_members.member_id
                ORDER BY lm.created_at DESC, lm.message_id DESC
                LIMIT 1
            )
            LEFT JOIN (
                SELECT member_id, COUNT(*) AS cnt
                FROM member_message
                WHERE coach_id = :coach_id AND sender_role = 'MEMBER' AND read_at IS NULL
                GROUP BY member_id
            ) unread ON unread.member_id = active_members.member_id
            ORDER BY latest.created_at DESC
            """
        ),
        {"coach_id": coach_id},
    )
    return [CoachConversationSummary.model_validate(dict(row)) for row in result.mappings().all()]


@router.post("/me/schedule/block", response_model=dict)
async def block_schedule_slots(
    payload: CoachScheduleBlockRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    coach_id = await _coach_id(user, db)
    target_date = payload.block_date or payload.date
    if target_date is None:
        raise HTTPException(status_code=422, detail="date or block_date is required")
    reason = payload.reason or "Personal leave"

    # Parse times
    try:
        sp = payload.start_time.split(":")
        sh, sm = int(sp[0]), int(sp[1])
        ep = payload.end_time.split(":")
        eh, em = int(ep[0]), int(ep[1])
        stime = time(hour=sh, minute=sm)
        etime = time(hour=eh, minute=em)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid time format (HH:MM required)")

    if sm % 10 != 0 or em % 10 != 0:
        raise HTTPException(status_code=422, detail="start_time and end_time minute must align to a 10-minute grid")
    if etime <= stime:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    table_name = await ScheduleService(db).get_table_name(coach_id)
    start_dt = datetime.combine(target_date, stime)
    end_dt = datetime.combine(target_date, etime)

    # Check for any already BOOKED slots in interval
    booked_check = await db.execute(
        text(
            f"""
            SELECT slot_start, status, booking_id
            FROM `{table_name}`
            WHERE slot_start >= :sdt AND slot_start < :edt AND status = 'BOOKED'
            LIMIT 1
            """
        ),
        {"sdt": start_dt, "edt": end_dt},
    )
    first_conflict = booked_check.mappings().first()
    if first_conflict is not None:
        b_id = first_conflict.get("booking_id")
        conflict_msg = (
            f"该时间段已有学员预约（预约号 #{b_id}），无法直接锁定。请先与学员沟通协调退改。"
            if b_id
            else "该时间段已有学员预约，无法直接锁定。请先与学员沟通协调退改。"
        )
        raise HTTPException(status_code=409, detail=conflict_msg)

    # Also check booking table directly for active bookings
    booking_conflict = await db.execute(
        text(
            """
            SELECT booking_id
            FROM booking
            WHERE coach_id = :coach_id
              AND booking_date = :bdate
              AND status IN ('CONFIRMED', 'PENDING')
              AND start_time < :etime
              AND end_time > :stime
            LIMIT 1
            """
        ),
        {
            "coach_id": coach_id,
            "bdate": target_date,
            "stime": stime,
            "etime": etime,
        },
    )
    b_row = booking_conflict.mappings().first()
    if b_row is not None:
        b_id = b_row["booking_id"]
        raise HTTPException(
            status_code=409,
            detail=f"该时间段已有学员预约（预约号 #{b_id}），无法直接锁定。请先与学员沟通协调退改。",
        )

    # Insert or update slots to BLOCKED
    curr = start_dt
    while curr < end_dt:
        await db.execute(
            text(
                f"""
                INSERT INTO `{table_name}` (slot_start, status, remark)
                VALUES (:st, 'BLOCKED', :reason)
                ON DUPLICATE KEY UPDATE status = 'BLOCKED', remark = :reason
                """
            ),
            {"st": curr, "reason": reason},
        )
        curr += timedelta(minutes=10)
    await db.commit()

    return {
        "success": True,
        "message": "Schedule slots successfully blocked",
        "date": str(target_date),
        "start_time": payload.start_time,
        "end_time": payload.end_time,
        "reason": reason,
    }


@router.post("/me/schedule/unblock", response_model=dict)
@router.delete("/me/schedule/block", response_model=dict)
async def unblock_schedule_slots(
    payload: CoachScheduleUnblockRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    coach_id = await _coach_id(user, db)
    target_date = payload.block_date or payload.date
    if target_date is None:
        raise HTTPException(status_code=422, detail="date or block_date is required")

    try:
        sp = payload.start_time.split(":")
        sh, sm = int(sp[0]), int(sp[1])
        ep = payload.end_time.split(":")
        eh, em = int(ep[0]), int(ep[1])
        stime = time(hour=sh, minute=sm)
        etime = time(hour=eh, minute=em)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid time format (HH:MM required)")

    if sm % 10 != 0 or em % 10 != 0:
        raise HTTPException(status_code=422, detail="start_time and end_time minute must align to a 10-minute grid")
    if etime <= stime:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    table_name = await ScheduleService(db).get_table_name(coach_id)
    start_dt = datetime.combine(target_date, stime)
    end_dt = datetime.combine(target_date, etime)

    await db.execute(
        text(
            f"""
            UPDATE `{table_name}`
            SET status = 'AVAILABLE', remark = NULL
            WHERE slot_start >= :sdt AND slot_start < :edt AND status = 'BLOCKED'
            """
        ),
        {"sdt": start_dt, "edt": end_dt},
    )
    await db.commit()

    return {
        "success": True,
        "message": "Schedule slots successfully unblocked",
        "date": str(target_date),
        "start_time": payload.start_time,
        "end_time": payload.end_time,
    }
