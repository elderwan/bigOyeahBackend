from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Coach(Base):
    __tablename__ = "coach"

    coach_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_no: Mapped[str] = mapped_column(String(8))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    coach_level: Mapped[str] = mapped_column(String(20))
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_mode: Mapped[str] = mapped_column(String(10))
    break_interval: Mapped[int] = mapped_column(SmallInteger)
    years_experience: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    certifications: Mapped[str | None] = mapped_column(String(500), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(10))
    hired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Booking(Base):
    __tablename__ = "booking"

    booking_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    member_id: Mapped[int] = mapped_column(Integer)
    coach_id: Mapped[int] = mapped_column(Integer)
    course_id: Mapped[int] = mapped_column(Integer)
    gym_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    package_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    booking_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    duration_minutes: Mapped[int] = mapped_column(SmallInteger)
    break_minutes: Mapped[int] = mapped_column(SmallInteger)
    service_mode: Mapped[str] = mapped_column(String(4))
    service_district: Mapped[str | None] = mapped_column(String(20), nullable=True)
    service_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(10))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
