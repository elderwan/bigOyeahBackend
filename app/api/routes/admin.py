from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_app_db

router = APIRouter()


async def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


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
                (SELECT COUNT(*) FROM coach WHERE status = 'ACTIVE') AS active_coaches,
                (SELECT COUNT(*) FROM booking
                 WHERE created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)) AS total_bookings,
                (SELECT COALESCE(SUM(final_amount), 0) FROM orders
                 WHERE payment_status = 'PAID'
                   AND payment_time >= DATE_SUB(NOW(), INTERVAL :days DAY)) AS revenue
            """
        ),
        {"days": days},
    )
    trend = await db.execute(
        text(
            """
            SELECT booking_date, COUNT(*) AS booking_count
            FROM booking
            WHERE booking_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
            GROUP BY booking_date
            ORDER BY booking_date
            """
        ),
        {"days": days},
    )
    return {
        "totals": dict(totals.mappings().one()),
        "booking_trend": [dict(row) for row in trend.mappings().all()],
    }


@router.get("/audit-log", response_model=list[dict])
async def audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_app_db),
) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT log_id, user_id, action, entity_type, entity_id, detail, ip_address, created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]
