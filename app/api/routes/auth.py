from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_app_db
from app.schemas.auth import AuthResponse, LoginRequest, MemberRegisterRequest, UserResponse

router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_member(
    payload: MemberRegisterRequest,
    db: AsyncSession = Depends(get_app_db),
) -> AuthResponse:
    try:
        await db.begin()
        result = await db.execute(
            text(
                """
                INSERT INTO users (username, password_hash, display_name, email, phone, role)
                VALUES (:username, :password_hash, :display_name, :email, :phone, 'MEMBER')
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
        await db.execute(
            text(
                """
                INSERT INTO member
                    (user_id, gender, birth_date, height_cm, weight_kg, fitness_goal)
                VALUES
                    (:user_id, :gender, :birth_date, :height_cm, :weight_kg, :fitness_goal)
                """
            ),
            {
                "user_id": user_id,
                "gender": payload.gender,
                "birth_date": payload.birth_date,
                "height_cm": payload.height_cm,
                "weight_kg": payload.weight_kg,
                "fitness_goal": payload.fitness_goal,
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
            SELECT user_id, username, display_name, email, phone, role, status,
                   last_login_at, created_at, updated_at
            FROM users WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    user = UserResponse.model_validate(dict(user_result.mappings().one()))
    return AuthResponse(access_token=create_access_token(user.user_id, user.role), user=user)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_app_db),
) -> AuthResponse:
    try:
        result = await db.execute(
            text(
                """
                SELECT user_id, username, password_hash, display_name, email, phone, role,
                       status, last_login_at, created_at, updated_at
                FROM users
                WHERE (username = :identifier OR email = :identifier)
                  AND status = 'ACTIVE'
                """
            ),
            {"identifier": payload.username},
        )
        row = result.mappings().one_or_none()
        if (
            row is None
            or row["status"] != "ACTIVE"
            or not verify_password(payload.password, row["password_hash"])
        ):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        await db.execute(
            text(
                "UPDATE users SET last_login_at = :last_login_at "
                "WHERE user_id = :user_id"
            ),
            {"last_login_at": datetime.now(), "user_id": row["user_id"]},
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except DBAPIError:
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable",
        ) from None

    user = UserResponse.model_validate(
        {key: value for key, value in row.items() if key != "password_hash"}
    )
    return AuthResponse(access_token=create_access_token(user.user_id, user.role), user=user)


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
