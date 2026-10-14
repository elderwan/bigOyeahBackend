# FitBooking API Reference — General & Common APIs (`API_GENERAL.md`)

> **Base URL**: `http://localhost:8000/api/v1`  
> **Unified Response Standard**: All responses use the unified JSON envelope.

---

## 1. Unified JSON Envelope Standard

All responses from FitBooking endpoints conform to this structure:

### Success Response Envelope (`200 OK` / `201 Created`):
```json
{
  "success": true,
  "code": 200,
  "message": "Success",
  "data": {},
  "errors": null,
  "meta": null,
  "requestId": "c1f7b884-2b99-4d62-b94f-f3b145698bc2",
  "timestamp": "2026-10-13T14:30:00Z"
}
```

### Error Response Envelope (`400`, `401`, `403`, `404`, `409`, `422`, `500`):
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
      "message": "start_time minute must align to a 10-minute grid"
    }
  ],
  "meta": null,
  "requestId": "c1f7b884-2b99-4d62-b94f-f3b145698bc2",
  "timestamp": "2026-10-13T14:30:00Z"
}
```

---

## 2. Health & System Status

### `GET /health`
Returns system and database connectivity status.

- **Authentication**: None
- **Response `data`**:
  ```json
  {
    "status": "healthy",
    "timestamp": "2026-10-13T14:30:00Z"
  }
  ```

---

## 3. Common Authentication APIs

### `POST /auth/login`
Signs in a user (Member, Coach, or Admin).

- **Authentication**: None
- **Request Body (`LoginRequest`)**:
  ```json
  {
    "username": "alex.demo",
    "password": "DemoPass123!"
  }
  ```
  *(Accepts either username or email).*
- **Response `data` (`AuthResponse`)**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user": {
      "user_id": 1,
      "username": "alex.demo",
      "display_name": "Alex Morgan",
      "email": "alex.demo@example.com",
      "phone": "+66812345678",
      "role": "MEMBER",
      "status": "ACTIVE",
      "last_login_at": "2026-10-13T14:00:00",
      "created_at": "2026-10-12T00:00:00",
      "updated_at": "2026-10-13T14:00:00"
    }
  }
  ```

### `POST /auth/register`
Self-service registration for new Members.

- **Authentication**: None
- **Request Body (`MemberRegisterRequest`)**:
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
- **Response**: `201 Created` with `AuthResponse`.

### `GET /auth/me`
Retrieves currently authenticated user account metadata.

- **Authentication**: `Authorization: Bearer <token>`
- **Response `data`**: `UserResponse`.

---

## 4. Public Catalog & Resource Directory APIs

### 4.1 Courses Catalogue

#### `GET /courses`
Lists available training courses with optional filters and assigned trainer counts.

- **Query Parameters**:
  - `search` (string, optional): Search course name, description, or equipment.
  - `difficulty` (string, optional): `BEGINNER`, `INTERMEDIATE`, or `ADVANCED`.
  - `is_active` (integer, optional): `1` (active) or `0` (archived).
- **Response `data`**: Array of course items:
  ```json
  [
    {
      "course_id": 1,
      "course_name": "Strength & Conditioning",
      "description": "Full body barbell training and conditioning.",
      "equipment": "Barbells, racks, dumbbells",
      "difficulty": "INTERMEDIATE",
      "default_duration": 60,
      "is_active": 1,
      "coach_count": 4
    }
  ]
  ```

#### `GET /courses/{course_id}`
Returns details of a single course, including all assigned coaches and rates.

- **Response `data`**:
  ```json
  {
    "course_id": 1,
    "course_name": "Strength & Conditioning",
    "description": "Full body barbell training and conditioning.",
    "equipment": "Barbells, racks, dumbbells",
    "difficulty": "INTERMEDIATE",
    "default_duration": 60,
    "is_active": 1,
    "coaches": [
      {
        "coach_id": 1,
        "coach_no": "1001",
        "display_name": "Tan Chaiyaporn",
        "price_per_session": 1000.0
      }
    ],
    "assigned_coach_ids": [1]
  }
  ```

---

### 4.2 Gyms & Facilities Catalogue

#### `GET /gyms`
Lists partner gym facilities across Chiang Mai districts.

- **Query Parameters**:
  - `search` (string, optional): Search gym name, address, or facilities.
  - `district` (string, optional): `NIMMAN`, `OLD_CITY`, `CENTRAL`, `MAE_RIM`, `HANG_DONG`.
  - `is_active` (integer, optional): `1` or `0`.
- **Response `data`**: Array of gym objects:
  ```json
  [
    {
      "gym_id": 1,
      "gym_name": "Nimman Fitness Club",
      "address": "Nimmanhaemin Soi 6, Suthep, Chiang Mai",
      "district": "NIMMAN",
      "phone": "+6653001001",
      "facilities": "Power racks, Saunas, Shower, Lockers",
      "opening_time": "06:00:00",
      "closing_time": "22:00:00",
      "latitude": 18.796142,
      "longitude": 98.968601,
      "is_active": 1,
      "coach_count": 3
    }
  ]
  ```

#### `GET /gyms/{gym_id}`
Returns detail of a specific gym and coaches providing service at this facility.

---

### 4.3 Package Plans Catalogue

#### `GET /packages`
Lists standard multi-session package tiers.

- **Query Parameters**:
  - `is_active` (integer, optional): `1` or `0`.
- **Response `data`**:
  ```json
  [
    {
      "package_type": "5+1",
      "paid_sessions": 5,
      "bonus_sessions": 1,
      "price": 3400.0,
      "validity_days": 180,
      "is_active": 1
    },
    {
      "package_type": "10+3",
      "paid_sessions": 10,
      "bonus_sessions": 3,
      "price": 8970.0,
      "validity_days": 180,
      "is_active": 1
    },
    {
      "package_type": "20+7",
      "paid_sessions": 20,
      "bonus_sessions": 7,
      "price": 17550.0,
      "validity_days": 180,
      "is_active": 1
    }
  ]
  ```

#### `GET /packages/{package_type}`
Returns detail for a single package tier.

---

### 4.4 Explore Coaches (Public Roster)

#### `GET /coaches`
Public coach directory with multi-criteria search.

- **Query Parameters**:
  - `search`: Name or specialty text.
  - `district`: District enum.
  - `course_id`: Filter by course capability.
  - `service_mode`: `GYM`, `HOME`, or `BOTH`.
  - `page`: Default `1`.
  - `page_size`: Default `12` (max `50`).
- **Response `data`**: `CoachSearchResponse` containing `items`, `page`, `page_size`, `total`, `total_pages`.

#### `GET /coaches/{coach_id}`
Returns coach summary card.

#### `GET /coaches/{coach_id}/profile`
Returns full public coach profile with biography, certifications, experience, courses, and ratings.

#### `GET /coaches/{coach_id}/courses`
Returns all courses taught by this coach with pricing.

#### `GET /coaches/{coach_id}/services`
Returns all gyms and home service districts covered by this coach.

#### `GET /coaches/{coach_id}/schedule/slots`
Queries coach availability slots for a target date range.
- **Query Parameters**:
  - `date`: `YYYY-MM-DD`
  - `service_mode`: `GYM` or `HOME`
  - `gym_id`: Facility ID (when `GYM`)
  - `district`: District (when `HOME`)
- **Response `data`**: List of 10-minute slots (`slot_start`, `status: "AVAILABLE" | "BOOKED" | "LOCKED"`).
