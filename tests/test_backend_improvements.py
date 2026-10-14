from datetime import date, datetime, time, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.booking import BookingCreateRequest, BookingResponse
from app.schemas.auth import NextSession
from app.schemas.coach import (
    CoachScheduleBlockRequest,
    CoachScheduleUnblockRequest,
    CoachConversationSummary,
)
from app.api.routes.orders import generate_promptpay_payload


def test_booking_create_request_price_optional():
    # Should not raise validation error when price is omitted
    req = BookingCreateRequest(
        coach_id=1,
        course_id=1,
        gym_id=1,
        booking_date=date(2026, 10, 20),
        start_time=time(10, 0),
        duration_minutes=60,
        break_minutes=10,
        service_mode="GYM",
    )
    assert req.price is None
    assert req.duration_minutes == 60


def test_booking_response_timedelta_parsing():
    # Simulate DB returning timedelta for TIME columns
    data = {
        "booking_id": 101,
        "member_id": 1,
        "coach_id": 1,
        "course_id": 1,
        "gym_id": 1,
        "package_id": None,
        "booking_date": date(2026, 10, 20),
        "start_time": timedelta(seconds=9 * 3600 + 10 * 60),  # 09:10:00
        "end_time": timedelta(seconds=10 * 3600 + 10 * 60),    # 10:10:00
        "duration_minutes": 60,
        "break_minutes": 10,
        "service_mode": "GYM",
        "service_district": None,
        "service_address": None,
        "price": Decimal("1000.00"),
        "status": "CONFIRMED",
        "expires_at": None,
        "cancelled_by": None,
        "cancel_reason": None,
        "cancelled_at": None,
        "completed_at": None,
        "created_at": "2026-10-14T10:00:00",
        "updated_at": "2026-10-14T10:00:00",
    }
    resp = BookingResponse.model_validate(data)
    assert resp.start_time == "09:10:00"
    assert resp.end_time == "10:10:00"


def test_next_session_timedelta_parsing():
    data = {
        "booking_id": 102,
        "booking_date": date(2026, 10, 20),
        "start_time": timedelta(seconds=14 * 3600 + 20 * 60),  # 14:20:00
        "end_time": timedelta(seconds=15 * 3600 + 20 * 60),    # 15:20:00
        "duration_minutes": 60,
        "service_mode": "GYM",
        "price": Decimal("1200.00"),
        "coach_name": "Tan Coach",
        "course_name": "Strength Training",
    }
    ns = NextSession.model_validate(data)
    assert ns.start_time == "14:20:00"
    assert ns.end_time == "15:20:00"


def test_promptpay_emvco_generator():
    payload = generate_promptpay_payload("0812345678", 500.00)
    assert payload.startswith("000201010212")
    assert "0016A000000677010111" in payload
    assert "0066812345678" in payload
    assert "5303764" in payload
    assert "5406500.00" in payload
    assert "5802TH" in payload
    assert payload.endswith("63047190")


def test_coach_schedule_block_defaults():
    req = CoachScheduleBlockRequest(
        block_date=date(2026, 10, 23),
        start_time="14:00",
        end_time="16:00",
    )
    assert req.reason == "Personal leave"
    assert req.block_date == date(2026, 10, 23)


def test_coach_conversation_summary_model():
    summary = CoachConversationSummary(
        member_id=1,
        member_name="Alex Morgan",
        last_message="See you tomorrow",
        last_message_time=datetime(2026, 10, 14, 15, 30),
        unread_count=2,
    )
    assert summary.member_id == 1
    assert summary.unread_count == 2


def test_member_profile_next_tier_integration():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "alex.demo", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = client.get("/api/v1/members/me", headers=headers)
        assert res.status_code == 200
        data = res.json()["data"]
        assert "level_code" in data
        assert "amount_to_next_tier" in data


def test_admin_audit_log_pagination_envelope():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "admin.demo", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = client.get("/api/v1/admin/audit-log?limit=5&offset=0", headers=headers)
        assert res.status_code == 200
        data = res.json()["data"]
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "has_more" in data
        assert data["limit"] == 5
        assert isinstance(data["items"], list)


def test_coach_routes_integration():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "tan.coach", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Test conversations overview
        conv_res = client.get("/api/v1/coaches/me/conversations", headers=headers)
        assert conv_res.status_code == 200
        assert isinstance(conv_res.json()["data"], list)

        # 2. Test member reviews listing
        rev_res = client.get("/api/v1/coaches/me/member-reviews", headers=headers)
        assert rev_res.status_code == 200
        assert isinstance(rev_res.json()["data"], list)

        # 3. Test block without reason (default "Personal leave")
        block_res = client.post(
            "/api/v1/coaches/me/schedule/block",
            headers=headers,
            json={
                "date": "2026-11-20",
                "start_time": "14:00",
                "end_time": "15:00"
            }
        )
        assert block_res.status_code == 200
        assert block_res.json()["data"]["reason"] == "Personal leave"

        # 4. Test unblock
        unblock_res = client.post(
            "/api/v1/coaches/me/schedule/unblock",
            headers=headers,
            json={
                "date": "2026-11-20",
                "start_time": "14:00",
                "end_time": "15:00"
            }
        )
        assert unblock_res.status_code == 200


def test_schedule_block_with_default_reason():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "tan.coach", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        block_res = client.post(
            "/api/v1/coaches/me/schedule/block",
            headers=headers,
            json={
                "block_date": "2026-12-05",
                "start_time": "14:00",
                "end_time": "15:00",
            },
        )
        assert block_res.status_code in (200, 201)
        data = block_res.json()["data"]
        assert data["reason"] == "Personal leave"

        # Cleanup
        unblock_res = client.post(
            "/api/v1/coaches/me/schedule/unblock",
            headers=headers,
            json={
                "block_date": "2026-12-05",
                "start_time": "14:00",
                "end_time": "15:00",
            },
        )
        assert unblock_res.status_code == 200


def test_schedule_block_conflict_on_existing_booking():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "tan.coach", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Booking #4 is on 2026-10-20 between 14:00 and 15:00 for coach 1
        block_res = client.post(
            "/api/v1/coaches/me/schedule/block",
            headers=headers,
            json={
                "block_date": "2026-10-20",
                "start_time": "14:00",
                "end_time": "15:00",
            },
        )
        assert block_res.status_code == 409
        err_msg = block_res.json()["message"]
        assert "已有学员预约" in err_msg or "无法直接锁定" in err_msg


def test_member_reviews_duplicate_handling():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "tan.coach", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Query existing review for booking 1
        rev_list = client.get("/api/v1/coaches/me/member-reviews?booking_id=1", headers=headers)
        assert rev_list.status_code == 200
        assert len(rev_list.json()["data"]) >= 1

        # Attempt to post a duplicate review for booking 1
        dup_res = client.post(
            "/api/v1/coaches/me/member-reviews",
            headers=headers,
            json={
                "booking_id": 1,
                "completion_score": 5,
                "proficiency_score": 5,
                "training_area": "CORE",
                "training_type": "STRENGTH",
                "coach_note": "Duplicate attempt",
            },
        )
        assert dup_res.status_code == 409
        assert "already exists" in dup_res.json()["message"]


def test_audit_log_pagination_offset():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "admin.demo", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res_p1 = client.get("/api/v1/admin/audit-log?limit=10&offset=0", headers=headers)
        res_p2 = client.get("/api/v1/admin/audit-log?limit=10&offset=10", headers=headers)

        assert res_p1.status_code == 200
        assert res_p2.status_code == 200

        data_p1 = res_p1.json()["data"]
        data_p2 = res_p2.json()["data"]

        assert data_p1["page"] == 1
        assert data_p2["page"] == 2
        assert data_p1["limit"] == 10
        assert data_p2["limit"] == 10

        if data_p1["total"] > 10:
            ids_p1 = {item["log_id"] for item in data_p1["items"]}
            ids_p2 = {item["log_id"] for item in data_p2["items"]}
            assert ids_p1.isdisjoint(ids_p2)


def test_promptpay_qr_generation():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "alex.demo", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Purchase a package to generate order
        pkg_res = client.post(
            "/api/v1/members/me/packages/purchase",
            headers=headers,
            json={"package_type": "5+1"},
        )
        assert pkg_res.status_code in (200, 201)
        order_id = pkg_res.json()["data"]["order_id"]
        assert order_id is not None

        # 2. Fetch PromptPay QR payload
        qr_res = client.post(f"/api/v1/orders/{order_id}/promptpay-qr", headers=headers)
        assert qr_res.status_code == 200
        qr_data = qr_res.json()["data"]
        assert qr_data["order_id"] == order_id
        assert qr_data["promptpay_payload"].startswith("000201")
        assert "0016A000000677010111" in qr_data["promptpay_payload"]

        # 3. Also verify /qr alias
        qr_alias_res = client.get(f"/api/v1/orders/{order_id}/qr", headers=headers)
        assert qr_alias_res.status_code == 200
        assert qr_alias_res.json()["data"]["qr_payload"] == qr_data["promptpay_payload"]

        # 4. Mock payment confirmation
        pay_res = client.post(f"/api/v1/orders/{order_id}/mock-pay", headers=headers)
        assert pay_res.status_code == 200
        assert pay_res.json()["data"]["payment_status"] == "PAID"


def test_websocket_chat_ping_pong():
    with TestClient(app) as client:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": "alex.demo", "password": "DemoPass123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["data"]["access_token"]

        with client.websocket_connect(f"/api/v1/ws/chat?token={token}") as ws:
            init_data = ws.receive_json()
            assert init_data["type"] == "connection_established"
            ws.send_json({"type": "ping"})
            pong_data = ws.receive_json()
            assert pong_data["type"] == "pong"

