# FitBooking API Reference — Admin APIs (`API_ADMIN.md`)

> **Base URL**: `http://localhost:8000/api/v1`  
> **Target Role**: `ADMIN` (`Authorization: Bearer <admin_token>`)  
> **Unified Response Format**: All responses use the unified JSON envelope `{ success, code, message, data, errors, meta, requestId, timestamp }`.  
> **Security & Compliance**: Every request verifies `_require_admin`, checks temporal grid validation, applies status-based soft deletion, and writes an entry to `audit_log` with client IP address.

---

## Complete Admin Endpoint Directory

| Category | Method & URL | Description |
| :--- | :--- | :--- |
| **Overview** | `GET /admin/dashboard?days=30` | Top-level KPIs, booking trends, top trainers |
| | `GET /admin/activity?limit=10` | Real-time platform activity stream |
| **Audit Log** | `GET /admin/audit-log?...` | Query audit trail with multi-criteria filters |
| | `GET /admin/audit-log/{log_id}` | Detailed audit record |
| **Members** | `GET /admin/members?search=&status=&level_code=&page=&page_size=` | Paginated member directory |
| | `GET /admin/members/{user_id}` | Single member full profile & fitness stats |
| | `POST /admin/members` | Provision new member account |
| | `PUT /admin/members/{user_id}` | Full update of member profile & metrics |
| | `DELETE /admin/members/{user_id}` | Soft delete (status = `DISABLED`) |
| | `PATCH /admin/members/{user_id}/status` | Status toggle (`ACTIVE` / `DISABLED`) |
| **Trainers** | `GET /admin/coaches?search=&status=&coach_level=&page=&page_size=` | Paginated coach roster |
| | `GET /admin/coaches/{coach_id}` | Coach profile, assigned courses & gyms |
| | `POST /admin/coaches` | Onboard trainer with dynamic schedule provisioning |
| | `PUT /admin/coaches/{coach_id}` | Update coach bio, level, courses & gym junctions |
| | `DELETE /admin/coaches/{coach_id}` | Soft delete (status = `RESIGNED`) |
| | `PATCH /admin/coaches/{coach_id}/status` | Status toggle (`ACTIVE`, `ON_LEAVE`, `RESIGNED`) |
| | `POST /admin/coaches/{coach_id}/courses` | Assign course with custom price |
| | `GET /admin/coaches/{coach_id}/verification-documents` | Trainer verification documents list |
| | `POST /admin/coaches/{coach_id}/verify` | Approve / review coach verification |
| **Courses** | `POST /admin/courses` | Create new course with 10-minute grid duration |
| | `PUT /admin/courses/{course_id}` | Full update of course details & trainer links |
| | `DELETE /admin/courses/{course_id}` | Soft delete (is_active = 0) with conflict check |
| | `PATCH /admin/courses/{course_id}/status` | Toggle course availability (`is_active: 1 \| 0`) |
| **Locations** | `POST /admin/locations` | Create gym facility with trainer links |
| | `PUT /admin/locations/{gym_id}` | Full update of gym details & facilities |
| | `DELETE /admin/locations/{gym_id}` | Soft delete (is_active = 0) with conflict check |
| | `PATCH /admin/locations/{gym_id}/status` | Toggle location availability (`is_active: 1 \| 0`) |
| **Bookings** | `GET /admin/bookings?search=&status=&coach_id=&member_id=&date_from=&date_to=` | Filtered cross-platform bookings directory |
| | `GET /admin/bookings/{booking_id}` | Single booking full details |
| | `POST /admin/bookings` | Admin booking creation with schedule locking |
| | `PUT /admin/bookings/{booking_id}` | Reschedule date, time, coach, or gym |
| | `PATCH /admin/bookings/{booking_id}/status` | Status transition (`CONFIRMED`, `COMPLETED`, etc.) |
| | `POST /admin/bookings/{booking_id}/cancel` | Cancellation with refund & slot release |
| **Packages** | `POST /admin/packages` | Create package plan tier in catalogue |
| | `PUT /admin/packages/{package_type}` | Update package pricing, validity, sessions |
| | `DELETE /admin/packages/{package_type}` | Deactivate package (`is_active: 0`) |
| | `PATCH /admin/packages/{package_type}/status` | Toggle package availability (`is_active: 1 \| 0`) |
| **KPI** | `GET /admin/kpi?year=&month=` | KPI rules & coach snapshots overview |
| | `GET /admin/kpi/records?year=&month=&coach_id=` | Coach KPI performance records list |
| | `PUT /admin/kpi/rules/{coach_level}` | Update monthly thresholds for coach level |
| | `PUT /admin/kpi/records/{record_id}` | Manual override of coach KPI performance |
| | `POST /admin/kpi/recalculate?year=&month=` | Batch engine recalculating hours, rating, retention |
| **Revenue & Reports**| `GET /admin/revenue?days=30` | Revenue by order type and daily trend |
| | `POST /admin/reports/generate` | Aggregated report builder by coach/course/day |
| | `GET /admin/reports/export?date_from=&date_to=` | Export CSV report of bookings & revenue |
| **Settings** | `GET /admin/settings` | Read platform preferences |
| | `PATCH /admin/settings` | Update platform switches |

---

## 1. Overview & Activity (`/admin#adminOverview`)

### `GET /admin/dashboard?days=30`
Returns platform aggregate metrics and charts.

- **Query Parameters**: `days` (integer, default 30, 7–365).
- **Response `data`**:
  ```json
  {
    "totals": {
      "total_users": 150,
      "total_members": 142,
      "active_coaches": 8,
      "total_bookings": 420,
      "completed_bookings": 395,
      "revenue": 458900.0,
      "active_packages": 64
    },
    "booking_trend": [
      { "booking_date": "2026-10-01", "booking_count": 14, "completed_count": 14 }
    ],
    "top_coaches": [
      { "coach_id": 1, "coach_name": "Tan Chaiyaporn", "total_sessions": 38, "avg_rating": 4.95, "revenue_generated": 38000.0 }
    ],
    "period_days": 30
  }
  ```

### `GET /admin/activity?limit=10`
Returns the recent activity feed merged from `audit_log` events.

- **Response `data`**:
  ```json
  [
    {
      "id": 142,
      "title": "Admin Create Booking",
      "description": "Admin Demo performed ADMIN_CREATE_BOOKING on booking #52",
      "timestamp": "2026-10-13T14:20:00",
      "type": "booking",
      "actor": "Admin Demo",
      "action": "ADMIN_CREATE_BOOKING",
      "entity_id": 52
    }
  ]
  ```

---

## 2. Bookings Management (`/admin#adminBookings`)

### `GET /admin/bookings`
Multi-criteria searchable bookings list.

- **Query Parameters**:
  - `search` (string): Search member name, coach name, or course name.
  - `status` (string): `PENDING`, `CONFIRMED`, `COMPLETED`, `CANCELLED`, `NO_SHOW`.
  - `coach_id` (integer): Filter by coach ID.
  - `member_id` (integer): Filter by member ID.
  - `date_from` & `date_to`: Date filter range (`YYYY-MM-DD`).
  - `page` (default `1`) & `page_size` (default `20`).

### `GET /admin/bookings/{booking_id}`
Returns full booking record including member contact details, coach profile, gym information, and payment order record.

### `POST /admin/bookings` (Admin Create Booking)
Creates a booking with strict 10-minute temporal grid validation, schedule slot locking in `coach_schedule_<coach_id>`, and direct order creation.

- **Request Body**:
  ```json
  {
    "member_id": 1,
    "coach_id": 1,
    "course_id": 1,
    "booking_date": "2026-10-20",
    "start_time": "09:00",
    "duration_minutes": 60,
    "break_minutes": 10,
    "service_mode": "GYM",
    "gym_id": 1,
    "service_district": null,
    "service_address": null,
    "price": 1000.0,
    "status": "CONFIRMED",
    "package_id": null,
    "payment_method": "PROMPTPAY"
  }
  ```
- **Validation**:
  - `start_time` minute must be `:00`, `:10`, `:20`, `:30`, `:40`, or `:50`.
  - `duration_minutes` must be a multiple of 10.
  - `break_minutes` must be `10`, `20`, or `30`.

### `PUT /admin/bookings/{booking_id}` (Reschedule / Edit)
Allows modifying booking date, start time, duration, coach, or facility.

### `PATCH /admin/bookings/{booking_id}/status`
Transitions booking status (`PENDING -> CONFIRMED`, `CONFIRMED -> COMPLETED`, `* -> CANCELLED`, `CONFIRMED -> NO_SHOW`).

- **Request Body**:
  ```json
  {
    "status": "COMPLETED"
  }
  ```

### `POST /admin/bookings/{booking_id}/cancel` (Admin Cancellation & Refund)
Cancels booking, releases coach slots back to `AVAILABLE`, marks order as `REFUNDED` if `refund_issued == true`, and restores package credit if applicable.

- **Request Body**:
  ```json
  {
    "cancel_reason": "Member injury override",
    "refund_issued": true
  }
  ```

---

## 3. Courses Management (`/admin#adminCourses`)

### `POST /admin/courses` (Create Course)
Creates a new course and synchronizes trainer capabilities into `coach_course`.

- **Request Body**:
  ```json
  {
    "course_name": "Advance Power Training",
    "description": "Barbell power development and athletic conditioning.",
    "equipment": "Power racks, barbells, bumper plates",
    "difficulty": "ADVANCED",
    "default_duration": 70,
    "is_active": 1,
    "assigned_coach_ids": [1, 2]
  }
  ```
- **Validation**: `default_duration` must be a multiple of 10.

### `PUT /admin/courses/{course_id}` (Update Course)
Updates course fields and updates assigned coach associations.

### `DELETE /admin/courses/{course_id}` (Soft Delete / Archive)
Checks for active future bookings. If none exist, sets `course.is_active = 0` and `coach_course.is_active = 0`. Returns `409 Conflict` if upcoming bookings rely on the course.

### `PATCH /admin/courses/{course_id}/status`
Toggle status switch: `{"is_active": 1 | 0}`.

---

## 4. Locations Management (`/admin#adminLocations`)

### `POST /admin/locations` (Create Location)
Registers a fitness facility and assigns trainers to `coach_service`.

- **Request Body**:
  ```json
  {
    "gym_name": "Nimman Elite Fitness",
    "address": "Nimman Soi 11, Suthep, Chiang Mai",
    "district": "NIMMAN",
    "phone": "+6653001005",
    "facilities": "Power racks, Saunas, Ice bath, Lockers",
    "opening_time": "06:00:00",
    "closing_time": "22:00:00",
    "latitude": 18.7965,
    "longitude": 98.9680,
    "is_active": 1,
    "assigned_coach_ids": [1, 2]
  }
  ```

### `PUT /admin/locations/{gym_id}` (Update Location)
Updates address, hours, facilities, and synchronized trainer assignments.

### `DELETE /admin/locations/{gym_id}` (Soft Delete / Archive)
Verifies no upcoming active bookings exist, then sets `gym.is_active = 0`.

### `PATCH /admin/locations/{gym_id}/status`
Toggle status switch: `{"is_active": 1 | 0}`.

---

## 5. Trainers Management (`/admin#adminTrainers`)

### `GET /admin/coaches`
Paginated trainer directory with rating, level, status, and completed bookings count.

### `GET /admin/coaches/{coach_id}`
Returns trainer drawer details: profile, assigned courses (with custom rates), assigned gyms, and verification documents.

### `POST /admin/coaches` (Onboard New Coach)
Creates user (`role = 'COACH'`), coach record, links initial courses and gyms, and automatically provisions dynamic table `coach_schedule_<coach_id>`.

- **Request Body**:
  ```json
  {
    "username": "coach.somchai",
    "password": "InitialTempPass123!",
    "display_name": "Somchai Jaidee",
    "email": "somchai@fitbooking.local",
    "phone": "+66891234567",
    "coach_no": "1005",
    "coach_level": "ADVANCED",
    "service_mode": "BOTH",
    "break_interval": 10,
    "years_experience": 5,
    "certifications": "CSCS, ACE-CPT",
    "bio": "Specializes in Olympic weightlifting.",
    "assigned_location_ids": [1, 2],
    "assigned_course_ids": [1, 2]
  }
  ```

### `PUT /admin/coaches/{coach_id}` (Update Coach)
Updates trainer bio, certifications, level, and chip selector associations for courses and locations.

### `DELETE /admin/coaches/{coach_id}` (Soft Delete / Resign)
Sets `coach.status = 'RESIGNED'` and `users.status = 'DISABLED'`.

### `PATCH /admin/coaches/{coach_id}/status`
Updates status: `ACTIVE`, `ON_LEAVE`, or `RESIGNED`.

### `POST /admin/coaches/{coach_id}/courses`
Assigns course with custom rate:
```json
{
  "course_id": 1,
  "price_per_session": 1200.0,
  "is_active": 1
}
```

### `GET /admin/coaches/{coach_id}/verification-documents`
Returns verification state and certificates.

### `POST /admin/coaches/{coach_id}/verify`
Reviews/approves trainer verification:
```json
{
  "verified": true,
  "notes": "Certificates confirmed with ACE registry"
}
```

---

## 6. Members Management (`/admin#adminMembers`)

### `GET /admin/members`
Paginated member directory with membership tiers, total spend, and contact info.

### `GET /admin/members/{user_id}`
Detailed member drawer: user details, fitness profile balance, active packages count, and booking stats.

### `POST /admin/members`
Provisions new member account:
```json
{
  "username": "nattakarn.demo",
  "password": "DemoPass123!",
  "display_name": "Nattakarn S.",
  "email": "nattakarn@example.com",
  "phone": "+66819876543",
  "level_id": 2,
  "gender": "FEMALE",
  "birth_date": "1997-03-22",
  "height_cm": 165.0,
  "weight_kg": 56.0,
  "fitness_goal": "Improve core strength and mobility"
}
```

### `PUT /admin/members/{user_id}`
Full update of member profile and body metrics.

### `DELETE /admin/members/{user_id}`
Sets `users.status = 'DISABLED'`.

### `PATCH /admin/members/{user_id}/status`
Toggle status switch: `ACTIVE` / `DISABLED`.

---

## 7. Packages Management (`/admin#adminPackages`)

### `POST /admin/packages`
Creates new package tier in catalog:
```json
{
  "package_type": "15+5",
  "paid_sessions": 15,
  "bonus_sessions": 5,
  "price": 12500.0,
  "validity_days": 180,
  "is_active": 1
}
```

### `PUT /admin/packages/{package_type}`
Updates package pricing, validity days, or session breakdown.

### `DELETE /admin/packages/{package_type}`
Deactivates package (`is_active = 0`).

### `PATCH /admin/packages/{package_type}/status`
Toggle availability: `{"is_active": 1 | 0}`.

---

## 8. KPI Engine & Recalculation (`/admin#adminKpi`)

### `GET /admin/kpi?year=&month=`
Returns thresholds from `kpi_rule` and monthly performance snapshots from `coach_kpi_record`.

### `GET /admin/kpi/records?year=&month=&coach_id=`
Returns list of coach KPI performance snapshots.

### `PUT /admin/kpi/rules/{coach_level}`
Updates monthly target thresholds for a coach level:
```json
{
  "min_monthly_hours": 70.0,
  "min_avg_rating": 4.5,
  "min_retention_rate": 50.0
}
```

### `PUT /admin/kpi/records/{record_id}`
Manual adjustment/override of a coach's monthly KPI record:
```json
{
  "total_hours": 85.0,
  "avg_rating": 4.9,
  "retention_rate": 65.0,
  "is_achieved": 1
}
```

### `POST /admin/kpi/recalculate?year=2026&month=4`
Batch recalculation engine: aggregates completed sessions, hours, average review ratings, and member retention rates for all active coaches, compares them against `kpi_rule`, and updates `coach_kpi_record`.

---

## 9. Reports & Analytics (`/admin#adminReports`)

### `GET /admin/revenue?days=30`
Returns revenue breakdowns grouped by order type (Booking vs Package), payment method, and daily revenue timeline.

### `POST /admin/reports/generate`
Generates an aggregated report snapshot:
```json
{
  "report_name": "Trainer Performance & Utilization",
  "date_from": "2026-04-01",
  "date_to": "2026-04-30",
  "group_by": "coach",
  "measures": ["bookings", "revenue", "retention", "rating"]
}
```

### `GET /admin/reports/export?date_from=&date_to=`
Exports CSV file containing bookings, revenue, and status details.

---

## 10. Audit Log (`/admin#adminAudit`)

### `GET /admin/audit-log`
Queries the audit log trail with multi-criteria filters:
- `limit`: Default `50`.
- `entity_type`: Filter by table (`booking`, `gym`, `course`, `coach`, `users`, `system_settings`).
- `entity_id`: Record ID.
- `action`: Specific action code (`ADMIN_CREATE_BOOKING`, etc.).
- `user_id`: Filter by actor.
- `date_from` & `date_to`: Date range.

### `GET /admin/audit-log/{log_id}`
Returns single audit record detail.

---

## 11. Settings (`/admin#adminSettings`)

### `GET /admin/settings`
Returns platform settings:
```json
{
  "require_coach_verification": true,
  "booking_reminder_hours": 24,
  "package_catalogue_enabled": true,
  "audit_logging_enabled": true
}
```

### `PATCH /admin/settings`
Updates platform configuration switches:
```json
{
  "booking_reminder_hours": 48
}
```
Persists into `system_settings` table and logs event to `audit_log`.
