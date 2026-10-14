from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.booking import BookingCreateRequest
from app.services.schedule_service import ScheduleService


class BookingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_booking(
        self,
        payload: BookingCreateRequest,
        member_id: int | None = None,
    ) -> dict:
        effective_member_id = member_id if member_id is not None else payload.member_id

        # Auto-calculate price if not provided by client
        booking_price = payload.price
        order_total_amount = Decimal("0.00")
        order_discount = Decimal("0.00")
        if booking_price is None:
            if payload.package_id is not None:
                booking_price = Decimal("0.00")
            else:
                course_price_res = await self.db.execute(
                    text(
                        """
                        SELECT price_per_session
                        FROM coach_course
                        WHERE coach_id = :coach_id AND course_id = :course_id AND is_active = 1
                        """
                    ),
                    {"coach_id": payload.coach_id, "course_id": payload.course_id},
                )
                base_price = course_price_res.scalar_one_or_none()
                if base_price is None:
                    base_price = Decimal("1000.00")
                else:
                    base_price = Decimal(str(base_price))

                discount_rate = Decimal("0.000")
                if effective_member_id is not None:
                    disc_res = await self.db.execute(
                        text(
                            """
                            SELECT ml.discount_rate
                            FROM member m
                            JOIN membership_level ml ON ml.level_id = m.level_id
                            WHERE m.member_id = :member_id
                            """
                        ),
                        {"member_id": effective_member_id},
                    )
                    rate = disc_res.scalar_one_or_none()
                    if rate is not None:
                        discount_rate = Decimal(str(rate))

                booking_price = round(base_price * (Decimal("1") - discount_rate), 2)
                order_total_amount = base_price
                order_discount = base_price - booking_price
        else:
            order_total_amount = Decimal(str(booking_price))

        end_time = (
            datetime.combine(payload.booking_date, payload.start_time)
            + timedelta(minutes=payload.duration_minutes)
        ).time()
        table_name = await ScheduleService(self.db).get_table_name(payload.coach_id)
        slot_end = datetime.combine(payload.booking_date, payload.start_time) + timedelta(
            minutes=payload.duration_minutes + payload.break_minutes
        )

        await self.db.rollback()
        try:
            await self.db.begin()
            start_dt = datetime.combine(payload.booking_date, payload.start_time)
            slots = await self.db.execute(
                text(
                    f"""
                    SELECT slot_start, status, booking_id
                    FROM `{table_name}`
                    WHERE slot_start >= :slot_start
                      AND slot_start < :slot_end
                    ORDER BY slot_start
                    FOR UPDATE
                    """
                ),
                {
                    "slot_start": start_dt,
                    "slot_end": slot_end,
                },
            )
            locked_slots = slots.mappings().all()
            expected_slots = (
                payload.duration_minutes + payload.break_minutes
            ) // 10
            if len(locked_slots) != expected_slots:
                # Auto-populate slots for the missing interval if coach has open availability
                current_slot = start_dt
                while current_slot < slot_end:
                    await self.db.execute(
                        text(f"INSERT IGNORE INTO `{table_name}` (slot_start, status) VALUES (:st, 'AVAILABLE')"),
                        {"st": current_slot},
                    )
                    current_slot += timedelta(minutes=10)
                # Re-select for update
                slots = await self.db.execute(
                    text(
                        f"""
                        SELECT slot_start, status, booking_id
                        FROM `{table_name}`
                        WHERE slot_start >= :slot_start
                          AND slot_start < :slot_end
                        ORDER BY slot_start
                        FOR UPDATE
                        """
                    ),
                    {
                        "slot_start": start_dt,
                        "slot_end": slot_end,
                    },
                )
                locked_slots = slots.mappings().all()
            if any(slot["status"] != "AVAILABLE" for slot in locked_slots):
                raise ValueError("One or more requested schedule slots are unavailable")

            result = await self.db.execute(
                text(
                    """
                    INSERT INTO booking (
                        member_id, coach_id, course_id, gym_id, package_id,
                        booking_date, start_time, end_time, duration_minutes,
                        break_minutes, service_mode, service_district,
                        service_address, price, status, expires_at
                    ) VALUES (
                        :member_id, :coach_id, :course_id, :gym_id, :package_id,
                        :booking_date, :start_time, :end_time, :duration_minutes,
                        :break_minutes, :service_mode, :service_district,
                        :service_address, :price,
                        CASE WHEN :is_pkg = 1 THEN 'CONFIRMED' ELSE 'PENDING' END,
                        CASE WHEN :is_pkg = 1 THEN NULL ELSE DATE_ADD(NOW(), INTERVAL 15 MINUTE) END
                    )
                    """
                ),
                {
                    "member_id": effective_member_id,
                    "coach_id": payload.coach_id,
                    "course_id": payload.course_id,
                    "gym_id": payload.gym_id,
                    "package_id": payload.package_id,
                    "booking_date": payload.booking_date,
                    "start_time": payload.start_time,
                    "end_time": end_time,
                    "duration_minutes": payload.duration_minutes,
                    "break_minutes": payload.break_minutes,
                    "service_mode": payload.service_mode,
                    "service_district": payload.service_district,
                    "service_address": payload.service_address,
                    "price": booking_price,
                    "is_pkg": 1 if payload.package_id is not None else 0,
                },
            )
            booking_id = result.lastrowid

            # Create corresponding orders record
            await self.db.execute(
                text(
                    """
                    INSERT INTO orders (
                        order_type, booking_id, total_amount, discount, final_amount,
                        payment_method, payment_status, payment_time
                    ) VALUES (
                        'BOOKING', :booking_id, :total_amount, :discount, :final_amount,
                        CASE WHEN :is_pkg = 1 THEN 'PACKAGE_CREDIT' ELSE NULL END,
                        CASE WHEN :is_pkg = 1 THEN 'PAID' ELSE 'UNPAID' END,
                        CASE WHEN :is_pkg = 1 THEN NOW() ELSE NULL END
                    )
                    """
                ),
                {
                    "booking_id": booking_id,
                    "total_amount": order_total_amount,
                    "discount": order_discount,
                    "final_amount": booking_price,
                    "is_pkg": 1 if payload.package_id is not None else 0,
                },
            )

            await self.db.execute(
                text(
                    f"""
                    UPDATE `{table_name}`
                    SET status = CASE
                            WHEN slot_start < :training_end THEN 'BOOKED'
                            ELSE 'BREAK'
                        END,
                        booking_id = :booking_id
                    WHERE slot_start >= :slot_start
                      AND slot_start < :slot_end
                    """
                ),
                {
                    "training_end": datetime.combine(payload.booking_date, end_time),
                    "slot_start": datetime.combine(payload.booking_date, payload.start_time),
                    "slot_end": slot_end,
                    "booking_id": booking_id,
                },
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        result = await self.db.execute(
            text("SELECT * FROM booking WHERE booking_id = :booking_id"),
            {"booking_id": booking_id},
        )
        row = result.mappings().one()
        return dict(row)
