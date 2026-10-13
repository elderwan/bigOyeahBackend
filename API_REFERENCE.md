# FitBooking API reference for the frontend

Base URL:

```text
http://localhost:8000/api/v1
```

Replace the host with the deployed backend URL when the frontend is hosted
remotely. The frontend must send `Authorization: Bearer <access_token>` for
member profile requests.

All JSON responses use the common envelope:

```json
{
  "success": true,
  "code": 200,
  "message": "Success",
  "data": {},
  "errors": null,
  "meta": null,
  "requestId": "uuid",
  "timestamp": "2026-10-13T00:00:00Z"
}
```

The `data` object contains the endpoint return model documented below. Error
responses keep their HTTP status and use the same envelope with `success: false`.
Clients should send an optional `X-Request-ID`; the API generates one when it is
missing and returns it in the response header.

## 1. Sign in

```text
POST /auth/login
```

Request headers:

```text
Content-Type: application/json
```

Request body (`LoginRequest`):

```json
{
  "username": "alex",
  "password": "FitBooking123!"
}
```

`username` accepts either the account username or email address. The response
data type is `AuthResponse`:

```json
{
  "access_token": "token",
  "token_type": "bearer",
  "user": {
    "user_id": 1,
    "username": "alex",
    "display_name": "Alex Morgan",
    "email": "alex@example.com",
    "phone": "+66812345678",
    "role": "MEMBER",
    "status": "ACTIVE",
    "last_login_at": null,
    "created_at": "2026-10-13T00:00:00",
    "updated_at": "2026-10-13T00:00:00"
  }
}
```

Frontend usage:

1. Save `data.access_token` in the frontend auth store.
2. Save `data.user`.
3. Navigate to `/member#profile` after a member login.

Status codes: `200` success, `401` invalid credentials, `503` database
temporarily unavailable, `422` invalid request body.

## 2. Sign up

```text
POST /auth/register
```

Request body (`MemberRegisterRequest`):

```json
{
  "username": "new.member",
  "password": "StrongPass123!",
  "display_name": "New Member",
  "email": "new.member@example.com",
  "phone": "+66812345678",
  "gender": "FEMALE",
  "birth_date": "1996-06-14",
  "height_cm": 165.0,
  "weight_kg": 58.0,
  "fitness_goal": "Build strength"
}
```

The profile fields after `phone` are optional. The UI value
`"Prefer not to say"` is normalized to `null`. The response data type is the
same `AuthResponse` as sign-in, with HTTP status `201`.

Status codes: `201` created, `409` username/email/phone already registered,
`422` invalid request body.

## 3. Read member profile

```text
GET /members/me
```

Request headers:

```text
Authorization: Bearer <access_token>
```

Response data type: `MemberProfileResponse`.

```json
{
  "member_id": 1,
  "user_id": 1,
  "username": "alex",
  "display_name": "Alex Morgan",
  "email": "alex@example.com",
  "phone": "+66812345678",
  "level_id": 2,
  "level_code": "GOLD",
  "level_name": "Gold Member",
  "discount_rate": 0.1,
  "total_spend": 7850.0,
  "gender": "FEMALE",
  "birth_date": "1996-06-14",
  "height_cm": 165.0,
  "weight_kg": 58.0,
  "fitness_goal": "Build strength"
}
```

Status codes: `200` success, `401` missing/invalid token, `403` non-member
account, `404` profile not found.

## 4. Update member profile

```text
PATCH /members/me
```

Request headers:

```text
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request body (`MemberProfileUpdate`): send only fields being changed.

```json
{
  "display_name": "Alex Morgan",
  "email": "alex.new@example.com",
  "phone": "+66812345678",
  "gender": "FEMALE",
  "birth_date": "1996-06-14",
  "height_cm": 165.0,
  "weight_kg": 58.0,
  "fitness_goal": "Build strength and mobility"
}
```

The `username` is read-only and cannot be changed through this endpoint.
Response data type: `MemberProfileResponse`.

Status codes: `200` success, `401` missing/invalid token, `403` non-member
account, `422` invalid fields, `409` duplicate email or phone.

## Frontend fetch examples

```ts
const API_URL = "http://localhost:8000/api/v1";

const loginResponse = await fetch(`${API_URL}/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password }),
});
const login = await loginResponse.json();
if (!login.success) throw new Error(login.message);
localStorage.setItem("fitbooking_access_token", login.data.access_token);

const profileResponse = await fetch(`${API_URL}/members/me`, {
  headers: {
    Authorization: `Bearer ${localStorage.getItem("fitbooking_access_token")}`,
  },
});
const profile = await profileResponse.json();
```

The backend CORS configuration must include the frontend origin, for example:

```env
CORS_ORIGINS=["http://10.195.90.91:3000","http://localhost:3000"]
```

## Complete endpoint matrix

Every endpoint uses the envelope shown above. `data` is the typed response
model in the `response_model` declaration; validation and error responses use
`data: null`.

| Method and URL | Authentication | Success data | Error statuses |
|---|---|---|---|
| `GET /health` | None | health object | `500` |
| `POST /auth/register` | None | `AuthResponse` (`201`) | `409`, `422`, `500` |
| `POST /auth/login` | None | `AuthResponse` | `401`, `422`, `503`, `500` |
| `GET /auth/me` | Bearer | `UserResponse` | `401`, `500` |
| `GET /members/me` | Member Bearer | `MemberProfileResponse` | `401`, `403`, `404`, `500` |
| `PATCH /members/me` | Member Bearer | `MemberProfileResponse` | `401`, `403`, `409`, `422`, `500` |
| `GET /members/me/dashboard` | Member Bearer | `MemberDashboardResponse` | `401`, `403`, `404`, `500` |
| `GET /members/me/bookings` | Member Bearer | booking list | `401`, `403`, `422`, `500` |
| `GET /members/me/bookings/{booking_id}` | Member Bearer | booking detail | `401`, `403`, `404`, `500` |
| `POST /members/me/bookings/{booking_id}/cancel` | Member Bearer | cancelled booking | `401`, `403`, `404`, `409`, `422`, `500` |
| `GET /members/me/packages` | Member Bearer | package list | `401`, `403`, `500` |
| `POST /members/me/packages/purchase` | Member Bearer | package (`201`) | `401`, `403`, `404`, `409`, `422`, `500` |
| `GET /members/me/reviews` | Member Bearer | review list | `401`, `403`, `500` |
| `POST /members/me/reviews` | Member Bearer | review (`201`) | `401`, `403`, `409`, `422`, `500` |
| `GET /members/me/progress` | Member Bearer | `ProgressDashboardResponse` | `401`, `403`, `404`, `500` |
| `PUT /members/me/progress` | Member Bearer | progress dashboard | `401`, `403`, `422`, `500` |
| `GET /members/me/payment-history` | Member Bearer | order list | `401`, `403`, `500` |
| `GET /members/me/payment-methods` | Member Bearer | payment-method list | `401`, `403`, `500` |
| `POST /members/me/payment-methods` | Member Bearer | payment method (`201`) | `400`, `401`, `403`, `409`, `422`, `500` |
| `DELETE /members/me/payment-methods/{id}` | Member Bearer | `null` (`204`) | `401`, `403`, `404`, `500` |
| `GET /members/me/messages` | Member Bearer | message list | `401`, `403`, `422`, `500` |
| `POST /members/me/messages` | Member Bearer | `MessageResponse` (`201`) | `401`, `403`, `404`, `422`, `500` |
| `GET /courses` | None | course list | `422`, `500` |
| `GET /courses/{course_id}` | None | course | `404`, `500` |
| `GET /gyms` | None | gym list | `422`, `500` |
| `GET /packages` | None | active package catalog | `500` |
| `GET /coaches` | None | `CoachSearchResponse` | `422`, `500` |
| `GET /coaches/{coach_id}` | None | coach summary | `404`, `500` |
| `GET /coaches/{coach_id}/profile` | None | coach profile | `404`, `500` |
| `GET /coaches/{coach_id}/courses` | None | coach courses | `404`, `500` |
| `GET /coaches/{coach_id}/services` | None | coach services | `404`, `500` |
| `PATCH /coaches/me` | Coach Bearer | coach profile | `401`, `403`, `409`, `422`, `500` |
| `GET /coaches/{coach_id}/schedule/slots` | None | schedule slot list | `400`, `404`, `422`, `500` |
| `POST /coaches/{coach_id}/schedule` | Admin/coach Bearer | schedule metadata (`201`) | `400`, `401`, `403`, `404`, `500` |
| `POST /bookings` | Member Bearer | booking (`201`) | `400`, `401`, `403`, `409`, `422`, `500` |
| `GET /admin/dashboard` | Admin Bearer | dashboard | `401`, `403`, `500` |
| `GET /admin/audit-log` | Admin Bearer | audit records | `401`, `403`, `500` |

### Standard error contracts

`400`, `401`, `403`, `404`, `409`, `422`, and `500` all preserve the actual
HTTP status. Examples:

```json
{
  "success": false,
  "code": 409,
  "message": "The booking is not reviewable or already has a review",
  "data": null,
  "errors": [
    {
      "field": "booking_id",
      "code": "conflict",
      "message": "The resource conflicts with an existing record"
    }
  ],
  "meta": null,
  "requestId": "uuid",
  "timestamp": "2026-10-13T12:00:00Z"
}
```

Validation failures use FastAPI/Pydantic field locations and codes:

```json
{
  "success": false,
  "code": 422,
  "message": "Request validation failed",
  "data": null,
  "errors": [
    {
      "field": "body.start_time",
      "code": "value_error",
      "message": "start_time must align to a 10-minute grid"
    }
  ],
  "meta": null,
  "requestId": "uuid",
  "timestamp": "2026-10-13T12:00:00Z"
}
```

`500` responses never expose stack traces:

```json
{
  "success": false,
  "code": 500,
  "message": "Internal server error",
  "data": null,
  "errors": null,
  "meta": null,
  "requestId": "uuid",
  "timestamp": "2026-10-13T12:00:00Z"
}
```

## Database migration and seed

For an existing database, run `migrations/001_member_application.sql` after
`schema.sql`. It is idempotent and creates the persistent package catalog,
tokenized member payment-method records, member-coach messages, and historical
body measurements. `sample_data.sql` also upserts the three package offers.
Payment-card data must be represented by a provider token and optional last
four digits; raw card numbers are never accepted or stored.

## Member home

```text
GET /members/me/dashboard
```

Authentication: `Authorization: Bearer <access_token>`.

Returns `MemberDashboardResponse` with `profile`, `weekly_summary`,
`next_session`, `recommended_coaches`, `upcoming_bookings`, and
`active_packages`. `weekly_summary` contains `workouts_done`, `workout_goal`,
`goal_percentage`, `calories_burned`, `active_minutes`, and `streak_days`.

Success response (`200`):

```json
{
  "success": true,
  "code": 200,
  "message": "Success",
  "data": {
    "weekly_summary": {
      "workouts_done": 3,
      "workout_goal": 4,
      "goal_percentage": 75,
      "calories_burned": 1240,
      "active_minutes": 42,
      "streak_days": 5
    },
    "next_session": {
      "course_name": "Strength & Conditioning",
      "booking_date": "2026-10-13",
      "start_time": "09:10:00",
      "coach_name": "Tan Chaiyaporn",
      "gym_name": "Nimman Fitness Club",
      "duration_minutes": 60
    },
    "recommended_coaches": []
  },
  "errors": null,
  "meta": null,
  "requestId": "uuid",
  "timestamp": "2026-10-13T00:00:00Z"
}
```

Errors: `401` missing/expired token, `403` non-member, `404` member profile
missing, `500` generic server failure.

```ts
const home = await fetch(`${API_URL}/members/me/dashboard`, {
  headers: { Authorization: `Bearer ${token}` },
});
const homeEnvelope = await home.json();
```

## Explore coaches

```text
GET /coaches
```

Authentication is optional. Query parameters:

| Parameter | Type | Rules |
|---|---|---|
| `search` | string | Optional, maximum 100 characters; searches name, bio, and service area |
| `district` | string | Optional; `NIMMAN`, `OLD_CITY`, `CENTRAL`, `MAE_RIM`, or `HANG_DONG` |
| `course_id` | integer | Optional, greater than 0 |
| `service_mode` | string | Optional; `GYM`, `HOME`, or `BOTH` |
| `page` | integer | Optional, minimum 1, default 1 |
| `page_size` | integer | Optional, 1–50, default 12 |

Response type: `CoachSearchResponse`, containing `items`, `page`, `page_size`,
`total`, and `total_pages`. Each item includes photo URL, verified flag,
rating, review count, districts, service types, and price per session.

Errors: `400` invalid business filter, `422` invalid query parameter,
`500` generic server failure.

```ts
const params = new URLSearchParams({
  search,
  district: "NIMMAN",
  page: "1",
  page_size: "12",
});
const coaches = await fetch(`${API_URL}/coaches?${params}`);
```

## Progress dashboard

```text
GET /members/me/progress
```

Authentication: `Authorization: Bearer <access_token>`.

Response type: `ProgressDashboardResponse`. The baseline includes `weight`
in kilograms, `body_fat` in percent, and calculated `bmi` with a category.
The current schema does not store body-fat measurements, so `body_fat.value`
is `null` until a body-composition column or measurement table is added.
`weekly_activity` contains completed sessions for Monday–Sunday of the current
week, including date, day, start/end time, title, coach, status, and duration.

Errors: `401` missing/expired token, `403` non-member, `404` profile missing,
`422` invalid request, `500` generic server failure.

```ts
const progress = await fetch(`${API_URL}/members/me/progress`, {
  headers: { Authorization: `Bearer ${token}` },
});
```

## Common error envelopes

All endpoints preserve the HTTP status code.

```json
{
  "success": false,
  "code": 422,
  "message": "Request validation failed",
  "data": null,
  "errors": [
    {
      "field": "page_size",
      "code": "less_than_equal",
      "message": "Input should be less than or equal to 50"
    }
  ],
  "meta": null,
  "requestId": "uuid",
  "timestamp": "2026-10-13T00:00:00Z"
}
```

The same envelope shape is used for `400`, `401`, `403`, `404`, `409`, and
`500`; only `code`, `message`, and `errors` differ.
