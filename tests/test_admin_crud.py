from fastapi.testclient import TestClient
import pytest
from app.main import app

@pytest.fixture
def auth_client():
    with TestClient(app) as c:
        login_res = c.post(
            "/api/v1/auth/login",
            json={"username": "admin.demo", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["data"]["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c

def test_admin_settings_get_and_patch(auth_client):
    res = auth_client.get("/api/v1/admin/settings")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "require_coach_verification" in data

    patch_res = auth_client.patch(
        "/api/v1/admin/settings",
        json={"booking_reminder_hours": 48}
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["booking_reminder_hours"] == 48

def test_admin_activity(auth_client):
    res = auth_client.get("/api/v1/admin/activity?limit=5")
    assert res.status_code == 200
    assert isinstance(res.json()["data"], list)

def test_admin_kpi_overview_and_records(auth_client):
    res = auth_client.get("/api/v1/admin/kpi")
    assert res.status_code == 200
    assert "kpi_rules" in res.json()["data"]

    rec_res = auth_client.get("/api/v1/admin/kpi/records")
    assert rec_res.status_code == 200
    assert isinstance(rec_res.json()["data"], list)

def test_admin_reports_generate_and_export(auth_client):
    gen_res = auth_client.post(
        "/api/v1/admin/reports/generate",
        json={
            "report_name": "Monthly Overview",
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            "group_by": "coach"
        }
    )
    assert gen_res.status_code == 200
    assert "summary" in gen_res.json()["data"]

    export_res = auth_client.get("/api/v1/admin/reports/export?date_from=2026-04-01&date_to=2026-04-30")
    assert export_res.status_code == 200
    assert "Booking ID" in export_res.text

def test_admin_create_coach(auth_client):
    payload = {
        "password": "DemoPass123!",
        "break_interval": 20,
        "years_experience": 10,
        "username": "new.coach.test",
        "email": "new.coach.test@gmail.com",
        "phone": "+66891234999",
        "display_name": "Oly Test",
        "coach_no": "9998",
        "coach_level": "MASTER",
        "service_mode": "BOTH",
        "certifications": "",
        "bio": "master!!!!!!!!1"
    }
    res = auth_client.post("/api/v1/admin/coaches", json=payload)
    # If coach already exists from earlier test, 201 or 409
    assert res.status_code in (201, 409)
    if res.status_code == 201:
        assert res.json()["data"]["coach_no"] == "9998"
