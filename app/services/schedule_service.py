import re
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

COACH_NO_RE = re.compile(r"^[0-9]{4,8}$")


def build_schedule_table_name(coach_no: str) -> str:
    if not COACH_NO_RE.fullmatch(coach_no):
        raise ValueError("Invalid coach number")
    return f"coach_schedule_{coach_no}"


class ScheduleService:
    def __init__(self, db: AsyncSession, ddl_engine: AsyncEngine | None = None):
        self.db = db
        self.ddl_engine = ddl_engine

    async def get_table_name(self, coach_id: int) -> str:
        result = await self.db.execute(
            text(
                """
                SELECT sr.table_name
                FROM schedule_registry sr
                WHERE sr.coach_id = :coach_id
                  AND sr.status = 'ACTIVE'
                """
            ),
            {"coach_id": coach_id},
        )
        registered_name = result.scalar_one_or_none()
        if registered_name is not None:
            return build_schedule_table_name(str(registered_name).removeprefix("coach_schedule_"))

        result = await self.db.execute(
            text("SELECT coach_no FROM coach WHERE coach_id = :coach_id"),
            {"coach_id": coach_id},
        )
        coach_no = result.scalar_one_or_none()
        if coach_no is None:
            raise ValueError("Coach not found")
        return build_schedule_table_name(str(coach_no))

    async def create_schedule_table(self, coach_id: int) -> str:
        if self.ddl_engine is None:
            raise ValueError("DDL engine is required to create a schedule table")

        result = await self.db.execute(
            text("SELECT coach_no FROM coach WHERE coach_id = :coach_id"),
            {"coach_id": coach_id},
        )
        coach_no = result.scalar_one_or_none()
        if coach_no is None:
            raise ValueError("Coach not found")

        table_name = build_schedule_table_name(str(coach_no))
        suffix = str(coach_no)
        exists_result = await self.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
        table_exists = bool(exists_result.scalar_one())
        await self.db.commit()

        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `slot_start` DATETIME NOT NULL,
            `slot_year` SMALLINT UNSIGNED
                GENERATED ALWAYS AS (YEAR(`slot_start`)) STORED,
            `slot_month` TINYINT UNSIGNED
                GENERATED ALWAYS AS (MONTH(`slot_start`)) STORED,
            `slot_day` TINYINT UNSIGNED
                GENERATED ALWAYS AS (DAY(`slot_start`)) STORED,
            `slot_hour` TINYINT UNSIGNED
                GENERATED ALWAYS AS (HOUR(`slot_start`)) STORED,
            `slot_minute` TINYINT UNSIGNED
                GENERATED ALWAYS AS (MINUTE(`slot_start`)) STORED,
            `status` ENUM('AVAILABLE','BOOKED','BREAK','BLOCKED')
                NOT NULL DEFAULT 'AVAILABLE',
            `booking_id` BIGINT UNSIGNED NULL,
            `remark` VARCHAR(100) NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`slot_start`),
            KEY `idx_cs_{suffix}_ymdhm`
                (`slot_year`, `slot_month`, `slot_day`, `slot_hour`, `slot_minute`),
            KEY `idx_cs_{suffix}_status` (`status`, `slot_start`),
            KEY `idx_cs_{suffix}_booking` (`booking_id`),
            CONSTRAINT `chk_cs_{suffix}_grid`
                CHECK (MINUTE(`slot_start`) %% 10 = 0 AND SECOND(`slot_start`) = 0),
            CONSTRAINT `chk_cs_{suffix}_booking`
                CHECK (
                    (`status` IN ('BOOKED','BREAK') AND `booking_id` IS NOT NULL)
                    OR (`status` IN ('AVAILABLE','BLOCKED') AND `booking_id` IS NULL)
                ),
            CONSTRAINT `fk_cs_{suffix}_booking`
                FOREIGN KEY (`booking_id`) REFERENCES booking (`booking_id`)
                ON DELETE RESTRICT ON UPDATE RESTRICT
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_0900_ai_ci
        """

        async with self.ddl_engine.begin() as connection:
            await connection.exec_driver_sql(ddl)

        try:
            await self.db.execute(
                text(
                    """
                    INSERT INTO schedule_registry (coach_id, table_name, status)
                    VALUES (:coach_id, :table_name, 'ACTIVE')
                    ON DUPLICATE KEY UPDATE
                        table_name = VALUES(table_name),
                        status = 'ACTIVE'
                    """
                ),
                {"coach_id": coach_id, "table_name": table_name},
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            if not table_exists:
                async with self.ddl_engine.begin() as connection:
                    await connection.exec_driver_sql(f"DROP TABLE IF EXISTS `{table_name}`")
            raise
        return table_name

    async def list_slots(
        self,
        coach_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict]:
        table_name = await self.get_table_name(coach_id)
        result = await self.db.execute(
            text(
                f"""
                SELECT slot_start, slot_year, slot_month, slot_day, slot_hour,
                       slot_minute, status, booking_id, remark, created_at, updated_at
                FROM `{table_name}`
                WHERE slot_start >= :start_at
                  AND slot_start < :end_at
                ORDER BY slot_start
                """
            ),
            {"start_at": start_at, "end_at": end_at},
        )
        return [dict(row) for row in result.mappings().all()]
