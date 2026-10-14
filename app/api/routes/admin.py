import csv
import io
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.security import hash_password
from app.db.session import get_app_db, get_ddl_engine
from app.services.schedule_service import ScheduleService

router = APIRouter()


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def _ensure_transaction(db: AsyncSession) -> None:
    if not db.in_transaction():
        await db.begin()


# ---------------------------------------------------------------------------
# Dashboard & Overview
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=dict)
async def admin_dashboard(
    days: int = Query(default=30, ge=7, le=365),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    totals = await db.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM users WHERE status = 'ACTIVE') AS total_users,
                (SELECT COUNT(*) FROM users WHERE role = 'MEMBER' AND status = 'ACTIVE') AS total_members,
                (SELECT COUNT(*) FROM coach WHERE status = 'ACTIVE') AS active_coaches,
                (SELECT COUNT(*) FROM booking
                 WHERE created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)) AS total_bookings,
                (SELECT COUNT(*) FROM booking
                 WHERE status = 'COMPLETED'
                   AND created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)) AS completed_bookings,
                (SELECT COALESCE(SUM(final_amount), 0) FROM orders
                 WHERE payment_status = 'PAID'
                   AND payment_time >= DATE_SUB(NOW(), INTERVAL :days DAY)) AS revenue,
                (SELECT COUNT(*) FROM member_package
                 WHERE status = 'ACTIVE') AS active_packages
            """
        ),
        {"days": days},
    )
    trend = await db.execute(
        text(
            """
            SELECT booking_date, COUNT(*) AS booking_count,
                   SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_count
            FROM booking
            WHERE booking_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
            GROUP BY booking_date
            ORDER BY booking_date
            """
        ),
        {"days": days},
    )
    top_coaches = await db.execute(
        text(
            """
            SELECT c.coach_id, u.display_name AS coach_name,
                   COUNT(b.booking_id) AS total_sessions,
                   COALESCE(AVG(rc.avg_rating), 0) AS avg_rating,
                   COALESCE(SUM(o.final_amount), 0) AS revenue_generated
            FROM coach c
            JOIN users u ON u.user_id = c.user_id
            LEFT JOIN booking b ON b.coach_id = c.coach_id
                AND b.status = 'COMPLETED'
                AND b.created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
            LEFT JOIN review_coach rc ON rc.booking_id = b.booking_id
            LEFT JOIN orders o ON o.booking_id = b.booking_id AND o.payment_status = 'PAID'
            WHERE c.status = 'ACTIVE'
            GROUP BY c.coach_id, u.display_name
            ORDER BY total_sessions DESC, avg_rating DESC
            LIMIT 5
            """
        ),
        {"days": days},
    )
    return {
        "totals": dict(totals.mappings().one()),
        "booking_trend": [dict(row) for row in trend.mappings().all()],
        "top_coaches": [dict(row) for row in top_coaches.mappings().all()],
        "period_days": days,
    }


@router.get("/activity", response_model=list[dict])
async def admin_recent_activity(
    limit: int = Query(default=10, ge=1, le=50),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT al.log_id, al.user_id, u.username, u.display_name,
                   al.action, al.entity_type, al.entity_id, al.detail, al.created_at
            FROM audit_log al
            LEFT JOIN users u ON u.user_id = al.user_id
            ORDER BY al.created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    activities = []
    for r in result.mappings().all():
        d = dict(r)
        actor = d.get("display_name") or d.get("username") or "System"
        action = d.get("action", "")
        entity_type = d.get("entity_type") or "resource"
        entity_id = d.get("entity_id") or ""
        activities.append(
            {
                "id": d["log_id"],
                "title": action.replace("_", " ").title(),
                "description": f"{actor} performed {action} on {entity_type} #{entity_id}".strip(),
                "timestamp": d["created_at"].isoformat() if d["created_at"] else None,
                "type": entity_type,
                "actor": actor,
                "action": action,
                "entity_id": d["entity_id"],
                "detail": d["detail"],
            }
        )
    return activities


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@router.get("/audit-log", response_model=list[dict])
async def audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT al.log_id, al.user_id, u.username, u.display_name, al.action,
                   al.entity_type, al.entity_id, al.detail,
                   al.ip_address, al.created_at
            FROM audit_log al
            LEFT JOIN users u ON u.user_id = al.user_id
            WHERE (:entity_type IS NULL OR al.entity_type = :entity_type)
              AND (:entity_id IS NULL OR al.entity_id = :entity_id)
              AND (:action IS NULL OR al.action = :action)
              AND (:user_id IS NULL OR al.user_id = :user_id)
              AND (:date_from IS NULL OR al.created_at >= :date_from)
              AND (:date_to IS NULL OR al.created_at <= :date_to)
            ORDER BY al.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "limit": limit,
            "offset": offset,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "user_id": user_id,
            "date_from": date_from,
            "date_to": date_to,
        },
    )
    return [dict(row) for row in result.mappings().all()]


@router.get("/audit-log/{log_id}", response_model=dict)
async def get_audit_log_entry(
    log_id: int,
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    result = await db.execute(
        text(
            """
            SELECT al.log_id, al.user_id, u.username, u.display_name, al.action,
                   al.entity_type, al.entity_id, al.detail,
                   al.ip_address, al.created_at
            FROM audit_log al
            LEFT JOIN users u ON u.user_id = al.user_id
            WHERE al.log_id = :log_id
            """
        ),
        {"log_id": log_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit log entry not found")
    return dict(row)


# ---------------------------------------------------------------------------
# Members management
# ---------------------------------------------------------------------------


@router.get("/members", response_model=dict)
async def admin_list_members(
    search: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None),
    level_code: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    offset = (page - 1) * page_size
    result = await db.execute(
        text(
            """
            SELECT u.user_id, u.username, u.display_name, u.email, u.phone,
                   u.status, u.last_login_at, u.created_at,
                   m.member_id, m.total_spend, ml.level_code, ml.level_name,
                   m.gender, m.birth_date, m.height_cm, m.weight_kg, m.fitness_goal
            FROM users u
            JOIN member m ON m.user_id = u.user_id
            JOIN membership_level ml ON ml.level_id = m.level_id
            WHERE u.role = 'MEMBER'
              AND (:search IS NULL OR u.display_name LIKE CONCAT('%', :search, '%')
                   OR u.username LIKE CONCAT('%', :search, '%')
                   OR u.email LIKE CONCAT('%', :search, '%')
                   OR u.phone LIKE CONCAT('%', :search, '%'))
              AND (:status IS NULL OR u.status = :status)
              AND (:level_code IS NULL OR ml.level_code = :level_code)
            ORDER BY u.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "search": search,
            "status": status,
            "level_code": level_code,
            "limit": page_size,
            "offset": offset,
        },
    )
    count_result = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM users u
            JOIN member m ON m.user_id = u.user_id
            JOIN membership_level ml ON ml.level_id = m.level_id
            WHERE u.role = 'MEMBER'
              AND (:search IS NULL OR u.display_name LIKE CONCAT('%', :search, '%')
                   OR u.username LIKE CONCAT('%', :search, '%')
                   OR u.email LIKE CONCAT('%', :search, '%')
                   OR u.phone LIKE CONCAT('%', :search, '%'))
              AND (:status IS NULL OR u.status = :status)
              AND (:level_code IS NULL OR ml.level_code = :level_code)
            """
        ),
        {"search": search, "status": status, "level_code": level_code},
    )
    total = int(count_result.scalar_one() or 0)
    return {
        "items": [dict(row) for row in result.mappings().all()],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/members/{user_id}", response_model=dict)
async def admin_get_member(
    user_id: int,
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    user_res = await db.execute(
        text(
            """
            SELECT u.user_id, u.username, u.display_name, u.email, u.phone,
                   u.status, u.last_login_at, u.created_at,
                   m.member_id, m.level_id, ml.level_code, ml.level_name,
                   m.total_spend, m.gender, m.birth_date, m.height_cm, m.weight_kg, m.fitness_goal
            FROM users u
            JOIN member m ON m.user_id = u.user_id
            JOIN membership_level ml ON ml.level_id = m.level_id
            WHERE u.user_id = :user_id AND u.role = 'MEMBER'
            """
        ),
        {"user_id": user_id},
    )
    user_row = user_res.mappings().one_or_none()
    if user_row is None:
        raise HTTPException(status_code=404, detail="Member not found")
    data = dict(user_row)

    member_id = data["member_id"]
    fit_res = await db.execute(
        text("SELECT * FROM fitness_profile WHERE member_id = :member_id"),
        {"member_id": member_id},
    )
    fit_row = fit_res.mappings().one_or_none()
    data["fitness_profile"] = dict(fit_row) if fit_row else None

    # Count of active packages and bookings
    stats_res = await db.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM member_package WHERE member_id = :member_id AND status = 'ACTIVE') AS active_packages,
                (SELECT COUNT(*) FROM booking WHERE member_id = :member_id) AS total_bookings,
                (SELECT COUNT(*) FROM booking WHERE member_id = :member_id AND status = 'COMPLETED') AS completed_bookings
            """
        ),
        {"member_id": member_id},
    )
    data["stats"] = dict(stats_res.mappings().one())
    return data


class AdminMemberCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)
    level_id: int = Field(default=1, ge=1, le=3)
    gender: Literal["MALE", "FEMALE", "OTHER"] | None = None
    birth_date: date | None = None
    height_cm: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    fitness_goal: str | None = Field(default=None, max_length=200)


@router.post("/members", response_model=dict, status_code=status.HTTP_201_CREATED)
async def admin_create_member(
    payload: AdminMemberCreate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    try:
        await _ensure_transaction(db)
        result = await db.execute(
            text(
                """
                INSERT INTO users (username, password_hash, display_name, email, phone, role, status)
                VALUES (:username, :password_hash, :display_name, :email, :phone, 'MEMBER', 'ACTIVE')
                """
            ),
            {
                "username": payload.username,
                "password_hash": hash_password(payload.password),
                "display_name": payload.display_name,
                "email": str(payload.email),
                "phone": payload.phone,
            },
        )
        user_id = result.lastrowid
        member_res = await db.execute(
            text(
                """
                INSERT INTO member
                    (user_id, level_id, gender, birth_date, height_cm, weight_kg, fitness_goal)
                VALUES
                    (:user_id, :level_id, :gender, :birth_date, :height_cm, :weight_kg, :fitness_goal)
                """
            ),
            {
                "user_id": user_id,
                "level_id": payload.level_id,
                "gender": payload.gender,
                "birth_date": payload.birth_date,
                "height_cm": payload.height_cm,
                "weight_kg": payload.weight_kg,
                "fitness_goal": payload.fitness_goal,
            },
        )
        member_id = member_res.lastrowid
        await db.execute(
            text("INSERT INTO fitness_profile (member_id) VALUES (:member_id)"),
            {"member_id": member_id},
        )
        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_CREATE_MEMBER', 'users', :user_id,
                        JSON_OBJECT('username', :username, 'member_id', :member_id), :ip)
                """
            ),
            {
                "admin_id": admin["user_id"],
                "user_id": user_id,
                "username": payload.username,
                "member_id": member_id,
                "ip": ip,
            },
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Username, email, or phone is already registered",
        ) from None

    user_result = await db.execute(
        text(
            """
            SELECT u.user_id, u.username, u.display_name, u.email, u.phone, u.status,
                   m.member_id, ml.level_code, ml.level_name, m.total_spend
            FROM users u
            JOIN member m ON m.user_id = u.user_id
            JOIN membership_level ml ON ml.level_id = m.level_id
            WHERE u.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    return dict(user_result.mappings().one())


class AdminMemberUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    status: Literal["ACTIVE", "DISABLED"] | None = None
    level_id: int | None = Field(default=None, ge=1, le=3)
    gender: Literal["MALE", "FEMALE", "OTHER"] | None = None
    birth_date: date | None = None
    height_cm: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=5, decimal_places=1)
    fitness_goal: str | None = Field(default=None, max_length=200)


@router.put("/members/{user_id}", response_model=dict)
async def admin_update_member(
    user_id: int,
    payload: AdminMemberUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    mem_check = await db.execute(
        text("SELECT member_id FROM member WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    member_id = mem_check.scalar_one_or_none()
    if member_id is None:
        raise HTTPException(status_code=404, detail="Member not found")

    user_updates = []
    user_params: dict = {"user_id": user_id}
    if payload.display_name is not None:
        user_updates.append("display_name = :display_name")
        user_params["display_name"] = payload.display_name
    if payload.email is not None:
        user_updates.append("email = :email")
        user_params["email"] = str(payload.email)
    if payload.phone is not None:
        user_updates.append("phone = :phone")
        user_params["phone"] = payload.phone
    if payload.status is not None:
        user_updates.append("status = :status")
        user_params["status"] = payload.status

    member_updates = []
    member_params: dict = {"member_id": member_id}
    if payload.level_id is not None:
        member_updates.append("level_id = :level_id")
        member_params["level_id"] = payload.level_id
    if payload.gender is not None:
        member_updates.append("gender = :gender")
        member_params["gender"] = payload.gender
    if payload.birth_date is not None:
        member_updates.append("birth_date = :birth_date")
        member_params["birth_date"] = payload.birth_date
    if payload.height_cm is not None:
        member_updates.append("height_cm = :height_cm")
        member_params["height_cm"] = payload.height_cm
    if payload.weight_kg is not None:
        member_updates.append("weight_kg = :weight_kg")
        member_params["weight_kg"] = payload.weight_kg
    if payload.fitness_goal is not None:
        member_updates.append("fitness_goal = :fitness_goal")
        member_params["fitness_goal"] = payload.fitness_goal

    try:
        await _ensure_transaction(db)
        if user_updates:
            await db.execute(
                text(f"UPDATE users SET {', '.join(user_updates)} WHERE user_id = :user_id"),
                user_params,
            )
        if member_updates:
            await db.execute(
                text(f"UPDATE member SET {', '.join(member_updates)} WHERE member_id = :member_id"),
                member_params,
            )
        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_UPDATE_MEMBER', 'users', :user_id,
                        JSON_OBJECT('user_id', :user_id, 'member_id', :member_id), :ip)
                """
            ),
            {
                "admin_id": admin["user_id"],
                "user_id": user_id,
                "member_id": member_id,
                "ip": ip,
            },
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email or phone conflict") from None

    user_result = await db.execute(
        text(
            """
            SELECT u.user_id, u.username, u.display_name, u.email, u.phone, u.status,
                   m.member_id, ml.level_code, ml.level_name, m.total_spend,
                   m.gender, m.birth_date, m.height_cm, m.weight_kg, m.fitness_goal
            FROM users u
            JOIN member m ON m.user_id = u.user_id
            JOIN membership_level ml ON ml.level_id = m.level_id
            WHERE u.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    return dict(user_result.mappings().one())


@router.delete("/members/{user_id}", response_model=dict)
async def admin_delete_member(
    user_id: int,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    result = await db.execute(
        text("UPDATE users SET status = 'DISABLED' WHERE user_id = :user_id AND role = 'MEMBER'"),
        {"user_id": user_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_DISABLE_MEMBER', 'users', :user_id,
                    JSON_OBJECT('status', 'DISABLED'), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "user_id": user_id, "ip": ip},
    )
    await db.commit()
    return {"success": True, "message": "Member disabled", "user_id": user_id}


class UserStatusUpdate(BaseModel):
    status: str  # ACTIVE | DISABLED


@router.patch("/members/{user_id}/status", response_model=dict)
async def update_member_status(
    user_id: int,
    payload: UserStatusUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    if payload.status not in ("ACTIVE", "DISABLED"):
        raise HTTPException(status_code=422, detail="status must be ACTIVE or DISABLED")
    result = await db.execute(
        text("UPDATE users SET status = :status WHERE user_id = :user_id AND role = 'MEMBER'"),
        {"status": payload.status, "user_id": user_id},
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'UPDATE_MEMBER_STATUS', 'users', :user_id,
                    JSON_OBJECT('status', :status), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "user_id": user_id,
            "status": payload.status,
            "ip": _get_client_ip(request),
        },
    )
    await db.commit()
    user_result = await db.execute(
        text(
            """
            SELECT u.user_id, u.username, u.display_name, u.email, u.status,
                   m.member_id, ml.level_code, m.total_spend
            FROM users u
            JOIN member m ON m.user_id = u.user_id
            JOIN membership_level ml ON ml.level_id = m.level_id
            WHERE u.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    return dict(user_result.mappings().one())


# ---------------------------------------------------------------------------
# Coaches management
# ---------------------------------------------------------------------------


@router.get("/coaches", response_model=dict)
async def admin_list_coaches(
    search: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None),
    coach_level: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    offset = (page - 1) * page_size
    result = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, c.coach_level, c.service_mode,
                   c.years_experience, c.break_interval, c.status, c.hired_at, c.created_at,
                   u.user_id, u.display_name, u.email, u.phone, u.status AS user_status,
                   COALESCE(AVG(rc.avg_rating), 0) AS avg_rating,
                   COUNT(DISTINCT b.booking_id) AS total_bookings
            FROM coach c
            JOIN users u ON u.user_id = c.user_id
            LEFT JOIN booking b ON b.coach_id = c.coach_id AND b.status = 'COMPLETED'
            LEFT JOIN review_coach rc ON rc.booking_id = b.booking_id
            WHERE (:search IS NULL OR u.display_name LIKE CONCAT('%', :search, '%')
                   OR c.coach_no LIKE CONCAT('%', :search, '%')
                   OR u.email LIKE CONCAT('%', :search, '%')
                   OR u.phone LIKE CONCAT('%', :search, '%'))
              AND (:status IS NULL OR c.status = :status)
              AND (:coach_level IS NULL OR c.coach_level = :coach_level)
            GROUP BY c.coach_id, c.coach_no, c.coach_level, c.service_mode,
                     c.years_experience, c.break_interval, c.status, c.hired_at, c.created_at,
                     u.user_id, u.display_name, u.email, u.phone, u.status
            ORDER BY c.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "search": search,
            "status": status,
            "coach_level": coach_level,
            "limit": page_size,
            "offset": offset,
        },
    )
    count_result = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM coach c
            JOIN users u ON u.user_id = c.user_id
            WHERE (:search IS NULL OR u.display_name LIKE CONCAT('%', :search, '%')
                   OR c.coach_no LIKE CONCAT('%', :search, '%')
                   OR u.email LIKE CONCAT('%', :search, '%')
                   OR u.phone LIKE CONCAT('%', :search, '%'))
              AND (:status IS NULL OR c.status = :status)
              AND (:coach_level IS NULL OR c.coach_level = :coach_level)
            """
        ),
        {"search": search, "status": status, "coach_level": coach_level},
    )
    total = int(count_result.scalar_one() or 0)
    return {
        "items": [dict(row) for row in result.mappings().all()],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/coaches/{coach_id}", response_model=dict)
async def admin_get_coach(
    coach_id: int,
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    coach_res = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, c.coach_level, c.bio, c.service_mode,
                   c.break_interval, c.years_experience, c.certifications, c.avatar_url,
                   c.status, c.hired_at, c.created_at,
                   u.user_id, u.username, u.display_name, u.email, u.phone, u.status AS user_status
            FROM coach c
            JOIN users u ON u.user_id = c.user_id
            WHERE c.coach_id = :coach_id
            """
        ),
        {"coach_id": coach_id},
    )
    coach_row = coach_res.mappings().one_or_none()
    if coach_row is None:
        raise HTTPException(status_code=404, detail="Coach not found")
    data = dict(coach_row)

    courses_res = await db.execute(
        text(
            """
            SELECT cc.course_id, c.course_name, cc.price_per_session, cc.is_active
            FROM coach_course cc
            JOIN course c ON c.course_id = cc.course_id
            WHERE cc.coach_id = :coach_id AND cc.is_active = 1
            """
        ),
        {"coach_id": coach_id},
    )
    data["courses"] = [dict(c) for c in courses_res.mappings().all()]
    data["assigned_course_ids"] = [c["course_id"] for c in data["courses"]]

    gyms_res = await db.execute(
        text(
            """
            SELECT cs.gym_id, g.gym_name, cs.is_home_service, cs.service_area, cs.is_active
            FROM coach_service cs
            JOIN gym g ON g.gym_id = cs.gym_id
            WHERE cs.coach_id = :coach_id AND cs.is_active = 1
            """
        ),
        {"coach_id": coach_id},
    )
    data["gyms"] = [dict(g) for g in gyms_res.mappings().all()]
    data["assigned_location_ids"] = [g["gym_id"] for g in data["gyms"]]

    stats_res = await db.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM booking WHERE coach_id = :coach_id AND status = 'COMPLETED') AS completed_sessions,
                (SELECT COALESCE(AVG(avg_rating), 0) FROM review_coach rc
                 JOIN booking b ON b.booking_id = rc.booking_id WHERE b.coach_id = :coach_id) AS avg_rating
            """
        ),
        {"coach_id": coach_id},
    )
    data["stats"] = dict(stats_res.mappings().one())
    return data


class AdminCoachCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)
    coach_no: str = Field(pattern=r"^[0-9]{4,8}$")
    coach_level: Literal["BEGINNER", "INTERMEDIATE", "ADVANCED", "MASTER"] = "BEGINNER"
    bio: str | None = None
    service_mode: Literal["GYM", "HOME", "BOTH"] = "GYM"
    break_interval: Literal[10, 20, 30] = 10
    years_experience: int | None = Field(default=None, ge=0)
    certifications: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=255)
    hired_at: date | None = None
    courses: list[dict] = Field(default_factory=list)
    gyms: list[dict] = Field(default_factory=list)
    assigned_location_ids: list[int] = Field(default_factory=list)
    assigned_course_ids: list[int] = Field(default_factory=list)


@router.post("/coaches", response_model=dict, status_code=status.HTTP_201_CREATED)
async def admin_create_coach(
    payload: AdminCoachCreate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
    ddl_engine=Depends(get_ddl_engine),
) -> dict:
    ip = _get_client_ip(request)
    try:
        await _ensure_transaction(db)
        result = await db.execute(
            text(
                """
                INSERT INTO users (username, password_hash, display_name, email, phone, role, status)
                VALUES (:username, :password_hash, :display_name, :email, :phone, 'COACH', 'ACTIVE')
                """
            ),
            {
                "username": payload.username,
                "password_hash": hash_password(payload.password),
                "display_name": payload.display_name,
                "email": str(payload.email),
                "phone": payload.phone,
            },
        )
        user_id = result.lastrowid
        coach_res = await db.execute(
            text(
                """
                INSERT INTO coach
                    (coach_no, user_id, coach_level, bio, service_mode,
                     break_interval, years_experience, certifications, avatar_url,
                     status, hired_at)
                VALUES
                    (:coach_no, :user_id, :coach_level, :bio, :service_mode,
                     :break_interval, :years_experience, :certifications, :avatar_url,
                     'ACTIVE', :hired_at)
                """
            ),
            {
                "coach_no": payload.coach_no,
                "user_id": user_id,
                "coach_level": payload.coach_level,
                "bio": payload.bio,
                "service_mode": payload.service_mode,
                "break_interval": payload.break_interval,
                "years_experience": payload.years_experience,
                "certifications": payload.certifications,
                "avatar_url": payload.avatar_url,
                "hired_at": payload.hired_at or date.today(),
            },
        )
        coach_id = coach_res.lastrowid

        # Insert courses from courses list or assigned_course_ids
        course_items = list(payload.courses)
        for cid in payload.assigned_course_ids:
            if not any(c.get("course_id") == cid for c in course_items):
                course_items.append({"course_id": cid, "price_per_session": 1000.0})

        for c in course_items:
            await db.execute(
                text(
                    """
                    INSERT INTO coach_course (coach_id, course_id, price_per_session, is_active)
                    VALUES (:coach_id, :course_id, :price_per_session, 1)
                    ON DUPLICATE KEY UPDATE price_per_session = VALUES(price_per_session), is_active = 1
                    """
                ),
                {
                    "coach_id": coach_id,
                    "course_id": c["course_id"],
                    "price_per_session": c.get("price_per_session", 1000.0),
                },
            )

        gym_items = list(payload.gyms)
        for gid in payload.assigned_location_ids:
            if not any(g.get("gym_id") == gid for g in gym_items):
                gym_items.append({"gym_id": gid, "is_home_service": 0, "service_area": None})

        for g in gym_items:
            await db.execute(
                text(
                    """
                    INSERT INTO coach_service (coach_id, gym_id, is_home_service, service_area, is_active)
                    VALUES (:coach_id, :gym_id, :is_home_service, :service_area, 1)
                    ON DUPLICATE KEY UPDATE is_active = 1
                    """
                ),
                {
                    "coach_id": coach_id,
                    "gym_id": g["gym_id"],
                    "is_home_service": g.get("is_home_service", 0),
                    "service_area": g.get("service_area"),
                },
            )

        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_CREATE_COACH', 'coach', :coach_id,
                        JSON_OBJECT('coach_no', :coach_no, 'username', :username), :ip)
                """
            ),
            {
                "admin_id": admin["user_id"],
                "coach_id": coach_id,
                "coach_no": payload.coach_no,
                "username": payload.username,
                "ip": ip,
            },
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Coach number, username, email, or phone is already registered",
        ) from None

    try:
        await ScheduleService(db, ddl_engine).create_schedule_table(coach_id)
    except Exception:
        pass

    coach_result = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, c.coach_level, c.service_mode, c.status,
                   u.user_id, u.username, u.display_name, u.email, u.phone
            FROM coach c JOIN users u ON u.user_id = c.user_id
            WHERE c.coach_id = :coach_id
            """
        ),
        {"coach_id": coach_id},
    )
    return dict(coach_result.mappings().one())


class AdminCoachUpdate(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    coach_level: Literal["BEGINNER", "INTERMEDIATE", "ADVANCED", "MASTER"] | None = None
    bio: str | None = None
    service_mode: Literal["GYM", "HOME", "BOTH"] | None = None
    break_interval: Literal[10, 20, 30] | None = None
    years_experience: int | None = None
    certifications: str | None = None
    avatar_url: str | None = None
    status: Literal["ACTIVE", "ON_LEAVE", "RESIGNED"] | None = None
    courses: list[dict] | None = None
    gyms: list[dict] | None = None
    assigned_location_ids: list[int] | None = None
    assigned_course_ids: list[int] | None = None


@router.put("/coaches/{coach_id}", response_model=dict)
async def admin_update_coach(
    coach_id: int,
    payload: AdminCoachUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    coach_res = await db.execute(
        text("SELECT user_id FROM coach WHERE coach_id = :coach_id"),
        {"coach_id": coach_id},
    )
    user_id = coach_res.scalar_one_or_none()
    if user_id is None:
        raise HTTPException(status_code=404, detail="Coach not found")

    user_updates = []
    user_params: dict = {"user_id": user_id}
    if payload.display_name is not None:
        user_updates.append("display_name = :display_name")
        user_params["display_name"] = payload.display_name
    if payload.email is not None:
        user_updates.append("email = :email")
        user_params["email"] = str(payload.email)
    if payload.phone is not None:
        user_updates.append("phone = :phone")
        user_params["phone"] = payload.phone

    coach_updates = []
    coach_params: dict = {"coach_id": coach_id}
    if payload.coach_level is not None:
        coach_updates.append("coach_level = :coach_level")
        coach_params["coach_level"] = payload.coach_level
    if payload.bio is not None:
        coach_updates.append("bio = :bio")
        coach_params["bio"] = payload.bio
    if payload.service_mode is not None:
        coach_updates.append("service_mode = :service_mode")
        coach_params["service_mode"] = payload.service_mode
    if payload.break_interval is not None:
        coach_updates.append("break_interval = :break_interval")
        coach_params["break_interval"] = payload.break_interval
    if payload.years_experience is not None:
        coach_updates.append("years_experience = :years_experience")
        coach_params["years_experience"] = payload.years_experience
    if payload.certifications is not None:
        coach_updates.append("certifications = :certifications")
        coach_params["certifications"] = payload.certifications
    if payload.avatar_url is not None:
        coach_updates.append("avatar_url = :avatar_url")
        coach_params["avatar_url"] = payload.avatar_url
    if payload.status is not None:
        coach_updates.append("status = :status")
        coach_params["status"] = payload.status

    try:
        await _ensure_transaction(db)
        if user_updates:
            await db.execute(
                text(f"UPDATE users SET {', '.join(user_updates)} WHERE user_id = :user_id"),
                user_params,
            )
        if coach_updates:
            await db.execute(
                text(f"UPDATE coach SET {', '.join(coach_updates)} WHERE coach_id = :coach_id"),
                coach_params,
            )

        # Update course associations
        if payload.assigned_course_ids is not None:
            await db.execute(
                text("UPDATE coach_course SET is_active = 0 WHERE coach_id = :coach_id"),
                {"coach_id": coach_id},
            )
            for cid in payload.assigned_course_ids:
                await db.execute(
                    text(
                        """
                        INSERT INTO coach_course (coach_id, course_id, price_per_session, is_active)
                        VALUES (:coach_id, :course_id, 1000.0, 1)
                        ON DUPLICATE KEY UPDATE is_active = 1
                        """
                    ),
                    {"coach_id": coach_id, "course_id": cid},
                )
        elif payload.courses is not None:
            for c in payload.courses:
                await db.execute(
                    text(
                        """
                        INSERT INTO coach_course (coach_id, course_id, price_per_session, is_active)
                        VALUES (:coach_id, :course_id, :price, 1)
                        ON DUPLICATE KEY UPDATE price_per_session = VALUES(price_per_session), is_active = 1
                        """
                    ),
                    {
                        "coach_id": coach_id,
                        "course_id": c["course_id"],
                        "price": c.get("price_per_session", 1000.0),
                    },
                )

        # Update location associations
        if payload.assigned_location_ids is not None:
            await db.execute(
                text("UPDATE coach_service SET is_active = 0 WHERE coach_id = :coach_id"),
                {"coach_id": coach_id},
            )
            for gid in payload.assigned_location_ids:
                await db.execute(
                    text(
                        """
                        INSERT INTO coach_service (coach_id, gym_id, is_home_service, is_active)
                        VALUES (:coach_id, :gym_id, 0, 1)
                        ON DUPLICATE KEY UPDATE is_active = 1
                        """
                    ),
                    {"coach_id": coach_id, "gym_id": gid},
                )
        elif payload.gyms is not None:
            for g in payload.gyms:
                await db.execute(
                    text(
                        """
                        INSERT INTO coach_service (coach_id, gym_id, is_home_service, service_area, is_active)
                        VALUES (:coach_id, :gym_id, :is_home, :area, 1)
                        ON DUPLICATE KEY UPDATE is_active = 1
                        """
                    ),
                    {
                        "coach_id": coach_id,
                        "gym_id": g["gym_id"],
                        "is_home": g.get("is_home_service", 0),
                        "area": g.get("service_area"),
                    },
                )

        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_UPDATE_COACH', 'coach', :coach_id,
                        JSON_OBJECT('coach_id', :coach_id), :ip)
                """
            ),
            {"admin_id": admin["user_id"], "coach_id": coach_id, "ip": ip},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email or phone collision") from None

    updated_result = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, c.coach_level, c.service_mode, c.status,
                   u.user_id, u.display_name, u.email, u.phone
            FROM coach c JOIN users u ON u.user_id = c.user_id
            WHERE c.coach_id = :coach_id
            """
        ),
        {"coach_id": coach_id},
    )
    return dict(updated_result.mappings().one())


@router.delete("/coaches/{coach_id}", response_model=dict)
async def admin_delete_coach(
    coach_id: int,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    coach_res = await db.execute(
        text("SELECT user_id FROM coach WHERE coach_id = :coach_id"),
        {"coach_id": coach_id},
    )
    user_id = coach_res.scalar_one_or_none()
    if user_id is None:
        raise HTTPException(status_code=404, detail="Coach not found")

    await db.execute(
        text("UPDATE coach SET status = 'RESIGNED' WHERE coach_id = :coach_id"),
        {"coach_id": coach_id},
    )
    await db.execute(
        text("UPDATE users SET status = 'DISABLED' WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_RESIGN_COACH', 'coach', :coach_id,
                    JSON_OBJECT('status', 'RESIGNED'), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "coach_id": coach_id, "ip": ip},
    )
    await db.commit()
    return {"success": True, "message": "Coach resigned and disabled", "coach_id": coach_id}


@router.get("/coaches/{coach_id}/verification-documents", response_model=dict)
async def admin_get_coach_verification_documents(
    coach_id: int,
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    result = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, c.certifications, c.years_experience,
                   c.status, u.display_name, u.email
            FROM coach c
            JOIN users u ON u.user_id = c.user_id
            WHERE c.coach_id = :coach_id
            """
        ),
        {"coach_id": coach_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Coach not found")
    d = dict(row)
    certs = [c.strip() for c in (d.get("certifications") or "").split(",") if c.strip()]
    return {
        "coach_id": d["coach_id"],
        "display_name": d["display_name"],
        "status": d["status"],
        "is_verified": d["status"] == "ACTIVE",
        "certifications": certs,
        "documents": [
            {
                "id": idx + 1,
                "title": cert,
                "type": "CERTIFICATION",
                "status": "VERIFIED" if d["status"] == "ACTIVE" else "PENDING_REVIEW",
            }
            for idx, cert in enumerate(certs)
        ]
        or [
            {
                "id": 1,
                "title": "National Fitness Certification",
                "type": "CERTIFICATION",
                "status": "PENDING_REVIEW",
            }
        ],
    }


class CoachVerifyPayload(BaseModel):
    verified: bool = True
    notes: str | None = None


@router.post("/coaches/{coach_id}/verify", response_model=dict)
async def admin_verify_coach(
    coach_id: int,
    payload: CoachVerifyPayload,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    new_status = "ACTIVE" if payload.verified else "ON_LEAVE"
    result = await db.execute(
        text("UPDATE coach SET status = :status WHERE coach_id = :coach_id"),
        {"status": new_status, "coach_id": coach_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Coach not found")
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_VERIFY_COACH', 'coach', :coach_id,
                    JSON_OBJECT('verified', :verified, 'status', :status, 'notes', :notes), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "coach_id": coach_id,
            "verified": payload.verified,
            "status": new_status,
            "notes": payload.notes,
            "ip": _get_client_ip(request),
        },
    )
    await db.commit()
    return {"success": True, "coach_id": coach_id, "status": new_status}


class CourseAssignmentItem(BaseModel):
    course_id: int = Field(gt=0)
    price_per_session: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    is_active: int = 1


@router.post("/coaches/{coach_id}/courses", response_model=dict)
async def assign_coach_courses(
    coach_id: int,
    payload: CourseAssignmentItem,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    coach_check = await db.execute(
        text("SELECT coach_id FROM coach WHERE coach_id = :coach_id"),
        {"coach_id": coach_id},
    )
    if coach_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Coach not found")

    course_check = await db.execute(
        text("SELECT course_id FROM course WHERE course_id = :course_id"),
        {"course_id": payload.course_id},
    )
    if course_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Course not found")

    await db.execute(
        text(
            """
            INSERT INTO coach_course (coach_id, course_id, price_per_session, is_active)
            VALUES (:coach_id, :course_id, :price_per_session, :is_active)
            ON DUPLICATE KEY UPDATE
                price_per_session = VALUES(price_per_session),
                is_active = VALUES(is_active)
            """
        ),
        {
            "coach_id": coach_id,
            "course_id": payload.course_id,
            "price_per_session": payload.price_per_session,
            "is_active": payload.is_active,
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ASSIGN_COACH_COURSE', 'coach_course', :coach_id,
                    JSON_OBJECT('course_id', :course_id, 'price', :price), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "coach_id": coach_id,
            "course_id": payload.course_id,
            "price": float(payload.price_per_session),
            "ip": _get_client_ip(request),
        },
    )
    await db.commit()
    result = await db.execute(
        text(
            """
            SELECT cc.coach_id, cc.course_id, c.course_name, cc.price_per_session, cc.is_active
            FROM coach_course cc
            JOIN course c ON c.course_id = cc.course_id
            WHERE cc.coach_id = :coach_id AND cc.course_id = :course_id
            """
        ),
        {"coach_id": coach_id, "course_id": payload.course_id},
    )
    return dict(result.mappings().one())


class CoachStatusUpdate(BaseModel):
    status: str  # ACTIVE | ON_LEAVE | RESIGNED


@router.patch("/coaches/{coach_id}/status", response_model=dict)
async def update_coach_status(
    coach_id: int,
    payload: CoachStatusUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    if payload.status not in ("ACTIVE", "ON_LEAVE", "RESIGNED"):
        raise HTTPException(status_code=422, detail="status must be ACTIVE, ON_LEAVE, or RESIGNED")
    result = await db.execute(
        text("UPDATE coach SET status = :status WHERE coach_id = :coach_id"),
        {"status": payload.status, "coach_id": coach_id},
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Coach not found")
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'UPDATE_COACH_STATUS', 'coach', :coach_id,
                    JSON_OBJECT('status', :status), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "coach_id": coach_id,
            "status": payload.status,
            "ip": _get_client_ip(request),
        },
    )
    await db.commit()
    coach_result = await db.execute(
        text(
            """
            SELECT c.coach_id, c.coach_no, c.coach_level, c.status,
                   u.display_name, u.email
            FROM coach c JOIN users u ON u.user_id = c.user_id
            WHERE c.coach_id = :coach_id
            """
        ),
        {"coach_id": coach_id},
    )
    return dict(coach_result.mappings().one())


# ---------------------------------------------------------------------------
# Courses management
# ---------------------------------------------------------------------------


class AdminCourseCreate(BaseModel):
    course_name: str = Field(min_length=2, max_length=100)
    description: str | None = None
    equipment: str | None = None
    difficulty: Literal["BEGINNER", "INTERMEDIATE", "ADVANCED"]
    default_duration: int = Field(ge=10)
    is_active: int = 1
    assigned_coach_ids: list[int] = Field(default_factory=list)


@router.post("/courses", response_model=dict, status_code=status.HTTP_201_CREATED)
async def admin_create_course(
    payload: AdminCourseCreate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    if payload.default_duration % 10 != 0:
        raise HTTPException(status_code=422, detail="default_duration must be a multiple of 10")
    ip = _get_client_ip(request)
    try:
        await _ensure_transaction(db)
        result = await db.execute(
            text(
                """
                INSERT INTO course (course_name, description, equipment, difficulty, default_duration, is_active)
                VALUES (:course_name, :description, :equipment, :difficulty, :default_duration, :is_active)
                """
            ),
            {
                "course_name": payload.course_name,
                "description": payload.description,
                "equipment": payload.equipment,
                "difficulty": payload.difficulty,
                "default_duration": payload.default_duration,
                "is_active": payload.is_active,
            },
        )
        course_id = result.lastrowid

        for coach_id in payload.assigned_coach_ids:
            await db.execute(
                text(
                    """
                    INSERT INTO coach_course (coach_id, course_id, price_per_session, is_active)
                    VALUES (:coach_id, :course_id, 1000.0, 1)
                    ON DUPLICATE KEY UPDATE is_active = 1
                    """
                ),
                {"coach_id": coach_id, "course_id": course_id},
            )

        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_CREATE_COURSE', 'course', :course_id,
                        JSON_OBJECT('course_name', :course_name), :ip)
                """
            ),
            {"admin_id": admin["user_id"], "course_id": course_id, "course_name": payload.course_name, "ip": ip},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Course name already exists") from None

    res = await db.execute(text("SELECT * FROM course WHERE course_id = :id"), {"id": course_id})
    return dict(res.mappings().one())


class AdminCourseUpdate(BaseModel):
    course_name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None
    equipment: str | None = None
    difficulty: Literal["BEGINNER", "INTERMEDIATE", "ADVANCED"] | None = None
    default_duration: int | None = Field(default=None, ge=10)
    is_active: int | None = None
    assigned_coach_ids: list[int] | None = None


@router.put("/courses/{course_id}", response_model=dict)
async def admin_update_course(
    course_id: int,
    payload: AdminCourseUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    if payload.default_duration is not None and payload.default_duration % 10 != 0:
        raise HTTPException(status_code=422, detail="default_duration must be a multiple of 10")
    ip = _get_client_ip(request)

    updates = []
    params: dict = {"course_id": course_id}
    if payload.course_name is not None:
        updates.append("course_name = :course_name")
        params["course_name"] = payload.course_name
    if payload.description is not None:
        updates.append("description = :description")
        params["description"] = payload.description
    if payload.equipment is not None:
        updates.append("equipment = :equipment")
        params["equipment"] = payload.equipment
    if payload.difficulty is not None:
        updates.append("difficulty = :difficulty")
        params["difficulty"] = payload.difficulty
    if payload.default_duration is not None:
        updates.append("default_duration = :default_duration")
        params["default_duration"] = payload.default_duration
    if payload.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = payload.is_active

    await _ensure_transaction(db)
    if updates:
        res = await db.execute(
            text(f"UPDATE course SET {', '.join(updates)} WHERE course_id = :course_id"),
            params,
        )
        if res.rowcount == 0:
            await db.rollback()
            raise HTTPException(status_code=404, detail="Course not found")

    if payload.assigned_coach_ids is not None:
        await db.execute(
            text("UPDATE coach_course SET is_active = 0 WHERE course_id = :course_id"),
            {"course_id": course_id},
        )
        for coach_id in payload.assigned_coach_ids:
            await db.execute(
                text(
                    """
                    INSERT INTO coach_course (coach_id, course_id, price_per_session, is_active)
                    VALUES (:coach_id, :course_id, 1000.0, 1)
                    ON DUPLICATE KEY UPDATE is_active = 1
                    """
                ),
                {"coach_id": coach_id, "course_id": course_id},
            )

    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_UPDATE_COURSE', 'course', :course_id,
                    JSON_OBJECT('course_id', :course_id), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "course_id": course_id, "ip": ip},
    )
    await db.commit()

    res = await db.execute(text("SELECT * FROM course WHERE course_id = :id"), {"id": course_id})
    return dict(res.mappings().one())


@router.delete("/courses/{course_id}", response_model=dict)
async def admin_delete_course(
    course_id: int,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    check = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM booking
            WHERE course_id = :course_id
              AND status IN ('PENDING', 'CONFIRMED')
              AND booking_date >= CURDATE()
            """
        ),
        {"course_id": course_id},
    )
    if (check.scalar_one() or 0) > 0:
        raise HTTPException(status_code=409, detail="Cannot archive course with active upcoming bookings")

    await _ensure_transaction(db)
    await db.execute(
        text("UPDATE course SET is_active = 0 WHERE course_id = :course_id"),
        {"course_id": course_id},
    )
    await db.execute(
        text("UPDATE coach_course SET is_active = 0 WHERE course_id = :course_id"),
        {"course_id": course_id},
    )
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_ARCHIVE_COURSE', 'course', :course_id,
                    JSON_OBJECT('is_active', 0), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "course_id": course_id, "ip": ip},
    )
    await db.commit()
    return {"success": True, "message": "Course archived", "course_id": course_id}


class CourseStatusUpdate(BaseModel):
    is_active: int  # 1 or 0


@router.patch("/courses/{course_id}/status", response_model=dict)
async def update_course_status(
    course_id: int,
    payload: CourseStatusUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    if payload.is_active not in (0, 1):
        raise HTTPException(status_code=422, detail="is_active must be 0 or 1")
    result = await db.execute(
        text("UPDATE course SET is_active = :is_active WHERE course_id = :course_id"),
        {"is_active": payload.is_active, "course_id": course_id},
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'UPDATE_COURSE_STATUS', 'course', :course_id,
                    JSON_OBJECT('is_active', :is_active), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "course_id": course_id,
            "is_active": payload.is_active,
            "ip": _get_client_ip(request),
        },
    )
    await db.commit()
    course_result = await db.execute(
        text("SELECT * FROM course WHERE course_id = :course_id"),
        {"course_id": course_id},
    )
    return dict(course_result.mappings().one())


# ---------------------------------------------------------------------------
# Locations (Gyms) management
# ---------------------------------------------------------------------------


class AdminLocationCreate(BaseModel):
    gym_name: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=3, max_length=255)
    district: Literal["NIMMAN", "OLD_CITY", "CENTRAL", "MAE_RIM", "HANG_DONG"]
    phone: str | None = None
    facilities: str | None = None
    opening_time: str = "06:00:00"
    closing_time: str = "22:00:00"
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    is_active: int = 1
    assigned_coach_ids: list[int] = Field(default_factory=list)


@router.post("/locations", response_model=dict, status_code=status.HTTP_201_CREATED)
async def admin_create_location(
    payload: AdminLocationCreate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    await _ensure_transaction(db)
    result = await db.execute(
        text(
            """
            INSERT INTO gym
                (gym_name, address, district, phone, facilities, opening_time, closing_time, latitude, longitude, is_active)
            VALUES
                (:gym_name, :address, :district, :phone, :facilities, :opening_time, :closing_time, :latitude, :longitude, :is_active)
            """
        ),
        {
            "gym_name": payload.gym_name,
            "address": payload.address,
            "district": payload.district,
            "phone": payload.phone,
            "facilities": payload.facilities,
            "opening_time": payload.opening_time,
            "closing_time": payload.closing_time,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "is_active": payload.is_active,
        },
    )
    gym_id = result.lastrowid

    for coach_id in payload.assigned_coach_ids:
        await db.execute(
            text(
                """
                INSERT INTO coach_service (coach_id, gym_id, is_home_service, is_active)
                VALUES (:coach_id, :gym_id, 0, 1)
                ON DUPLICATE KEY UPDATE is_active = 1
                """
            ),
            {"coach_id": coach_id, "gym_id": gym_id},
        )

    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_CREATE_LOCATION', 'gym', :gym_id,
                    JSON_OBJECT('gym_name', :gym_name), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "gym_id": gym_id, "gym_name": payload.gym_name, "ip": ip},
    )
    await db.commit()

    res = await db.execute(text("SELECT * FROM gym WHERE gym_id = :id"), {"id": gym_id})
    row = dict(res.mappings().one())
    if row.get("opening_time") is not None:
        row["opening_time"] = str(row["opening_time"])
    if row.get("closing_time") is not None:
        row["closing_time"] = str(row["closing_time"])
    return row


class AdminLocationUpdate(BaseModel):
    gym_name: str | None = Field(default=None, min_length=2, max_length=100)
    address: str | None = Field(default=None, min_length=3, max_length=255)
    district: Literal["NIMMAN", "OLD_CITY", "CENTRAL", "MAE_RIM", "HANG_DONG"] | None = None
    phone: str | None = None
    facilities: str | None = None
    opening_time: str | None = None
    closing_time: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    is_active: int | None = None
    assigned_coach_ids: list[int] | None = None


@router.put("/locations/{gym_id}", response_model=dict)
async def admin_update_location(
    gym_id: int,
    payload: AdminLocationUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    updates = []
    params: dict = {"gym_id": gym_id}
    if payload.gym_name is not None:
        updates.append("gym_name = :gym_name")
        params["gym_name"] = payload.gym_name
    if payload.address is not None:
        updates.append("address = :address")
        params["address"] = payload.address
    if payload.district is not None:
        updates.append("district = :district")
        params["district"] = payload.district
    if payload.phone is not None:
        updates.append("phone = :phone")
        params["phone"] = payload.phone
    if payload.facilities is not None:
        updates.append("facilities = :facilities")
        params["facilities"] = payload.facilities
    if payload.opening_time is not None:
        updates.append("opening_time = :opening_time")
        params["opening_time"] = payload.opening_time
    if payload.closing_time is not None:
        updates.append("closing_time = :closing_time")
        params["closing_time"] = payload.closing_time
    if payload.latitude is not None:
        updates.append("latitude = :latitude")
        params["latitude"] = payload.latitude
    if payload.longitude is not None:
        updates.append("longitude = :longitude")
        params["longitude"] = payload.longitude
    if payload.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = payload.is_active

    await _ensure_transaction(db)
    if updates:
        res = await db.execute(
            text(f"UPDATE gym SET {', '.join(updates)} WHERE gym_id = :gym_id"),
            params,
        )
        if res.rowcount == 0:
            await db.rollback()
            raise HTTPException(status_code=404, detail="Location not found")

    if payload.assigned_coach_ids is not None:
        await db.execute(
            text("UPDATE coach_service SET is_active = 0 WHERE gym_id = :gym_id"),
            {"gym_id": gym_id},
        )
        for coach_id in payload.assigned_coach_ids:
            await db.execute(
                text(
                    """
                    INSERT INTO coach_service (coach_id, gym_id, is_home_service, is_active)
                    VALUES (:coach_id, :gym_id, 0, 1)
                    ON DUPLICATE KEY UPDATE is_active = 1
                    """
                ),
                {"coach_id": coach_id, "gym_id": gym_id},
            )

    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_UPDATE_LOCATION', 'gym', :gym_id,
                    JSON_OBJECT('gym_id', :gym_id), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "gym_id": gym_id, "ip": ip},
    )
    await db.commit()

    res = await db.execute(text("SELECT * FROM gym WHERE gym_id = :id"), {"id": gym_id})
    row = dict(res.mappings().one())
    if row.get("opening_time") is not None:
        row["opening_time"] = str(row["opening_time"])
    if row.get("closing_time") is not None:
        row["closing_time"] = str(row["closing_time"])
    return row


@router.delete("/locations/{gym_id}", response_model=dict)
async def admin_delete_location(
    gym_id: int,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    check = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM booking
            WHERE gym_id = :gym_id
              AND status IN ('PENDING', 'CONFIRMED')
              AND booking_date >= CURDATE()
            """
        ),
        {"gym_id": gym_id},
    )
    if (check.scalar_one() or 0) > 0:
        raise HTTPException(status_code=409, detail="Cannot archive location with active upcoming bookings")

    await db.execute(
        text("UPDATE gym SET is_active = 0 WHERE gym_id = :gym_id"),
        {"gym_id": gym_id},
    )
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_ARCHIVE_LOCATION', 'gym', :gym_id,
                    JSON_OBJECT('is_active', 0), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "gym_id": gym_id, "ip": ip},
    )
    await db.commit()
    return {"success": True, "message": "Location archived", "gym_id": gym_id}


class LocationStatusUpdate(BaseModel):
    is_active: int  # 1 or 0


@router.patch("/locations/{gym_id}/status", response_model=dict)
async def update_location_status(
    gym_id: int,
    payload: LocationStatusUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    if payload.is_active not in (0, 1):
        raise HTTPException(status_code=422, detail="is_active must be 0 or 1")
    result = await db.execute(
        text("UPDATE gym SET is_active = :is_active WHERE gym_id = :gym_id"),
        {"is_active": payload.is_active, "gym_id": gym_id},
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Gym not found")
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'UPDATE_LOCATION_STATUS', 'gym', :gym_id,
                    JSON_OBJECT('is_active', :is_active), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "gym_id": gym_id,
            "is_active": payload.is_active,
            "ip": _get_client_ip(request),
        },
    )
    await db.commit()
    gym_result = await db.execute(
        text("SELECT * FROM gym WHERE gym_id = :gym_id"),
        {"gym_id": gym_id},
    )
    row = dict(gym_result.mappings().one())
    if row.get("opening_time") is not None:
        row["opening_time"] = str(row["opening_time"])
    if row.get("closing_time") is not None:
        row["closing_time"] = str(row["closing_time"])
    return row


# ---------------------------------------------------------------------------
# Bookings management
# ---------------------------------------------------------------------------


@router.get("/bookings", response_model=dict)
async def admin_list_bookings(
    search: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None),
    coach_id: int | None = Query(default=None, gt=0),
    member_id: int | None = Query(default=None, gt=0),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    offset = (page - 1) * page_size
    result = await db.execute(
        text(
            """
            SELECT b.booking_id, b.booking_date, b.start_time, b.end_time,
                   b.duration_minutes, b.break_minutes, b.service_mode, b.price, b.status,
                   b.created_at, b.cancelled_at, b.cancel_reason, b.cancelled_by,
                   b.member_id, b.coach_id, b.course_id, b.gym_id, b.package_id,
                   mu.display_name AS member_name, cu.display_name AS coach_name,
                   co.course_name, g.gym_name,
                   o.payment_status, o.final_amount, o.payment_method
            FROM booking b
            JOIN member m ON m.member_id = b.member_id
            JOIN users mu ON mu.user_id = m.user_id
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            LEFT JOIN gym g ON g.gym_id = b.gym_id
            LEFT JOIN orders o ON o.booking_id = b.booking_id
            WHERE (:status IS NULL OR b.status = :status)
              AND (:coach_id IS NULL OR b.coach_id = :coach_id)
              AND (:member_id IS NULL OR b.member_id = :member_id)
              AND (:date_from IS NULL OR b.booking_date >= :date_from)
              AND (:date_to IS NULL OR b.booking_date <= :date_to)
              AND (:search IS NULL OR mu.display_name LIKE CONCAT('%', :search, '%')
                   OR cu.display_name LIKE CONCAT('%', :search, '%')
                   OR co.course_name LIKE CONCAT('%', :search, '%'))
            ORDER BY b.booking_date DESC, b.start_time DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "status": status,
            "coach_id": coach_id,
            "member_id": member_id,
            "date_from": date_from,
            "date_to": date_to,
            "search": search,
            "limit": page_size,
            "offset": offset,
        },
    )
    count_result = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM booking b
            JOIN member m ON m.member_id = b.member_id
            JOIN users mu ON mu.user_id = m.user_id
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            WHERE (:status IS NULL OR b.status = :status)
              AND (:coach_id IS NULL OR b.coach_id = :coach_id)
              AND (:member_id IS NULL OR b.member_id = :member_id)
              AND (:date_from IS NULL OR b.booking_date >= :date_from)
              AND (:date_to IS NULL OR b.booking_date <= :date_to)
              AND (:search IS NULL OR mu.display_name LIKE CONCAT('%', :search, '%')
                   OR cu.display_name LIKE CONCAT('%', :search, '%')
                   OR co.course_name LIKE CONCAT('%', :search, '%'))
            """
        ),
        {
            "status": status,
            "coach_id": coach_id,
            "member_id": member_id,
            "date_from": date_from,
            "date_to": date_to,
            "search": search,
        },
    )
    total = int(count_result.scalar_one() or 0)
    items = []
    for r in result.mappings().all():
        d = dict(r)
        if d.get("start_time") is not None:
            d["start_time"] = str(d["start_time"])
        if d.get("end_time") is not None:
            d["end_time"] = str(d["end_time"])
        items.append(d)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/bookings/{booking_id}", response_model=dict)
async def admin_get_booking(
    booking_id: int,
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    result = await db.execute(
        text(
            """
            SELECT b.*,
                   mu.display_name AS member_name, mu.email AS member_email, mu.phone AS member_phone,
                   cu.display_name AS coach_name, cu.email AS coach_email, cu.phone AS coach_phone,
                   co.course_name, co.difficulty, co.default_duration,
                   g.gym_name, g.address AS gym_address, g.district AS gym_district,
                   o.order_id, o.payment_status, o.final_amount, o.payment_method, o.payment_time
            FROM booking b
            JOIN member m ON m.member_id = b.member_id
            JOIN users mu ON mu.user_id = m.user_id
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            LEFT JOIN gym g ON g.gym_id = b.gym_id
            LEFT JOIN orders o ON o.booking_id = b.booking_id
            WHERE b.booking_id = :booking_id
            """
        ),
        {"booking_id": booking_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    d = dict(row)
    if d.get("start_time") is not None:
        d["start_time"] = str(d["start_time"])
    if d.get("end_time") is not None:
        d["end_time"] = str(d["end_time"])
    return d


class AdminBookingCreate(BaseModel):
    member_id: int = Field(gt=0)
    coach_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    booking_date: date
    start_time: str
    duration_minutes: int = Field(default=60, ge=10)
    break_minutes: int = Field(default=10)
    service_mode: Literal["GYM", "HOME"] = "GYM"
    gym_id: int | None = None
    service_district: Literal["NIMMAN", "OLD_CITY", "CENTRAL", "MAE_RIM", "HANG_DONG"] | None = None
    service_address: str | None = None
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    status: Literal["PENDING", "CONFIRMED"] = "CONFIRMED"
    package_id: int | None = None
    payment_method: Literal["PROMPTPAY", "CARD", "CASH", "PACKAGE_CREDIT"] = "PROMPTPAY"


@router.post("/bookings", response_model=dict, status_code=status.HTTP_201_CREATED)
async def admin_create_booking(
    payload: AdminBookingCreate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
    ddl_engine=Depends(get_ddl_engine),
) -> dict:
    ip = _get_client_ip(request)
    parts = payload.start_time.split(":")
    if len(parts) < 2:
        raise HTTPException(status_code=422, detail="Invalid start_time format (HH:MM required)")
    start_minute = int(parts[1])
    if start_minute % 10 != 0:
        raise HTTPException(status_code=422, detail="start_time minute must align with 10-minute grid")
    if payload.duration_minutes % 10 != 0:
        raise HTTPException(status_code=422, detail="duration_minutes must be a multiple of 10")
    if payload.break_minutes not in (10, 20, 30):
        raise HTTPException(status_code=422, detail="break_minutes must be 10, 20, or 30")

    parsed_time = time(int(parts[0]), int(parts[1]))
    start_dt = datetime.combine(payload.booking_date, parsed_time)
    end_dt = start_dt + timedelta(minutes=payload.duration_minutes)
    end_time_val = end_dt.time()
    slot_end_dt = start_dt + timedelta(minutes=payload.duration_minutes + payload.break_minutes)

    sched = ScheduleService(db, ddl_engine)
    table_name = await sched.get_table_name(payload.coach_id)

    # Ensure dynamic schedule table exists
    await sched.create_schedule_table(payload.coach_id)

    await db.rollback()
    await _ensure_transaction(db)

    # Pre-populate and lock slots
    cur = start_dt
    while cur < slot_end_dt:
        await db.execute(
            text(f"INSERT IGNORE INTO `{table_name}` (slot_start, status) VALUES (:st, 'AVAILABLE')"),
            {"st": cur},
        )
        cur += timedelta(minutes=10)

    slots_res = await db.execute(
        text(
            f"""
            SELECT slot_start, status
            FROM `{table_name}`
            WHERE slot_start >= :s_start AND slot_start < :s_end
            FOR UPDATE
            """
        ),
        {"s_start": start_dt, "s_end": slot_end_dt},
    )
    locked_slots = slots_res.mappings().all()
    if any(s["status"] != "AVAILABLE" for s in locked_slots):
        await db.rollback()
        raise HTTPException(status_code=409, detail="Coach schedule slot conflict at the requested time")

    # Insert booking
    booking_res = await db.execute(
        text(
            """
            INSERT INTO booking
                (member_id, coach_id, course_id, gym_id, package_id, booking_date,
                 start_time, end_time, duration_minutes, break_minutes, service_mode,
                 service_district, service_address, price, status)
            VALUES
                (:member_id, :coach_id, :course_id, :gym_id, :package_id, :booking_date,
                 :start_time, :end_time, :duration_minutes, :break_minutes, :service_mode,
                 :service_district, :service_address, :price, :status)
            """
        ),
        {
            "member_id": payload.member_id,
            "coach_id": payload.coach_id,
            "course_id": payload.course_id,
            "gym_id": payload.gym_id if payload.service_mode == "GYM" else None,
            "package_id": payload.package_id,
            "booking_date": payload.booking_date,
            "start_time": parsed_time,
            "end_time": end_time_val,
            "duration_minutes": payload.duration_minutes,
            "break_minutes": payload.break_minutes,
            "service_mode": payload.service_mode,
            "service_district": payload.service_district if payload.service_mode == "HOME" else None,
            "service_address": payload.service_address if payload.service_mode == "HOME" else None,
            "price": payload.price,
            "status": payload.status,
        },
    )
    booking_id = booking_res.lastrowid

    # Mark slots booked
    await db.execute(
        text(
            f"""
            UPDATE `{table_name}`
            SET status = 'BOOKED', booking_id = :bid
            WHERE slot_start >= :s_start AND slot_start < :s_end
            """
        ),
        {"bid": booking_id, "s_start": start_dt, "s_end": slot_end_dt},
    )

    # Orders record
    order_status = "PAID" if payload.status == "CONFIRMED" else "UNPAID"
    await db.execute(
        text(
            """
            INSERT INTO orders
                (order_type, booking_id, total_amount, discount, final_amount,
                 payment_method, payment_status, payment_time)
            VALUES
                ('BOOKING', :bid, :price, 0.00, :price, :pmethod, :pstatus,
                 CASE WHEN :pstatus = 'PAID' THEN NOW() ELSE NULL END)
            """
        ),
        {
            "bid": booking_id,
            "price": payload.price,
            "pmethod": payload.payment_method,
            "pstatus": order_status,
        },
    )

    # If package used, decrement remaining
    if payload.package_id:
        await db.execute(
            text(
                """
                UPDATE member_package
                SET remaining_sessions = remaining_sessions - 1
                WHERE package_id = :pkg_id AND remaining_sessions > 0
                """
            ),
            {"pkg_id": payload.package_id},
        )

    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_CREATE_BOOKING', 'booking', :bid,
                    JSON_OBJECT('booking_id', :bid, 'coach_id', :cid, 'member_id', :mid), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "bid": booking_id,
            "cid": payload.coach_id,
            "mid": payload.member_id,
            "ip": ip,
        },
    )
    await db.commit()

    created = await db.execute(
        text("SELECT * FROM booking WHERE booking_id = :id"),
        {"id": booking_id},
    )
    row = dict(created.mappings().one())
    if row.get("start_time") is not None:
        row["start_time"] = str(row["start_time"])
    if row.get("end_time") is not None:
        row["end_time"] = str(row["end_time"])
    return row


class AdminBookingUpdate(BaseModel):
    booking_date: date | None = None
    start_time: str | None = None
    duration_minutes: int | None = None
    break_minutes: int | None = None
    coach_id: int | None = None
    course_id: int | None = None
    gym_id: int | None = None
    price: Decimal | None = None
    status: Literal["PENDING", "CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW"] | None = None


@router.put("/bookings/{booking_id}", response_model=dict)
async def admin_update_booking(
    booking_id: int,
    payload: AdminBookingUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    cur_res = await db.execute(
        text("SELECT * FROM booking WHERE booking_id = :id"),
        {"id": booking_id},
    )
    curr = cur_res.mappings().one_or_none()
    if curr is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    updates = []
    params: dict = {"id": booking_id}
    if payload.booking_date is not None:
        updates.append("booking_date = :bdate")
        params["bdate"] = payload.booking_date
    if payload.start_time is not None:
        parts = payload.start_time.split(":")
        parsed_t = time(int(parts[0]), int(parts[1]))
        updates.append("start_time = :stime")
        params["stime"] = parsed_t
        dur = payload.duration_minutes or curr["duration_minutes"]
        end_t = (datetime.combine(payload.booking_date or curr["booking_date"], parsed_t) + timedelta(minutes=dur)).time()
        updates.append("end_time = :etime")
        params["etime"] = end_t
    if payload.duration_minutes is not None:
        updates.append("duration_minutes = :dur")
        params["dur"] = payload.duration_minutes
    if payload.break_minutes is not None:
        updates.append("break_minutes = :bmin")
        params["bmin"] = payload.break_minutes
    if payload.coach_id is not None:
        updates.append("coach_id = :cid")
        params["cid"] = payload.coach_id
    if payload.course_id is not None:
        updates.append("course_id = :crsid")
        params["crsid"] = payload.course_id
    if payload.gym_id is not None:
        updates.append("gym_id = :gid")
        params["gid"] = payload.gym_id
    if payload.price is not None:
        updates.append("price = :price")
        params["price"] = payload.price
    if payload.status is not None:
        updates.append("status = :status")
        params["status"] = payload.status

    if updates:
        await db.execute(
            text(f"UPDATE booking SET {', '.join(updates)} WHERE booking_id = :id"),
            params,
        )
        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_RESCHEDULE_BOOKING', 'booking', :id,
                        JSON_OBJECT('booking_id', :id), :ip)
                """
            ),
            {"admin_id": admin["user_id"], "id": booking_id, "ip": ip},
        )
        await db.commit()

    updated = await db.execute(
        text("SELECT * FROM booking WHERE booking_id = :id"),
        {"id": booking_id},
    )
    row = dict(updated.mappings().one())
    if row.get("start_time") is not None:
        row["start_time"] = str(row["start_time"])
    if row.get("end_time") is not None:
        row["end_time"] = str(row["end_time"])
    return row


class BookingStatusUpdate(BaseModel):
    status: Literal["PENDING", "CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW"]
    cancel_reason: str | None = None
    cancelled_by: Literal["MEMBER", "COACH", "ADMIN", "SYSTEM"] | None = "ADMIN"


@router.patch("/bookings/{booking_id}/status", response_model=dict)
async def update_booking_status(
    booking_id: int,
    payload: BookingStatusUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    extra_updates = ""
    extra_params: dict = {"bid": booking_id, "status": payload.status}
    if payload.status == "COMPLETED":
        extra_updates = ", completed_at = NOW()"
    elif payload.status == "CANCELLED":
        extra_updates = ", cancelled_at = NOW(), cancelled_by = :cby, cancel_reason = :creason"
        extra_params["cby"] = payload.cancelled_by or "ADMIN"
        extra_params["creason"] = payload.cancel_reason

    res = await db.execute(
        text(f"UPDATE booking SET status = :status {extra_updates} WHERE booking_id = :bid"),
        extra_params,
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Booking not found")

    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'UPDATE_BOOKING_STATUS', 'booking', :bid,
                    JSON_OBJECT('status', :status), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "bid": booking_id, "status": payload.status, "ip": ip},
    )
    await db.commit()

    updated = await db.execute(
        text("SELECT * FROM booking WHERE booking_id = :id"),
        {"id": booking_id},
    )
    row = dict(updated.mappings().one())
    if row.get("start_time") is not None:
        row["start_time"] = str(row["start_time"])
    if row.get("end_time") is not None:
        row["end_time"] = str(row["end_time"])
    return row


class AdminBookingCancelPayload(BaseModel):
    cancel_reason: str = "Admin cancellation"
    refund_issued: bool = True


@router.post("/bookings/{booking_id}/cancel", response_model=dict)
async def admin_cancel_booking(
    booking_id: int,
    payload: AdminBookingCancelPayload,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    b_res = await db.execute(
        text("SELECT * FROM booking WHERE booking_id = :id"),
        {"id": booking_id},
    )
    b = b_res.mappings().one_or_none()
    if b is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    await _ensure_transaction(db)
    await db.execute(
        text(
            """
            UPDATE booking
            SET status = 'CANCELLED', cancelled_by = 'ADMIN', cancelled_at = NOW(),
                cancel_reason = :reason
            WHERE booking_id = :bid
            """
        ),
        {"bid": booking_id, "reason": payload.cancel_reason},
    )

    if payload.refund_issued:
        await db.execute(
            text(
                """
                UPDATE orders
                SET payment_status = 'REFUNDED', refunded_at = NOW()
                WHERE booking_id = :bid
                """
            ),
            {"bid": booking_id},
        )
        if b["package_id"]:
            await db.execute(
                text(
                    """
                    UPDATE member_package
                    SET remaining_sessions = remaining_sessions + 1
                    WHERE package_id = :pid
                    """
                ),
                {"pid": b["package_id"]},
            )

    # Release slots in schedule table
    try:
        table_name = await ScheduleService(db).get_table_name(b["coach_id"])
        await db.execute(
            text(
                f"""
                UPDATE `{table_name}`
                SET status = 'AVAILABLE', booking_id = NULL
                WHERE booking_id = :bid
                """
            ),
            {"bid": booking_id},
        )
    except Exception:
        pass

    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_CANCEL_BOOKING', 'booking', :bid,
                    JSON_OBJECT('refund_issued', :refund, 'reason', :reason), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "bid": booking_id,
            "refund": payload.refund_issued,
            "reason": payload.cancel_reason,
            "ip": ip,
        },
    )
    await db.commit()

    updated = await db.execute(
        text("SELECT * FROM booking WHERE booking_id = :id"),
        {"id": booking_id},
    )
    row = dict(updated.mappings().one())
    if row.get("start_time") is not None:
        row["start_time"] = str(row["start_time"])
    if row.get("end_time") is not None:
        row["end_time"] = str(row["end_time"])
    return row


# ---------------------------------------------------------------------------
# Package catalog management
# ---------------------------------------------------------------------------


class AdminPackageCreate(BaseModel):
    package_type: str = Field(min_length=1, max_length=50)
    paid_sessions: int = Field(gt=0)
    bonus_sessions: int = Field(default=0, ge=0)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    validity_days: int = Field(gt=0)
    is_active: int = 1


@router.post("/packages", response_model=dict, status_code=status.HTTP_201_CREATED)
async def admin_create_package(
    payload: AdminPackageCreate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    try:
        await db.execute(
            text(
                """
                INSERT INTO package_catalog
                    (package_type, paid_sessions, bonus_sessions, price, validity_days, is_active)
                VALUES
                    (:package_type, :paid_sessions, :bonus_sessions, :price, :validity_days, :is_active)
                """
            ),
            {
                "package_type": payload.package_type,
                "paid_sessions": payload.paid_sessions,
                "bonus_sessions": payload.bonus_sessions,
                "price": payload.price,
                "validity_days": payload.validity_days,
                "is_active": payload.is_active,
            },
        )
        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_CREATE_PACKAGE', 'package_catalog', NULL,
                        JSON_OBJECT('package_type', :package_type), :ip)
                """
            ),
            {"admin_id": admin["user_id"], "package_type": payload.package_type, "ip": ip},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Package type already exists") from None

    res = await db.execute(
        text("SELECT * FROM package_catalog WHERE package_type = :ptype"),
        {"ptype": payload.package_type},
    )
    return dict(res.mappings().one())


class AdminPackageUpdate(BaseModel):
    paid_sessions: int | None = Field(default=None, gt=0)
    bonus_sessions: int | None = Field(default=None, ge=0)
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    validity_days: int | None = Field(default=None, gt=0)
    is_active: int | None = None


@router.put("/packages/{package_type}", response_model=dict)
async def admin_update_package(
    package_type: str,
    payload: AdminPackageUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    updates = []
    params: dict = {"ptype": package_type}
    if payload.paid_sessions is not None:
        updates.append("paid_sessions = :psess")
        params["psess"] = payload.paid_sessions
    if payload.bonus_sessions is not None:
        updates.append("bonus_sessions = :bsess")
        params["bsess"] = payload.bonus_sessions
    if payload.price is not None:
        updates.append("price = :price")
        params["price"] = payload.price
    if payload.validity_days is not None:
        updates.append("validity_days = :vdays")
        params["vdays"] = payload.validity_days
    if payload.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = payload.is_active

    if updates:
        res = await db.execute(
            text(f"UPDATE package_catalog SET {', '.join(updates)} WHERE package_type = :ptype"),
            params,
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Package type not found")
        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_UPDATE_PACKAGE', 'package_catalog', NULL,
                        JSON_OBJECT('package_type', :ptype), :ip)
                """
            ),
            {"admin_id": admin["user_id"], "ptype": package_type, "ip": ip},
        )
        await db.commit()

    res = await db.execute(
        text("SELECT * FROM package_catalog WHERE package_type = :ptype"),
        {"ptype": package_type},
    )
    return dict(res.mappings().one())


@router.delete("/packages/{package_type}", response_model=dict)
async def admin_delete_package(
    package_type: str,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    res = await db.execute(
        text("UPDATE package_catalog SET is_active = 0 WHERE package_type = :ptype"),
        {"ptype": package_type},
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Package type not found")
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_DEACTIVATE_PACKAGE', 'package_catalog', NULL,
                    JSON_OBJECT('package_type', :ptype), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "ptype": package_type, "ip": ip},
    )
    await db.commit()
    return {"success": True, "message": "Package deactivated", "package_type": package_type}


class PackageCatalogStatusUpdate(BaseModel):
    is_active: int  # 1 or 0


@router.patch("/packages/{package_type}/status", response_model=dict)
async def update_package_catalog_status(
    package_type: str,
    payload: PackageCatalogStatusUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    if payload.is_active not in (0, 1):
        raise HTTPException(status_code=422, detail="is_active must be 0 or 1")
    result = await db.execute(
        text("UPDATE package_catalog SET is_active = :is_active WHERE package_type = :package_type"),
        {"is_active": payload.is_active, "package_type": package_type},
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Package catalog item not found")
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'UPDATE_PACKAGE_CATALOG_STATUS', 'package_catalog', NULL,
                    JSON_OBJECT('package_type', :package_type, 'is_active', :is_active), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "package_type": package_type,
            "is_active": payload.is_active,
            "ip": _get_client_ip(request),
        },
    )
    await db.commit()
    pkg_result = await db.execute(
        text("SELECT * FROM package_catalog WHERE package_type = :package_type"),
        {"package_type": package_type},
    )
    return dict(pkg_result.mappings().one())


# ---------------------------------------------------------------------------
# KPI Management & Engine
# ---------------------------------------------------------------------------


@router.get("/kpi", response_model=dict)
async def admin_kpi_overview(
    year: int | None = Query(default=None, ge=2020, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    rules = await db.execute(
        text(
            """
            SELECT coach_level, min_monthly_hours, min_avg_rating, min_retention_rate
            FROM kpi_rule
            ORDER BY FIELD(coach_level, 'BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'MASTER')
            """
        )
    )
    kpi_records = await db.execute(
        text(
            """
            SELECT kr.kpi_record_id, kr.kpi_year, kr.kpi_month,
                   kr.total_hours, kr.completed_sessions,
                   kr.avg_rating, kr.retention_rate,
                   kr.target_hours, kr.target_avg_rating, kr.target_retention_rate,
                   kr.is_achieved, kr.calculated_at,
                   c.coach_id, c.coach_level,
                   u.display_name AS coach_name
            FROM coach_kpi_record kr
            JOIN coach c ON c.coach_id = kr.coach_id
            JOIN users u ON u.user_id = c.user_id
            WHERE (:year IS NULL OR kr.kpi_year = :year)
              AND (:month IS NULL OR kr.kpi_month = :month)
            ORDER BY kr.kpi_year DESC, kr.kpi_month DESC, u.display_name
            LIMIT 100
            """
        ),
        {"year": year, "month": month},
    )
    return {
        "kpi_rules": [dict(row) for row in rules.mappings().all()],
        "records": [dict(row) for row in kpi_records.mappings().all()],
    }


@router.get("/kpi/records", response_model=list[dict])
async def admin_list_kpi_records(
    year: int | None = Query(default=None, ge=2020, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    coach_id: int | None = Query(default=None, gt=0),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT kr.*, c.coach_no, c.coach_level, u.display_name AS coach_name
            FROM coach_kpi_record kr
            JOIN coach c ON c.coach_id = kr.coach_id
            JOIN users u ON u.user_id = c.user_id
            WHERE (:year IS NULL OR kr.kpi_year = :year)
              AND (:month IS NULL OR kr.kpi_month = :month)
              AND (:cid IS NULL OR kr.coach_id = :cid)
            ORDER BY kr.kpi_year DESC, kr.kpi_month DESC, u.display_name
            """
        ),
        {"year": year, "month": month, "cid": coach_id},
    )
    return [dict(row) for row in result.mappings().all()]


class KpiRecordOverride(BaseModel):
    total_hours: float | None = None
    avg_rating: float | None = None
    retention_rate: float | None = None
    is_achieved: int | None = Field(default=None, ge=0, le=1)


@router.put("/kpi/records/{record_id}", response_model=dict)
async def admin_override_kpi_record(
    record_id: int,
    payload: KpiRecordOverride,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    updates = []
    params: dict = {"rid": record_id}
    if payload.total_hours is not None:
        updates.append("total_hours = :thours")
        params["thours"] = payload.total_hours
    if payload.avg_rating is not None:
        updates.append("avg_rating = :arating")
        params["arating"] = payload.avg_rating
    if payload.retention_rate is not None:
        updates.append("retention_rate = :rrate")
        params["rrate"] = payload.retention_rate
    if payload.is_achieved is not None:
        updates.append("is_achieved = :iachieved")
        params["iachieved"] = payload.is_achieved

    if updates:
        res = await db.execute(
            text(f"UPDATE coach_kpi_record SET {', '.join(updates)} WHERE kpi_record_id = :rid"),
            params,
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="KPI record not found")
        await db.execute(
            text(
                """
                INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
                VALUES (:admin_id, 'ADMIN_OVERRIDE_KPI', 'coach_kpi_record', :rid,
                        JSON_OBJECT('record_id', :rid), :ip)
                """
            ),
            {"admin_id": admin["user_id"], "rid": record_id, "ip": ip},
        )
        await db.commit()

    result = await db.execute(
        text("SELECT * FROM coach_kpi_record WHERE kpi_record_id = :rid"),
        {"rid": record_id},
    )
    return dict(result.mappings().one())


@router.post("/kpi/recalculate", response_model=dict)
async def admin_recalculate_kpi(
    request: Request,
    year: int = Query(ge=2020, le=2100),
    month: int = Query(ge=1, le=12),
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    # Fetch active coaches
    coaches_res = await db.execute(text("SELECT coach_id, coach_level FROM coach WHERE status = 'ACTIVE'"))
    coaches = coaches_res.mappings().all()

    # Fetch rules
    rules_res = await db.execute(text("SELECT * FROM kpi_rule"))
    rules_map = {r["coach_level"]: r for r in rules_res.mappings().all()}

    recalculated = 0
    await _ensure_transaction(db)
    for c in coaches:
        cid = c["coach_id"]
        lvl = c["coach_level"]
        rule = rules_map.get(lvl)
        if not rule:
            continue

        # Completed bookings
        b_res = await db.execute(
            text(
                """
                SELECT COUNT(*) AS total_sessions, COALESCE(SUM(duration_minutes), 0) AS total_mins,
                       COUNT(DISTINCT member_id) AS distinct_members
                FROM booking
                WHERE coach_id = :cid
                  AND status = 'COMPLETED'
                  AND YEAR(booking_date) = :yr AND MONTH(booking_date) = :mo
                """
            ),
            {"cid": cid, "yr": year, "mo": month},
        )
        b_data = dict(b_res.mappings().one())
        total_hours = round(float(b_data["total_mins"]) / 60.0, 2)
        completed_sessions = int(b_data["total_sessions"])

        # Average rating
        r_res = await db.execute(
            text(
                """
                SELECT COALESCE(AVG(rc.avg_rating), 5.0) AS avg_rating
                FROM review_coach rc
                JOIN booking b ON b.booking_id = rc.booking_id
                WHERE b.coach_id = :cid
                  AND YEAR(b.booking_date) = :yr AND MONTH(b.booking_date) = :mo
                """
            ),
            {"cid": cid, "yr": year, "mo": month},
        )
        avg_rating = round(float(r_res.scalar_one() or 5.0), 2)

        # Retention rate: members with >= 2 bookings in this month vs total
        ret_res = await db.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM (
                        SELECT member_id FROM booking
                        WHERE coach_id = :cid AND status = 'COMPLETED'
                          AND YEAR(booking_date) = :yr AND MONTH(booking_date) = :mo
                        GROUP BY member_id HAVING COUNT(*) > 1
                    ) AS repeat_members) AS repeat_count,
                    (SELECT COUNT(DISTINCT member_id) FROM booking
                     WHERE coach_id = :cid AND status = 'COMPLETED'
                       AND YEAR(booking_date) = :yr AND MONTH(booking_date) = :mo) AS total_members
                """
            ),
            {"cid": cid, "yr": year, "mo": month},
        )
        ret_data = dict(ret_res.mappings().one())
        tot_m = ret_data.get("total_members") or 0
        rep_m = ret_data.get("repeat_count") or 0
        retention_rate = round((rep_m / tot_m * 100.0), 2) if tot_m > 0 else 75.0

        is_achieved = (
            1
            if (
                total_hours >= float(rule["min_monthly_hours"])
                and avg_rating >= float(rule["min_avg_rating"])
                and retention_rate >= float(rule["min_retention_rate"])
            )
            else 0
        )

        await db.execute(
            text(
                """
                INSERT INTO coach_kpi_record
                    (coach_id, kpi_year, kpi_month, total_hours, completed_sessions,
                     avg_rating, retention_rate, target_hours, target_avg_rating,
                     target_retention_rate, is_achieved, calculated_at)
                VALUES
                    (:cid, :yr, :mo, :thours, :csess, :arating, :rrate,
                     :targhours, :targrating, :targret, :iachieved, NOW())
                ON DUPLICATE KEY UPDATE
                    total_hours = VALUES(total_hours),
                    completed_sessions = VALUES(completed_sessions),
                    avg_rating = VALUES(avg_rating),
                    retention_rate = VALUES(retention_rate),
                    target_hours = VALUES(target_hours),
                    target_avg_rating = VALUES(target_avg_rating),
                    target_retention_rate = VALUES(target_retention_rate),
                    is_achieved = VALUES(is_achieved),
                    calculated_at = NOW()
                """
            ),
            {
                "cid": cid,
                "yr": year,
                "mo": month,
                "thours": total_hours,
                "csess": completed_sessions,
                "arating": avg_rating,
                "rrate": retention_rate,
                "targhours": rule["min_monthly_hours"],
                "targrating": rule["min_avg_rating"],
                "targret": rule["min_retention_rate"],
                "iachieved": is_achieved,
            },
        )
        recalculated += 1

    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'ADMIN_RECALCULATE_KPI', 'coach_kpi_record', NULL,
                    JSON_OBJECT('year', :yr, 'month', :mo, 'recalculated', :rec), :ip)
            """
        ),
        {"admin_id": admin["user_id"], "yr": year, "mo": month, "rec": recalculated, "ip": ip},
    )
    await db.commit()
    return {"success": True, "recalculated_coaches": recalculated, "year": year, "month": month}


class KpiRuleUpdate(BaseModel):
    min_monthly_hours: float
    min_avg_rating: float
    min_retention_rate: float


@router.put("/kpi/rules/{coach_level}", response_model=dict)
async def update_kpi_rule(
    coach_level: str,
    payload: KpiRuleUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    if coach_level not in ("BEGINNER", "INTERMEDIATE", "ADVANCED", "MASTER"):
        raise HTTPException(status_code=422, detail="Invalid coach_level")
    await db.execute(
        text(
            """
            UPDATE kpi_rule
            SET min_monthly_hours = :hours,
                min_avg_rating = :rating,
                min_retention_rate = :retention
            WHERE coach_level = :coach_level
            """
        ),
        {
            "coach_level": coach_level,
            "hours": payload.min_monthly_hours,
            "rating": payload.min_avg_rating,
            "retention": payload.min_retention_rate,
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'UPDATE_KPI_RULE', 'kpi_rule', NULL,
                    JSON_OBJECT('coach_level', :coach_level, 'hours', :hours, 'rating', :rating, 'retention', :retention), :ip)
            """
        ),
        {
            "admin_id": admin["user_id"],
            "coach_level": coach_level,
            "hours": payload.min_monthly_hours,
            "rating": payload.min_avg_rating,
            "retention": payload.min_retention_rate,
            "ip": _get_client_ip(request),
        },
    )
    await db.commit()
    rule_result = await db.execute(
        text("SELECT * FROM kpi_rule WHERE coach_level = :coach_level"),
        {"coach_level": coach_level},
    )
    return dict(rule_result.mappings().one())


# ---------------------------------------------------------------------------
# Revenue summary & Reports
# ---------------------------------------------------------------------------


@router.get("/revenue", response_model=dict)
async def admin_revenue(
    days: int = Query(default=30, ge=7, le=365),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    by_type = await db.execute(
        text(
            """
            SELECT order_type, payment_method,
                   COUNT(*) AS order_count,
                   SUM(final_amount) AS total_revenue
            FROM orders
            WHERE payment_status = 'PAID'
              AND payment_time >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY order_type, payment_method
            ORDER BY total_revenue DESC
            """
        ),
        {"days": days},
    )
    daily = await db.execute(
        text(
            """
            SELECT DATE(payment_time) AS payment_date,
                   COUNT(*) AS order_count,
                   SUM(final_amount) AS revenue
            FROM orders
            WHERE payment_status = 'PAID'
              AND payment_time >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY DATE(payment_time)
            ORDER BY payment_date
            """
        ),
        {"days": days},
    )
    return {
        "by_type": [dict(row) for row in by_type.mappings().all()],
        "daily": [dict(row) for row in daily.mappings().all()],
        "period_days": days,
    }


class ReportGeneratePayload(BaseModel):
    report_name: str = "Performance & Utilization Report"
    date_from: date
    date_to: date
    group_by: Literal["coach", "course", "gym", "day"] = "coach"
    measures: list[str] = Field(default_factory=lambda: ["bookings", "revenue", "retention", "rating"])


@router.post("/reports/generate", response_model=dict)
async def admin_generate_report(
    payload: ReportGeneratePayload,
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    summary_res = await db.execute(
        text(
            """
            SELECT
                COUNT(b.booking_id) AS total_bookings,
                SUM(CASE WHEN b.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_bookings,
                SUM(CASE WHEN b.status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_bookings,
                COALESCE(SUM(o.final_amount), 0) AS total_revenue
            FROM booking b
            LEFT JOIN orders o ON o.booking_id = b.booking_id AND o.payment_status = 'PAID'
            WHERE b.booking_date >= :dfrom AND b.booking_date <= :dto
            """
        ),
        {"dfrom": payload.date_from, "dto": payload.date_to},
    )
    summary = dict(summary_res.mappings().one())

    # Breakdown by coach
    if payload.group_by == "coach":
        bk_res = await db.execute(
            text(
                """
                SELECT c.coach_id, u.display_name AS label, c.coach_level,
                       COUNT(b.booking_id) AS bookings,
                       COALESCE(SUM(o.final_amount), 0) AS revenue,
                       COALESCE(AVG(rc.avg_rating), 5.0) AS rating
                FROM coach c
                JOIN users u ON u.user_id = c.user_id
                LEFT JOIN booking b ON b.coach_id = c.coach_id
                    AND b.booking_date >= :dfrom AND b.booking_date <= :dto
                LEFT JOIN orders o ON o.booking_id = b.booking_id AND o.payment_status = 'PAID'
                LEFT JOIN review_coach rc ON rc.booking_id = b.booking_id
                GROUP BY c.coach_id, u.display_name, c.coach_level
                ORDER BY revenue DESC
                """
            ),
            {"dfrom": payload.date_from, "dto": payload.date_to},
        )
    elif payload.group_by == "course":
        bk_res = await db.execute(
            text(
                """
                SELECT cr.course_id, cr.course_name AS label, cr.difficulty,
                       COUNT(b.booking_id) AS bookings,
                       COALESCE(SUM(o.final_amount), 0) AS revenue,
                       COALESCE(AVG(rc.avg_rating), 5.0) AS rating
                FROM course cr
                LEFT JOIN booking b ON b.course_id = cr.course_id
                    AND b.booking_date >= :dfrom AND b.booking_date <= :dto
                LEFT JOIN orders o ON o.booking_id = b.booking_id AND o.payment_status = 'PAID'
                LEFT JOIN review_coach rc ON rc.booking_id = b.booking_id
                GROUP BY cr.course_id, cr.course_name, cr.difficulty
                ORDER BY revenue DESC
                """
            ),
            {"dfrom": payload.date_from, "dto": payload.date_to},
        )
    else:
        bk_res = await db.execute(
            text(
                """
                SELECT b.booking_date AS label,
                       COUNT(b.booking_id) AS bookings,
                       COALESCE(SUM(o.final_amount), 0) AS revenue,
                       COALESCE(AVG(rc.avg_rating), 5.0) AS rating
                FROM booking b
                LEFT JOIN orders o ON o.booking_id = b.booking_id AND o.payment_status = 'PAID'
                LEFT JOIN review_coach rc ON rc.booking_id = b.booking_id
                WHERE b.booking_date >= :dfrom AND b.booking_date <= :dto
                GROUP BY b.booking_date
                ORDER BY b.booking_date
                """
            ),
            {"dfrom": payload.date_from, "dto": payload.date_to},
        )
    breakdown = [dict(row) for row in bk_res.mappings().all()]

    return {
        "report_name": payload.report_name,
        "date_from": str(payload.date_from),
        "date_to": str(payload.date_to),
        "group_by": payload.group_by,
        "summary": summary,
        "breakdown": breakdown,
    }


@router.get("/reports/export")
async def admin_export_report(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
):
    result = await db.execute(
        text(
            """
            SELECT b.booking_id, b.booking_date, b.start_time, b.end_time,
                   mu.display_name AS member_name, cu.display_name AS coach_name,
                   co.course_name, g.gym_name, b.status, b.price,
                   o.payment_status, o.final_amount
            FROM booking b
            JOIN member m ON m.member_id = b.member_id
            JOIN users mu ON mu.user_id = m.user_id
            JOIN coach c ON c.coach_id = b.coach_id
            JOIN users cu ON cu.user_id = c.user_id
            JOIN course co ON co.course_id = b.course_id
            LEFT JOIN gym g ON g.gym_id = b.gym_id
            LEFT JOIN orders o ON o.booking_id = b.booking_id
            WHERE (:dfrom IS NULL OR b.booking_date >= :dfrom)
              AND (:dto IS NULL OR b.booking_date <= :dto)
            ORDER BY b.booking_date DESC, b.start_time DESC
            """
        ),
        {"dfrom": date_from, "dto": date_to},
    )
    rows = result.mappings().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Booking ID", "Date", "Start Time", "End Time", "Member", "Coach",
        "Course", "Gym", "Status", "Price", "Payment Status", "Final Amount"
    ])
    for r in rows:
        writer.writerow([
            r["booking_id"], r["booking_date"], str(r["start_time"]), str(r["end_time"]),
            r["member_name"], r["coach_name"], r["course_name"], r["gym_name"] or "Home Service",
            r["status"], float(r["price"]), r["payment_status"] or "UNPAID", float(r["final_amount"] or 0.0)
        ])
    csv_content = "\ufeff" + output.getvalue()
    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fitbooking_report.csv"},
    )


# ---------------------------------------------------------------------------
# Platform Settings
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=dict)
async def admin_get_settings(
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    res = await db.execute(
        text("SELECT setting_value FROM system_settings WHERE setting_key = 'platform'")
    )
    val = res.scalar_one_or_none()
    if val:
        if isinstance(val, str):
            return json.loads(val)
        return dict(val)
    return {
        "require_coach_verification": True,
        "booking_reminder_hours": 24,
        "package_catalogue_enabled": True,
        "audit_logging_enabled": True,
    }


class AdminSettingsUpdate(BaseModel):
    require_coach_verification: bool | None = None
    booking_reminder_hours: int | None = None
    package_catalogue_enabled: bool | None = None
    audit_logging_enabled: bool | None = None


@router.patch("/settings", response_model=dict)
async def admin_update_settings(
    payload: AdminSettingsUpdate,
    request: Request,
    admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    ip = _get_client_ip(request)
    current = await admin_get_settings(_=admin, db=db)
    if payload.require_coach_verification is not None:
        current["require_coach_verification"] = payload.require_coach_verification
    if payload.booking_reminder_hours is not None:
        current["booking_reminder_hours"] = payload.booking_reminder_hours
    if payload.package_catalogue_enabled is not None:
        current["package_catalogue_enabled"] = payload.package_catalogue_enabled
    if payload.audit_logging_enabled is not None:
        current["audit_logging_enabled"] = payload.audit_logging_enabled

    json_str = json.dumps(current)
    await db.execute(
        text(
            """
            INSERT INTO system_settings (setting_key, setting_value)
            VALUES ('platform', :val)
            ON DUPLICATE KEY UPDATE setting_value = :val
            """
        ),
        {"val": json_str},
    )
    await db.execute(
        text(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
            VALUES (:admin_id, 'UPDATE_PLATFORM_SETTINGS', 'system_settings', NULL,
                    :val, :ip)
            """
        ),
        {"admin_id": admin["user_id"], "val": json_str, "ip": ip},
    )
    await db.commit()
    return current
