# FitBooking API Reference — Coach APIs (`API_COACH.md`)

> **Base URL**: `http://localhost:8000/api/v1`  
> **Target Role**: `COACH` (`Authorization: Bearer <coach_token>`)  
> **Unified Response Standard**: All endpoints wrapped in `{ success, code, message, data, errors, meta, requestId, timestamp }`.

---

## 1. Coach Self Profile

### `GET /coaches/me`
Fetches the currently authenticated trainer's profile, qualifications, assigned services, and aggregate stats.

- **Authentication**: `Authorization: Bearer <coach_token>`
- **Response `data` (`CoachProfileResponse`)**:
  ```json
  {
    "coach_id": 1,
    "user_id": 3,
    "coach_no": "1001",
    "display_name": "Tan Chaiyaporn",
    "email": "tan.coach@example.com",
    "phone": "+66812345680",
    "coach_level": "ADVANCED",
    "service_mode": "BOTH",
    "break_interval": 10,
    "years_experience": 5,
    "certifications": "CSCS, ACE-CPT",
    "bio": "Certified strength and conditioning coach with 5 years experience.",
    "avatar_url": "/avatars/coach_1001.png",
    "status": "ACTIVE",
    "hired_at": "2024-01-15",
    "stats": {
      "avg_rating": 4.95,
      "total_reviews": 42,
      "completed_sessions": 128
    },
    "courses": [
      {
        "course_id": 1,
        "course_name": "Strength & Conditioning",
        "price_per_session": 1000.0,
        "is_active": 1
      }
    ],
    "gyms": [
      {
        "gym_id": 1,
        "gym_name": "Nimman Fitness Club",
        "is_home_service": 0,
        "service_area": null
      }
    ]
  }
  ```

### `PATCH /coaches/me`
Allows the coach to update bio, phone, certifications, service mode, and default break interval.

- **Authentication**: `Authorization: Bearer <coach_token>`
- **Request Body**:
  ```json
  {
    "phone": "+66812345680",
    "bio": "Updated biography highlighting Olympic weightlifting guidance.",
    "break_interval": 10,
    "years_experience": 6,
    "certifications": "CSCS, ACE-CPT, USAW Level 1",
    "avatar_url": "/avatars/coach_1001_new.png"
  }
  ```
- **Constraints**: `break_interval` must be `10`, `20`, or `30`.

---

## 2. Dynamic Schedule Management

Each coach has a dedicated dynamic table `coach_schedule_<coach_id>` governed by the 10-minute grid rule.

### `GET /coaches/{coach_id}/schedule/slots`
Queries schedule slots for any calendar day or week.

- **Query Parameters**:
  - `date`: `YYYY-MM-DD`
  - `service_mode`: `GYM` or `HOME`
  - `gym_id`: Gym ID (when `GYM`)
  - `district`: Service area (when `HOME`)
- **Response `data`**: Array of slot objects:
  ```json
  [
    {
      "slot_start": "2026-10-18T08:00:00",
      "status": "AVAILABLE",
      "booking_id": null
    },
    {
      "slot_start": "2026-10-18T08:10:00",
      "status": "AVAILABLE",
      "booking_id": null
    },
    {
      "slot_start": "2026-10-18T09:00:00",
      "status": "BOOKED",
      "booking_id": 45
    }
  ]
  ```

### `POST /coaches/{coach_id}/schedule`
Generates or extends schedule slots for the coach up to a specified end date using their weekly availability template.

- **Authentication**: `Authorization: Bearer <coach_or_admin_token>`
- **Request Body**:
  ```json
  {
    "until_date": "2026-11-30"
  }
  ```
- **Response `data`**:
  ```json
  {
    "coach_id": 1,
    "table_name": "coach_schedule_1001",
    "generated_until": "2026-11-30",
    "slots_added": 240
  }
  ```

---

## 3. Session Evaluations & Member Reviews

### `POST /coaches/me/member-reviews`
After completing a training session, the coach evaluates the member's proficiency and notes progress areas.

- **Authentication**: `Authorization: Bearer <coach_token>`
- **Request Body**:
  ```json
  {
    "booking_id": 101,
    "completion_score": 5,
    "proficiency_score": 4,
    "training_area": "LOWER_BODY",
    "training_type": "STRENGTH",
    "coach_note": "Great hip hinge mechanics. Ready to increase squat load next week."
  }
  ```
- **Constraints**:
  - `completion_score` and `proficiency_score` between `1` and `5`.
  - `training_area`: `UPPER_BODY`, `CORE`, `LOWER_BODY`, `BACK`, `SHOULDER`, `FULL_BODY`.
  - `training_type`: `STRENGTH`, `CARDIO`, `FLEXIBILITY`, `BALANCE`, `POWER`.
- **Database Action**: Inserts into `review_member`, updates cached `fitness_profile` for the member.

---

## 4. Member Messaging

### `GET /coaches/me/messages?member_id=1`
Fetches conversation history with a specific member.

### `POST /coaches/me/messages`
Sends a reply to a member.

- **Authentication**: `Authorization: Bearer <coach_token>`
- **Request Body**:
  ```json
  {
    "member_id": 1,
    "message_text": "Looking forward to our session tomorrow at Nimman Fitness Club at 09:00."
  }
  ```

---

## 5. Schedule Slot Blocking (Leave Request)

### `POST /coaches/me/schedule/block`
Locks out a specific time range from being booked (e.g. for personal leave or doctor appointment).

- **Authentication**: `Authorization: Bearer <coach_token>`
- **Request Body**:
  ```json
  {
    "date": "2026-10-23",
    "start_time": "14:00",
    "end_time": "16:00",
    "reason": "Personal medical appointment"
  }
  ```
- **Rules**:
  - `start_time` and `end_time` must align to a 10-minute grid (`:00`, `:10`, `:20`, `:30`, `:40`, `:50`).
  - If any slot in the requested range is already `BOOKED`, returns `409 Conflict`.
  - Otherwise, matching slots in dynamic schedule table `coach_schedule_<coach_id>` are updated to `status = 'BLOCKED', remark = :reason`.
