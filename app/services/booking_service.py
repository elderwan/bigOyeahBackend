from datetime import datetime, timedelta

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
                        :service_address, :price, 'PENDING',
                        DATE_ADD(NOW(), INTERVAL 15 MINUTE)
                    )
                    """
                ),
                {
                    "member_id": member_id if member_id is not None else payload.member_id,
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
                    "price": payload.price,
                },
            )
            booking_id = result.lastrowid
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
