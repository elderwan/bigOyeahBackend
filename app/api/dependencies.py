from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_token
from app.db.session import get_app_db


async def get_current_user(
    token: dict[str, object] = Depends(get_current_token),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    try:
        user_id = int(token["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid access token") from None
    result = await db.execute(
        text(
            """
            SELECT user_id, username, display_name, email, phone, role, status,
                   last_login_at, created_at, updated_at
            FROM users
            WHERE user_id = :user_id AND status = 'ACTIVE'
            """
        ),
        {"user_id": user_id},
    )
    user = result.mappings().one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User account is unavailable")
    return dict(user)
