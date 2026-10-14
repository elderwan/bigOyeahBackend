from datetime import date, time, timedelta
from decimal import Decimal
import pytest
from pydantic import ValidationError

from app.schemas.booking import BookingCreateRequest, BookingResponse
from app.schemas.auth import NextSession
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
