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


@router.post("/{order_id}/promptpay-qr", response_model=dict)
@router.get("/{order_id}/promptpay-qr", response_model=dict)
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

    amount = float(order["final_amount"] if order["final_amount"] is not None else order["total_amount"])
    # Default platform promptpay merchant account ID
    merchant_target = "0812345678"
    qr_payload = generate_promptpay_payload(merchant_target, amount)

    return {
        "order_id": order["order_id"],
        "order_type": order["order_type"],
        "amount": amount,
        "currency": "THB",
        "payment_status": order["payment_status"],
        "promptpay_payload": qr_payload,
        "qr_data": qr_payload,
    }
