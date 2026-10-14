from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_app_db

router = APIRouter()


def _crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for c in data.encode("ascii"):
        crc ^= c << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def generate_promptpay_payload(target: str, amount: float | Decimal | None = None) -> str:
    target_clean = str(target).replace("-", "").strip()
    if len(target_clean) == 10 and target_clean.startswith("0"):
        # Thai Mobile Number (08x, 09x, 06x) formatted to 13 digits: 0066...
        formatted_target = "0066" + target_clean[1:]
        subtag = f"01{len(formatted_target):02d}{formatted_target}"
    else:
        # National ID / Tax ID (13 digits)
        subtag = f"02{len(target_clean):02d}{target_clean}"

    tag29_val = f"0016A000000677010111{subtag}"
    tag29 = f"29{len(tag29_val):02d}{tag29_val}"

    parts = [
        "000201",
        "010212" if amount is not None else "010211",
        tag29,
        "5303764",  # Currency: THB (764)
    ]
    if amount is not None:
        amt_str = f"{float(amount):.2f}"
        parts.append(f"54{len(amt_str):02d}{amt_str}")
    parts.append("5802TH")  # Country Code: TH
    raw = "".join(parts) + "6304"
    checksum = _crc16_ccitt(raw)
    return raw + checksum


async def _assert_order_access(order: dict, user: dict, db: AsyncSession) -> None:
    if user.get("role") == "ADMIN":
        return
    user_id = user.get("user_id")
    order_owner_user_id = None
    if order.get("booking_id"):
        b_res = await db.execute(
            text("SELECT m.user_id FROM booking b JOIN member m ON m.member_id = b.member_id WHERE b.booking_id = :bid"),
            {"bid": order["booking_id"]},
        )
        order_owner_user_id = b_res.scalar_one_or_none()
    elif order.get("package_id"):
        p_res = await db.execute(
            text("SELECT m.user_id FROM member_package mp JOIN member m ON m.member_id = mp.member_id WHERE mp.package_id = :pid"),
            {"pid": order["package_id"]},
        )
        order_owner_user_id = p_res.scalar_one_or_none()
    if order_owner_user_id is not None and order_owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have permission for this order")


@router.post("/{order_id}/promptpay-qr", response_model=dict)
@router.get("/{order_id}/promptpay-qr", response_model=dict)
@router.post("/{order_id}/qr", response_model=dict)
@router.get("/{order_id}/qr", response_model=dict)
async def get_order_promptpay_qr(
    order_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    order_res = await db.execute(
        text(
            """
            SELECT order_id, order_type, booking_id, package_id,
                   total_amount, discount, final_amount,
                   payment_method, payment_status
            FROM orders
            WHERE order_id = :order_id
            """
        ),
        {"order_id": order_id},
    )
    order = order_res.mappings().one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    await _assert_order_access(order, user, db)

    amount = float(order["final_amount"] if order["final_amount"] is not None else order["total_amount"])
    # Default platform promptpay merchant account ID
    merchant_target = "0812345678"
    qr_payload = generate_promptpay_payload(merchant_target, amount)

    order_no = f"ORD-{order['order_type'][:3]}-{order['order_id']:08d}"
    return {
        "order_id": order["order_id"],
        "order_no": order_no,
        "order_type": order["order_type"],
        "amount": amount,
        "currency": "THB",
        "payment_status": order["payment_status"],
        "promptpay_payload": qr_payload,
        "qr_payload": qr_payload,
        "qr_data": qr_payload,
    }


@router.post("/{order_id}/mock-pay", response_model=dict)
@router.post("/{order_id}/confirm-payment", response_model=dict)
async def mock_confirm_order_payment(
    order_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    order_res = await db.execute(
        text("SELECT * FROM orders WHERE order_id = :order_id FOR UPDATE"),
        {"order_id": order_id},
    )
    order = order_res.mappings().one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    await _assert_order_access(order, user, db)

    if order["payment_status"] != "PAID":
        await db.execute(
            text(
                """
                UPDATE orders
                SET payment_status = 'PAID', payment_time = NOW(), updated_at = NOW()
                WHERE order_id = :order_id
                """
            ),
            {"order_id": order_id},
        )

        member_id_to_update = None
        final_amount = Decimal(str(order["final_amount"] or 0))

        if order["order_type"] == "PACKAGE" and order["package_id"]:
            # Update member_package status to ACTIVE
            pkg_res = await db.execute(
                text("SELECT member_id FROM member_package WHERE package_id = :pid"),
                {"pid": order["package_id"]},
            )
            pkg = pkg_res.mappings().one_or_none()
            if pkg:
                member_id_to_update = pkg["member_id"]
                await db.execute(
                    text(
                        """
                        UPDATE member_package
                        SET status = 'ACTIVE', updated_at = NOW()
                        WHERE package_id = :pid
                        """
                    ),
                    {"pid": order["package_id"]},
                )

        elif order["order_type"] == "BOOKING" and order["booking_id"]:
            # Update booking status to CONFIRMED
            b_res = await db.execute(
                text("SELECT member_id, coach_id, booking_date, start_time, duration_minutes, break_minutes FROM booking WHERE booking_id = :bid"),
                {"bid": order["booking_id"]},
            )
            b_row = b_res.mappings().one_or_none()
            if b_row:
                member_id_to_update = b_row["member_id"]
                await db.execute(
                    text(
                        """
                        UPDATE booking
                        SET status = 'CONFIRMED', updated_at = NOW()
                        WHERE booking_id = :bid AND status = 'PENDING'
                        """
                    ),
                    {"bid": order["booking_id"]},
                )

        # Update member total_spend and check tier upgrade
        if member_id_to_update and final_amount > 0:
            await db.execute(
                text(
                    """
                    UPDATE member
                    SET total_spend = total_spend + :amt
                    WHERE member_id = :mid
                    """
                ),
                {"amt": final_amount, "mid": member_id_to_update},
            )
            # Re-evaluate membership tier
            mem_res = await db.execute(
                text("SELECT total_spend FROM member WHERE member_id = :mid"),
                {"mid": member_id_to_update},
            )
            curr_spend = mem_res.scalar_one_or_none() or Decimal("0")
            level_res = await db.execute(
                text(
                    """
                    SELECT level_id
                    FROM membership_level
                    WHERE min_total_spend <= :spend
                    ORDER BY min_total_spend DESC, sort_order DESC
                    LIMIT 1
                    """
                ),
                {"spend": curr_spend},
            )
            new_level_id = level_res.scalar_one_or_none()
            if new_level_id:
                await db.execute(
                    text("UPDATE member SET level_id = :lid WHERE member_id = :mid"),
                    {"lid": new_level_id, "mid": member_id_to_update},
                )

        await db.commit()

    updated = await db.execute(
        text("SELECT * FROM orders WHERE order_id = :order_id"),
        {"order_id": order_id},
    )
    d = dict(updated.mappings().one())
    d["order_no"] = f"ORD-{d['order_type'][:3]}-{d['order_id']:08d}"
    return d


@router.post("/bookings/{booking_id}/mock-pay", response_model=dict)
async def mock_confirm_booking_payment(
    booking_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_app_db),
) -> dict:
    order_res = await db.execute(
        text(
            """
            SELECT order_id
            FROM orders
            WHERE booking_id = :booking_id AND order_type = 'BOOKING'
            """
        ),
        {"booking_id": booking_id},
    )
    order_id = order_res.scalar_one_or_none()
    if order_id is None:
        raise HTTPException(status_code=404, detail="Booking payment order not found")
    return await mock_confirm_order_payment(int(order_id), user, db)
