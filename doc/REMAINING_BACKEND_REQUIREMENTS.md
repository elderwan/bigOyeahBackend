# FitBooking — Remaining Backend Development & Production Readiness Requirements

> **Author**: Antigravity Frontend & Integration Pair Programming Agent  
> **Date**: October 13, 2026  
> **Target Audience**: Backend Development Team (FastAPI / SQLAlchemy / MySQL)  
> **Context**: Frontend has fully integrated all endpoints from `API_ADMIN.md`, `API_COACH.md`, `API_GENERAL.md`, and `API_MEMBER.md`. End-to-end authentication, role-based redirection, 10-minute grid temporal enforcement, and interactive CRUD operations have been verified with live seeded accounts:
> - **Admin**: `admin.demo` / `DemoPass123!` -> `/admin`
> - **Coach**: `tan.coach` / `DemoPass123!` -> `/trainer`
> - **Member**: `alex.demo` / `DemoPass123!` -> `/member#profile`

---

## 1. Integration Status Overview

The frontend has successfully wired and tested the following core modules against the live FastAPI service (`http://localhost:8000/api/v1`):

| Module | Endpoints Wired | Test Status |
| :--- | :--- | :--- |
| **Authentication & Profile** | `POST /auth/login`, `POST /auth/register`, `GET /auth/me`, `GET /members/me`, `PATCH /members/me`, `GET /coaches/me`, `PATCH /coaches/me` | ✅ **Passed**: Token generation, role detection, session enrichment, profile updates verified live. |
| **Admin Operations** | `GET /admin/dashboard`, `GET /admin/bookings`, `POST /admin/bookings`, `PUT /admin/bookings/{id}`, `PATCH /admin/bookings/{id}/status`, `POST /admin/bookings/{id}/cancel`, `GET /admin/members`, `POST /admin/members`, `PUT /admin/members/{id}`, `PATCH /admin/members/{id}/status`, `GET /admin/coaches`, `POST /admin/coaches`, `PUT /admin/coaches/{id}`, `POST /admin/coaches/{id}/verify`, `PATCH /admin/coaches/{id}/status`, `GET /gyms`, `POST /admin/locations`, `PUT /admin/locations/{id}`, `PATCH /admin/locations/{id}/status`, `GET /courses`, `POST /admin/courses`, `PUT /admin/courses/{id}`, `PATCH /admin/courses/{id}/status`, `GET /packages`, `POST /admin/packages`, `PUT /admin/packages/{id}`, `PATCH /admin/packages/{id}/status`, `GET /admin/kpi`, `PUT /admin/kpi/rules/{level}`, `PUT /admin/kpi/records/{id}`, `POST /admin/kpi/recalculate`, `GET /admin/settings`, `PATCH /admin/settings`, `GET /admin/audit-log`, `GET /admin/reports/export` | ✅ **Passed**: Form submissions, status toggles, drawer actions, KPI rules and recalculations live. |
| **Trainer Operations** | `GET /coaches/me`, `POST /coaches/{coach_id}/schedule`, `GET /coaches/{coach_id}/schedule/slots`, `POST /coaches/me/member-reviews`, `GET /coaches/me/messages`, `POST /coaches/me/messages` | ✅ **Passed**: Dynamic table slot generation in `coach_schedule_1001`, messages sending and retrieval. |
| **Member Operations** | `GET /members/me/dashboard`, `GET /members/me/bookings`, `POST /bookings`, `POST /members/me/bookings/{id}/cancel`, `GET /members/me/packages`, `POST /members/me/packages/purchase`, `GET /members/me/progress`, `POST /members/me/reviews`, `GET /members/me/messages`, `POST /members/me/messages` | ✅ **Passed**: Checkout reservation creation on 10-minute grid, cancellation with refund, reviews submission. |

---

## 2. Remaining Backend Requirements for Production

The following items represent architectural improvements, missing sub-features, or edge-case handlers identified during live frontend UI and database testing:

### 1. Granular Coach Slot Blocking / Ad-Hoc Leave API
- **Current State**: `POST /coaches/{coach_id}/schedule` generates schedule slots based on weekly availability rules up to an `until_date`.
- **Gap**: If a coach needs to block out a specific day or a 2-hour window (e.g., dentist appointment or emergency leave) without altering their general weekly recurring availability, there is currently no endpoint to mark specific slots as `BLOCKED` or delete them.
- **Recommended API**:
  ```http
  POST /api/v1/coaches/me/schedule/block
  ```
  **Payload**:
  ```json
  {
    "date": "2026-04-25",
    "start_time": "14:00",
    "end_time": "16:00",
    "reason": "Personal doctor appointment"
  }
  ```
  **Database Action**: Updates `status = 'BLOCKED'` in table `coach_schedule_<coach_id>` for all matching 10-minute intervals that are currently `AVAILABLE`. Rejects with error `409 Conflict` if any slot is already `BOOKED`.

---

### 2. Audit Log Advanced Filtering Parameters
- **Current State**: `GET /admin/audit-log` accepts `?limit=50`.
- **Gap**: The admin UI provides a "Filter events" modal where an administrator can filter by Actor, Action, Entity Type (`booking`, `gym`, `coach`, `users`, `kpi_rule`), and Date Range (`date_from`, `date_to`).
- **Recommended API Upgrade**:
  ```http
  GET /api/v1/admin/audit-log?entity_type=booking&action=STATUS_UPDATE&user_id=1&date_from=2026-04-01&date_to=2026-04-30&limit=50&offset=0
  ```

---

### 3. Automated Post-Review Aggregation Triggers
- **Current State**: `POST /members/me/reviews` writes a review record into `review_coach`. `POST /coaches/me/member-reviews` writes into `review_member`.
- **Gap**:
  1. The coach's public `average_rating` in `coach` table and `stats.avg_rating` in `/coaches/me` should be automatically recalculated from `AVG(avg_rating)` in `review_coach`.
  2. The coach's monthly `coach_kpi_record` for the corresponding month should recalculate `avg_rating` and update `is_achieved` against `kpi_rule`.
- **Recommended Action**: Implement an asynchronous DB trigger or SQLAlchemy `after_insert` hook on `review_coach` to maintain denormalized aggregates.

---

### 4. PromptPay QR Code Generation for Direct Payments
- **Current State**: `POST /members/me/packages/purchase` and `POST /bookings` simulate orders and store `payment_method: 'PROMPTPAY'`.
- **Gap**: When the member chooses PromptPay at checkout, they expect to see an EMVCo compliant PromptPay QR payload to scan in Thai banking apps (SCB, KBank, Bangkok Bank).
- **Recommended API**:
  ```http
  POST /api/v1/orders/{order_id}/qr
  ```
  **Response**:
  ```json
  {
    "order_id": 108,
    "amount": 800.0,
    "qr_payload": "00020101021229370016A000000677010111011300668123456785802TH53037645406800.005802TH6304ABCD",
    "expires_at": "2026-04-20T09:15:00Z"
  }
  ```

---

### 5. Automated Booking Session Lifecycle Daemon (Cron / Celery / APScheduler)
- **Current State**: Bookings stay `CONFIRMED` until someone manually toggles them to `COMPLETED` or cancels them.
- **Gap**: Sessions whose scheduled `end_time` has elapsed should automatically transition to `COMPLETED` (e.g. 1 hour after session finish time), or `NO_SHOW` if the member did not check in.
- **Recommended Action**: Add a light cron job in FastAPI (via `fastapi-utilities` or `APScheduler`):
  ```sql
  UPDATE booking 
  SET status = 'COMPLETED', updated_at = NOW() 
  WHERE status = 'CONFIRMED' 
    AND CONCAT(booking_date, ' ', end_time) < NOW() - INTERVAL 1 HOUR;
  ```

---

### 6. Real-Time Chat WebSocket / SSE Endpoint
- **Current State**: Chat messages in `/member#messages` and `/trainer#trainerMessages` use REST polling (`GET /members/me/messages`, `GET /coaches/me/messages`).
- **Gap**: Real-time two-way messaging is more interactive with WebSockets and avoids repeated HTTP polling.
- **Recommended API**:
  ```
  WebSocket: ws://localhost:8000/api/v1/ws/chat?token=<jwt_token>
  ```
  Enables instantaneous delivery of messages between `alex.demo` and `tan.coach`.

---

### 7. Export CSV Header Encoding (UTF-8 BOM for Thai Characters)
- **Current State**: `GET /admin/reports/export` streams CSV content.
- **Requirement**: Thai strings (e.g. district names `นิมมาน`, gym names, coach names) must include the UTF-8 BOM (`\xef\xbb\xbf`) at the beginning of the stream so Microsoft Excel for Windows opens Thai text without garbled characters.

---

## 3. Account Reference Matrix

The following accounts are pre-seeded in the database and fully verified end-to-end:

| Role | Username | Password | User ID | Relational ID | Default Redirection Route |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ADMIN** | `admin.demo` | `DemoPass123!` | 2 | N/A | `/admin` |
| **COACH** | `tan.coach` | `DemoPass123!` | 3 | `coach_id: 1` (`coach_no: "1001"`) | `/trainer` |
| **MEMBER** | `alex.demo` | `DemoPass123!` | 1 | `member_id: 1` (`GOLD`) | `/member#profile` |

All temporal constraints (10-minute grid multiples, 10/20/30 break intervals) and status-based soft deletions are strictly compliant across both backend triggers and frontend client components.
