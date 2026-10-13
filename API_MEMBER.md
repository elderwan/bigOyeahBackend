# FitBooking API Reference — Member APIs (`API_MEMBER.md`)

> **Base URL**: `http://localhost:8000/api/v1`  
> **Target Role**: `MEMBER` (`Authorization: Bearer <member_token>`)  
> **Unified Response Format**: All responses wrapped in `{ success, code, message, data, errors, meta, requestId, timestamp }`.

---

## 1. Member Profile & Account

### `GET /members/me`
Fetches the authenticated member's personal and membership profile.

- **Authentication**: `Authorization: Bearer <member_token>`
- **Response `data` (`MemberProfileResponse`)**:
  ```json
  {
    "member_id": 1,
    "user_id": 1,
    "username": "alex.demo",
    "display_name": "Alex Morgan",
    "email": "alex.demo@example.com",
    "phone": "+66812345678",
    "level_id": 2,
    "level_code": "GOLD",
    "level_name": "Gold Member",
    "discount_rate": 0.1,
    "total_spend": 22000.0,
    "gender": "MALE",
    "birth_date": "1996-06-14",
    "height_cm": 175.0,
    "weight_kg": 68.0,
    "fitness_goal": "Build muscle and improve strength"
  }
  ```

### `PATCH /members/me`
Updates personal body metrics, contact info, and goals.

- **Authentication**: `Authorization: Bearer <member_token>`
- **Request Body (`MemberProfileUpdate`)**:
  ```json
  {
    "display_name": "Alex Morgan",
    "email": "alex.new@example.com",
    "phone": "+66812345678",
    "gender": "MALE",
    "birth_date": "1996-06-14",
    "height_cm": 175.0,
    "weight_kg": 67.5,
    "fitness_goal": "Hypertrophy and core stability"
  }
  ```
- **Response `data`**: `MemberProfileResponse`.

---

## 2. Member Dashboard (`/member#home`)

### `GET /members/me/dashboard`
Aggregates personalized weekly stats, upcoming booking, and package balances for the member home screen.

- **Authentication**: `Authorization: Bearer <member_token>`
- **Response `data` (`MemberDashboardResponse`)**:
  ```json
  {
    "weekly_summary": {
      "workouts_done": 3,
      "workout_goal": 4,
      "goal_percentage": 75,
      "calories_burned": 1240,
      "active_minutes": 180,
      "streak_days": 5
    },
    "next_session": {
      "booking_id": 101,
      "course_name": "Strength & Conditioning",
      "booking_date": "2026-10-15",
      "start_time": "09:00:00",
      "coach_name": "Tan Chaiyaporn",
      "gym_name": "Nimman Fitness Club",
      "duration_minutes": 60
    },
    "upcoming_bookings": [],
    "active_packages": [
      {
        "package_id": 5,
        "package_type": "10+3",
        "remaining_sessions": 8,
        "total_sessions": 13,
        "expire_date": "2026-12-31"
      }
    ]
  }
  ```

---

## 3. Bookings (`/member#bookings`)

### `GET /members/me/bookings`
Retrieves list of all bookings for the member.

- **Query Parameters**:
  - `status` (optional): `PENDING`, `CONFIRMED`, `COMPLETED`, `CANCELLED`, `NO_SHOW`.
  - `date_from` (optional): `YYYY-MM-DD`.
  - `date_to` (optional): `YYYY-MM-DD`.
- **Response `data`**: Array of booking objects.

### `GET /members/me/bookings/{booking_id}`
Returns details of a specific booking.

### `POST /bookings` (Member Booking Creation)
Creates a personal training reservation on the 10-minute grid.

- **Request Body (`BookingCreateRequest`)**:
  ```json
  {
    "coach_id": 1,
    "course_id": 1,
    "gym_id": 1,
    "booking_date": "2026-10-18",
    "start_time": "10:00",
    "duration_minutes": 60,
    "break_minutes": 10,
    "service_mode": "GYM",
    "service_district": null,
    "service_address": null,
    "package_id": null
  }
  ```
- **Temporal Grid Rules**:
  - `start_time` minute must be `:00`, `:10`, `:20`, `:30`, `:40`, or `:50`.
  - `duration_minutes` must be a multiple of 10 (e.g. 50, 60, 70, 80).
  - `break_minutes` must be `10`, `20`, or `30`.
- **Response `data`**: `201 Created` with `BookingResponse`.

### `POST /members/me/bookings/{booking_id}/cancel`
Cancels a reservation.

- **Request Body**:
  ```json
  {
    "cancel_reason": "Schedule conflict"
  }
  ```
- **Response `data`**: Updated booking object (`status = 'CANCELLED'`). Restores package session balance if applicable.

---

## 4. Multi-Session Packages (`/member#packages`)

### `GET /members/me/packages`
Lists all session packages owned by the member (Active, Exhausted, Expired).

- **Response `data`**: Array of `member_package` items with `remaining_sessions` and `expire_date`.

### `POST /members/me/packages/purchase`
Purchases a package tier from the catalog.

- **Request Body**:
  ```json
  {
    "package_type": "10+3",
    "payment_method": "PROMPTPAY"
  }
  ```
- **Response `data`**: Newly issued `member_package` object with order receipt.

---

## 5. Fitness Progress & Body Measurements (`/member#progress`)

### `GET /members/me/progress`
Retrieves body composition trends and muscle training balance scores.

- **Response `data` (`ProgressDashboardResponse`)**:
  ```json
  {
    "body_metrics": {
      "weight_kg": 67.5,
      "height_cm": 175.0,
      "bmi": 22.0,
      "body_fat_percent": 16.5
    },
    "fitness_balance": {
      "strongest_area": "CORE",
      "strongest_score": 4.8,
      "weakest_area": "UPPER_BODY",
      "weakest_score": 3.6,
      "review_count": 8
    },
    "recent_measurements": [
      {
        "measurement_id": 1,
        "weight_kg": 67.5,
        "body_fat_percent": 16.5,
        "measured_at": "2026-10-10T08:00:00"
      }
    ],
    "weekly_sessions": []
  }
  ```

### `PUT /members/me/progress`
Logs a new weight and body fat measurement.

- **Request Body**:
  ```json
  {
    "weight_kg": 67.2,
    "body_fat_percent": 16.2
  }
  ```

---

## 6. Reviews & Session Feedback

### `GET /members/me/reviews`
Lists all reviews submitted by the member for past coaches.

### `POST /members/me/reviews`
Submits a multidimensional performance rating for a completed session.

- **Request Body**:
  ```json
  {
    "booking_id": 101,
    "rating_professional": 5,
    "rating_communication": 5,
    "rating_punctuality": 4,
    "rating_effectiveness": 5,
    "comment": "Exceptional form guidance on squats and deadlifts!"
  }
  ```
- **Constraints**: Each metric must be between `1` and `5`. `booking` must be in `COMPLETED` status.

---

## 7. Payments & Methods (`/member#payment`)

### `GET /members/me/payment-history`
Lists all transaction receipts from the `orders` table.

### `GET /members/me/payment-methods`
Lists saved credit cards / PromptPay tokens for 1-click checkout.

### `POST /members/me/payment-methods`
Saves a new payment method (tokenized).

- **Request Body**:
  ```json
  {
    "method_type": "CARD",
    "label": "Kasikorn Visa Card",
    "provider_token": "tok_1Nxxxxxx",
    "last_four": "4242",
    "is_default": 1
  }
  ```

### `DELETE /members/me/payment-methods/{payment_method_id}`
Soft deletes a payment method (`status = 'REMOVED'`).

---

## 8. Coach Messaging (`/member#messages`)

### `GET /members/me/messages?coach_id=1`
Fetches message thread between the member and a specific coach.

### `POST /members/me/messages`
Sends a message in the thread.

- **Request Body**:
  ```json
  {
    "coach_id": 1,
    "message_text": "Hi Coach Tan, do I need to bring lifting straps tomorrow?"
  }
  ```
