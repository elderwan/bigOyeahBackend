from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_current_user
from app.api.routes.auth import hash_password
from app.db.session import get_app_db
from app.main import app


def _user_row(
    *,
    user_id: int = 1,
    username: str = "alex",
    email: str = "alex@example.com",
    password: str = "FitBooking123!",
) -> dict[str, Any]:
    now = datetime(2026, 10, 13, 10, 0, 0)
    return {
        "user_id": user_id,
        "username": username,
        "password_hash": hash_password(password),
        "display_name": "Alex Morgan",
        "email": email,
        "phone": "+66812345678",
        "role": "MEMBER",
        "status": "ACTIVE",
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
    }


def _profile_row(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "member_id": 10,
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "email": user["email"],
        "phone": user["phone"],
        "level_id": 2,
        "level_code": "GOLD",
        "level_name": "Gold Member",
        "discount_rate": Decimal("0.10"),
        "total_spend": Decimal("7850.00"),
        "gender": "FEMALE",
        "birth_date": date(1996, 6, 14),
        "height_cm": Decimal("165.0"),
        "weight_kg": Decimal("58.0"),
        "fitness_goal": "Build strength",
    }


class Result:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        lastrowid: int | None = None,
    ) -> None:
        self.rows = rows or []
        self.lastrowid = lastrowid

    def mappings(self) -> "Result":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def one(self) -> dict[str, Any]:
        if not self.rows:
            raise LookupError("expected one row")
        return self.rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class ContractSession:
    def __init__(
        self,
        *,
        user: dict[str, Any] | None = None,
        duplicate_contact: bool = False,
    ) -> None:
        self.user = user
        self.profile = _profile_row(user) if user else None
        self.duplicate_contact = duplicate_contact
        self.registered_user_params: dict[str, Any] | None = None
        self.registered_member_params: dict[str, Any] | None = None
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement: object, params: dict[str, Any]) -> Result:
        sql = " ".join(str(statement).upper().split())
        if sql.startswith("SELECT") and "FROM USERS" in sql:
            if "WHERE (USERNAME = :IDENTIFIER" in sql:
                identifier = params["identifier"]
                if self.user and identifier in (self.user["username"], self.user["email"]):
                    return Result([self.user])
                return Result()
            if self.user:
                return Result([self.user])
            return Result()

        if sql.startswith("INSERT INTO USERS"):
            self.registered_user_params = params.copy()
            self.user = _user_row(
                username=params["username"],
                email=params["email"],
            )
            return Result(lastrowid=self.user["user_id"])

        if sql.startswith("INSERT INTO MEMBER"):
            self.registered_member_params = params.copy()
            return Result()

        if sql.startswith("UPDATE USERS"):
            if self.duplicate_contact:
                raise IntegrityError("duplicate", params, Exception("duplicate"))
            assert self.user is not None
            self.user.update(
                {key: value for key, value in params.items() if key != "user_id"}
            )
            if self.profile:
                self.profile.update(
                    {key: value for key, value in params.items() if key != "user_id"}
                )
            return Result()

        if sql.startswith("UPDATE MEMBER"):
            assert self.profile is not None
            self.profile.update(
                {key: value for key, value in params.items() if key != "user_id"}
            )
            return Result()

        if "FROM MEMBER M" in sql:
            return Result([self.profile] if self.profile else [])

        raise AssertionError(f"Unexpected SQL: {statement}")

    async def begin(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def override_db(session: ContractSession):
    async def dependency():
        yield session

    return dependency


def client_for(
    session: ContractSession,
    *,
    current_user: dict[str, Any] | None = None,
) -> TestClient:
    app.dependency_overrides[get_app_db] = override_db(session)
    if current_user is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_login_accepts_username_and_email_and_rejects_invalid_credentials() -> None:
    user = _user_row()
    for identifier in (user["username"], user["email"]):
        with client_for(ContractSession(user=user)) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": identifier, "password": "FitBooking123!"},
            )
        assert response.status_code == 200
        assert response.json()["data"]["user"]["username"] == "alex"

    for payload in (
        {"username": "alex", "password": "wrong-password"},
        {"username": "missing", "password": "FitBooking123!"},
    ):
        with client_for(ContractSession(user=user)) as client:
            response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401
        assert response.json()["success"] is False


def test_register_persists_all_profile_fields_and_normalizes_prefer_not_to_say() -> None:
    session = ContractSession()
    payload = {
        "username": "new.member",
        "password": "StrongPass123!",
        "display_name": "New Member",
        "email": "new.member@example.com",
        "phone": "+66812345679",
        "gender": "Prefer not to say",
        "birth_date": "1996-06-14",
        "height_cm": 165.0,
        "weight_kg": 58.0,
        "fitness_goal": "Build strength",
    }
    with client_for(session) as client:
        response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    assert session.registered_user_params is not None
    assert session.registered_member_params is not None
    assert session.registered_user_params["display_name"] == "New Member"
    assert session.registered_member_params["gender"] is None
    assert session.registered_member_params["birth_date"] == date(1996, 6, 14)
    assert session.registered_member_params["height_cm"] == Decimal("165.0")
    assert session.registered_member_params["weight_kg"] == Decimal("58.0")
    assert session.registered_member_params["fitness_goal"] == "Build strength"


def test_register_duplicate_username_email_phone_returns_409() -> None:
    class DuplicateRegisterSession(ContractSession):
        async def execute(self, statement: object, params: dict[str, Any]) -> Result:
            if " ".join(str(statement).upper().split()).startswith("INSERT INTO USERS"):
                raise IntegrityError("duplicate", params, Exception("duplicate"))
            return await super().execute(statement, params)

    with client_for(DuplicateRegisterSession()) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "alex",
                "password": "StrongPass123!",
                "display_name": "Alex",
                "email": "alex@example.com",
                "phone": "+66812345678",
            },
        )
    assert response.status_code == 409
    assert response.json()["success"] is False


def test_profile_get_and_patch_update_user_and_member_columns() -> None:
    user = _user_row()
    session = ContractSession(user=user)
    with client_for(session, current_user=user) as client:
        get_response = client.get(
            "/api/v1/members/me",
            headers={"Authorization": "Bearer test-token"},
        )
        patch_response = client.patch(
            "/api/v1/members/me",
            headers={"Authorization": "Bearer test-token"},
            json={
                "display_name": "Alex Updated",
                "email": "alex.updated@example.com",
                "phone": "+66812345680",
                "gender": "MALE",
                "birth_date": "1995-05-15",
                "height_cm": 170.0,
                "weight_kg": 65.0,
                "fitness_goal": "Mobility",
            },
        )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["username"] == "alex"
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["display_name"] == "Alex Updated"
    assert patch_response.json()["data"]["email"] == "alex.updated@example.com"
    assert patch_response.json()["data"]["fitness_goal"] == "Mobility"
    assert session.committed is True


def test_duplicate_profile_contact_returns_409_not_500() -> None:
    user = _user_row()
    session = ContractSession(user=user, duplicate_contact=True)
    with client_for(session, current_user=user) as client:
        response = client.patch(
            "/api/v1/members/me",
            json={"email": "already-used@example.com"},
        )
    assert response.status_code == 409
    assert response.json()["success"] is False
    assert session.rolled_back is True


@pytest.mark.parametrize(
    "payload",
    [
        {
            "username": "valid.user",
            "password": "StrongPass123!",
            "display_name": "Valid User",
            "email": "not-an-email",
            "phone": "+66812345678",
        },
        {
            "username": "valid.user",
            "password": "StrongPass123!",
            "display_name": "Valid User",
            "email": "valid@example.com",
            "phone": "+66812345678",
            "birth_date": "not-a-date",
        },
        {
            "username": "valid.user",
            "password": "StrongPass123!",
            "display_name": "Valid User",
            "email": "valid@example.com",
            "phone": "+66812345678",
            "height_cm": 0,
        },
    ],
)
def test_signup_validation_errors_return_422(payload: dict[str, Any]) -> None:
    with client_for(ContractSession()) as client:
        response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_cors_allows_live_frontend_and_localhost() -> None:
    with client_for(ContractSession()) as client:
        for origin in ("http://10.195.90.91:3000", "http://localhost:3000"):
            response = client.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
