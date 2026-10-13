from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.routes.auth import login
from app.core.security import hash_password
from app.schemas.auth import LoginRequest


class FakeResult:
    def __init__(self, row: dict | None) -> None:
        self.row = row

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict | None:
        return self.row


class FakeSession:
    def __init__(self, row: dict | None) -> None:
        self.row = row
        self.rollback_count = 0
        self.commit_count = 0

    async def execute(self, statement: object, params: dict) -> FakeResult:
        if "SELECT" in str(statement).upper():
            return FakeResult(self.row)
        return FakeResult(None)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def user_row() -> dict:
    now = datetime.now()
    return {
        "user_id": 1,
        "username": "mLyoZbo2lP",
        "password_hash": hash_password("stringstring"),
        "display_name": "Test User",
        "email": "test@example.com",
        "phone": "0812345678",
        "role": "MEMBER",
        "status": "ACTIVE",
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
    }


@pytest.mark.asyncio
async def test_login_same_request_is_deterministic() -> None:
    payload = LoginRequest(username="mLyoZbo2lP", password="stringstring")

    for _ in range(2):
        response = await login(payload, FakeSession(user_row()))
        assert response.user.username == payload.username
        assert response.access_token


@pytest.mark.asyncio
async def test_invalid_login_returns_401_and_rolls_back() -> None:
    session = FakeSession(None)

    with pytest.raises(HTTPException) as error:
        await login(
            LoginRequest(username="mLyoZbo2lP", password="stringstring"),
            session,
        )

    assert error.value.status_code == 401
    assert session.rollback_count == 1
