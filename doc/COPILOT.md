# FitBooking Backend Coding Guide

## Product scope

FitBooking is a Chiang Mai personal-trainer booking platform. The reference UI covers member onboarding, dashboard, coach discovery and profiles, course selection, booking and checkout, booking history, packages/membership, reviews, fitness progress, member settings, and a coach/admin portal.

The current backend is FastAPI with asynchronous SQLAlchemy and MySQL 8.0.16+. The fixed schema in `schema.sql` is authoritative. The database uses `utf8mb4`, Chiang Mai business time (`+07:00`), InnoDB, and DECIMAL for money.

## Repository conventions

- Use Python 3.11+ style, type annotations, async route handlers, and `AsyncSession`.
- Use `snake_case` request and response fields to match MySQL.
- Use SQLAlchemy `text()` with bound parameters for all business values. Never interpolate frontend values into SQL.
- Dynamic schedule identifiers may only be derived from a database-read `coach.coach_no` and validated by `build_schedule_table_name`.
- Do not call `Base.metadata.create_all()`. The deployed database is created by the SQL scripts.
- Do not expose `users.password_hash`.
- Business records use status-based soft deletion. Do not physically delete users, coaches, bookings, orders, reviews, gyms, or courses.
- Booking, payment, package, and schedule-slot changes must use application transactions and row locks where required by `schema.sql`.
- Preserve the database ENUM values in API contracts; presentation translations belong in the frontend.

## API areas

- `/api/v1/auth`: member registration, login, and current-account lookup.
- `/api/v1/members`: authenticated member profile and dashboard data.
- `/api/v1/coaches`: public coach discovery/profile and authenticated coach profile updates.
- `/api/v1/bookings`: booking creation and future booking lifecycle operations.
- `/api/v1/coaches/{coach_id}/schedule`: dynamic schedule creation and slot reads.
- `/api/v1/courses`, `/api/v1/gyms`: public catalog data used by discovery and booking.
- `/api/v1/members/me/bookings`, `/api/v1/members/me/packages`, `/api/v1/members/me/reviews`: member activity and checkout data.
- `/api/v1/members/me/progress`: fitness profile and activity metrics.
- `/api/v1/admin`: protected dashboard and audit-log data.

Authentication uses a signed bearer token from `AUTH_SECRET`. Keep secrets in `.env`; never commit connection strings or credentials. In production, replace the development secret and run behind HTTPS.

## Database facts

`users` is the account table. `member` and `coach` are one-to-one extensions. Coach course and gym relationships are represented by `coach_course` and `coach_service`. Member packages are in `member_package`; bookings reference the member, coach/course pair, and optionally a package. The dynamic schedule table is registered in `schedule_registry`.

Important constraints include 10-minute schedule grids, booking durations divisible by 10, break intervals of 10/20/30 minutes, valid GYM versus HOME location fields, coach numbers of 4–8 digits, and package ownership enforced by a composite foreign key.

## Validation commands

```powershell
pytest
ruff check app tests
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Keep endpoint behavior aligned with the UI while preserving database invariants. Add focused tests for new validation, authorization, and transaction behavior.
