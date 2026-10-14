-- ===========================================================================
-- FitBooking / Chiang Mai Personal Training Booking System
-- Database Manipulation Language (DML) Script
-- Targets: MySQL 8.0.16+
--
-- This script contains:
--   PART 1: Full Seed / Sample Data Initialization (直接可执行的全量测试基础数据)
--   PART 2: Core Operational Backend DML Templates (从 FastAPI 后端业务层提取的实时流转 DML 语句)
-- ===========================================================================

SET NAMES utf8mb4;
SET time_zone = '+07:00';
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY';

USE `fitbooking`;

-- ###########################################################################
-- PART 1: Full Seed / Sample Data Initialization
-- ###########################################################################

START TRANSACTION;

-- ---------------------------------------------------------------------------
-- 1. Package Catalog Offers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `package_catalog` (
    `package_type`     ENUM('5+1','10+3','20+7') NOT NULL,
    `paid_sessions`    SMALLINT UNSIGNED NOT NULL,
    `bonus_sessions`   SMALLINT UNSIGNED NOT NULL,
    `price`            DECIMAL(10,2) NOT NULL,
    `validity_days`    SMALLINT UNSIGNED NOT NULL,
    `is_active`        TINYINT(1) NOT NULL DEFAULT 1,
    `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`package_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO package_catalog
    (package_type, paid_sessions, bonus_sessions, price, validity_days, is_active)
VALUES
    ('5+1', 5, 1, 3400.00, 180, 1),
    ('10+3', 10, 3, 8970.00, 180, 1),
    ('20+7', 20, 7, 17550.00, 180, 1)
ON DUPLICATE KEY UPDATE
    paid_sessions = VALUES(paid_sessions),
    bonus_sessions = VALUES(bonus_sessions),
    price = VALUES(price),
    validity_days = VALUES(validity_days),
    is_active = VALUES(is_active);

-- ---------------------------------------------------------------------------
-- 2. System Accounts (Users)
-- Demo password for all accounts: DemoPass123!
-- ---------------------------------------------------------------------------
INSERT INTO users
    (username, password_hash, display_name, email, phone, role, status)
VALUES
    (
        'alex.demo',
        'scrypt$JTvlaHslAjKvJAmw9yOMpQ==$dxwiS-xEV44XtHv1TwjJzT9mUd9_e50oZuxDZ9h_eZKD52L4UfB88QNapD15zZA4i6ZmgiaYP6pWp3C34vsTEA==',
        'Alex Morgan',
        'alex.demo@example.com',
        '+66812345678',
        'MEMBER',
        'ACTIVE'
    ),
    (
        'maya.demo',
        'scrypt$JTvlaHslAjKvJAmw9yOMpQ==$dxwiS-xEV44XtHv1TwjJzT9mUd9_e50oZuxDZ9h_eZKD52L4UfB88QNapD15zZA4i6ZmgiaYP6pWp3C34vsTEA==',
        'Maya Demo',
        'maya.demo@example.com',
        '+66812345679',
        'MEMBER',
        'ACTIVE'
    ),
    (
        'tan.coach',
        'scrypt$JTvlaHslAjKvJAmw9yOMpQ==$dxwiS-xEV44XtHv1TwjJzT9mUd9_e50oZuxDZ9h_eZKD52L4UfB88QNapD15zZA4i6ZmgiaYP6pWp3C34vsTEA==',
        'Tan Chaiyaporn',
        'tan.coach@example.com',
        '+66812345680',
        'COACH',
        'ACTIVE'
    ),
    (
        'may.coach',
        'scrypt$JTvlaHslAjKvJAmw9yOMpQ==$dxwiS-xEV44XtHv1TwjJzT9mUd9_e50oZuxDZ9h_eZKD52L4UfB88QNapD15zZA4i6ZmgiaYP6pWp3C34vsTEA==',
        'May Suthida',
        'may.coach@example.com',
        '+66812345681',
        'COACH',
        'ACTIVE'
    ),
    (
        'admin.demo',
        'scrypt$JTvlaHslAjKvJAmw9yOMpQ==$dxwiS-xEV44XtHv1TwjJzT9mUd9_e50oZuxDZ9h_eZKD52L4UfB88QNapD15zZA4i6ZmgiaYP6pWp3C34vsTEA==',
        'FitBooking Admin',
        'admin.demo@example.com',
        '+66812345682',
        'ADMIN',
        'ACTIVE'
    )
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    status = 'ACTIVE';

SELECT user_id INTO @alex_user_id FROM users WHERE username = 'alex.demo';
SELECT user_id INTO @maya_user_id FROM users WHERE username = 'maya.demo';
SELECT user_id INTO @tan_user_id FROM users WHERE username = 'tan.coach';
SELECT user_id INTO @may_user_id FROM users WHERE username = 'may.coach';
SELECT user_id INTO @admin_user_id FROM users WHERE username = 'admin.demo';

-- ---------------------------------------------------------------------------
-- 3. Member Profiles
-- ---------------------------------------------------------------------------
INSERT INTO member
    (user_id, level_id, total_spend, gender, birth_date, height_cm, weight_kg, fitness_goal)
SELECT @alex_user_id, level_id, 22000.00, 'MALE', '1996-06-14', 175.0, 68.0,
       'Build muscle and improve strength'
FROM membership_level
WHERE level_code = 'GOLD'
ON DUPLICATE KEY UPDATE
    total_spend = VALUES(total_spend),
    gender = VALUES(gender),
    birth_date = VALUES(birth_date),
    height_cm = VALUES(height_cm),
    weight_kg = VALUES(weight_kg),
    fitness_goal = VALUES(fitness_goal);

INSERT INTO member
    (user_id, level_id, total_spend, gender, birth_date, height_cm, weight_kg, fitness_goal)
SELECT @maya_user_id, level_id, 6500.00, 'FEMALE', '1998-02-20', 162.0, 56.5,
       'Improve mobility and build a consistent routine'
FROM membership_level
WHERE level_code = 'SILVER'
ON DUPLICATE KEY UPDATE
    total_spend = VALUES(total_spend),
    gender = VALUES(gender),
    birth_date = VALUES(birth_date),
    height_cm = VALUES(height_cm),
    weight_kg = VALUES(weight_kg),
    fitness_goal = VALUES(fitness_goal);

SELECT member_id INTO @alex_member_id FROM member WHERE user_id = @alex_user_id;
SELECT member_id INTO @maya_member_id FROM member WHERE user_id = @maya_user_id;

-- ---------------------------------------------------------------------------
-- 4. Coaches & Venues (Gyms)
-- ---------------------------------------------------------------------------
INSERT INTO coach
    (coach_no, user_id, coach_level, bio, service_mode, break_interval,
     years_experience, certifications, avatar_url, status, hired_at)
VALUES
    (
        '1001', @tan_user_id, 'ADVANCED',
        'Certified strength coach focused on sustainable progress, mobility, and confidence.',
        'BOTH', 10, 6, 'NASM-CPT, Strength and Conditioning Specialist',
        'https://images.unsplash.com/photo-1583454110551-21f2fa2afe61',
        'ACTIVE', '2020-04-01'
    ),
    (
        '1002', @may_user_id, 'INTERMEDIATE',
        'Mobility, core control, and movement longevity for daily life.',
        'GYM', 10, 4, 'ACE-CPT, Certified Functional Strength Coach',
        'https://images.unsplash.com/photo-1594381898411-846e7d193883',
        'ACTIVE', '2022-09-01'
    )
ON DUPLICATE KEY UPDATE
    coach_level = VALUES(coach_level),
    service_mode = VALUES(service_mode),
    break_interval = VALUES(break_interval),
    years_experience = VALUES(years_experience),
    status = 'ACTIVE';

SELECT coach_id INTO @tan_coach_id FROM coach WHERE coach_no = '1001';
SELECT coach_id INTO @may_coach_id FROM coach WHERE coach_no = '1002';

INSERT INTO gym
    (gym_name, district, address, latitude, longitude, phone, opening_time, closing_time, is_active)
VALUES
    (
        'Nimman Fitness Club', 'NIMMAN', '45/2 Nimmanhaemin Rd, Suthep, Chiang Mai',
        18.7983000, 98.9687000, '+6653123456', '06:00:00', '22:00:00', 1
    ),
    (
        'Old City Training Studio', 'OLD_CITY', '12 Moon Muang Rd, Sri Phum, Chiang Mai',
        18.7883000, 98.9935000, '+6653123457', '07:00:00', '21:00:00', 1
    ),
    (
        'Central Strength Club', 'CENTRAL', '99/3 Huay Kaew Rd, Chang Phueak, Chiang Mai',
        18.8072000, 98.9564000, '+6653123458', '06:00:00', '23:00:00', 1
    )
ON DUPLICATE KEY UPDATE
    phone = VALUES(phone),
    opening_time = VALUES(opening_time),
    closing_time = VALUES(closing_time),
    is_active = 1;

SELECT gym_id INTO @nimman_gym_id FROM gym WHERE gym_name = 'Nimman Fitness Club';
SELECT gym_id INTO @old_city_gym_id FROM gym WHERE gym_name = 'Old City Training Studio';
SELECT gym_id INTO @central_gym_id FROM gym WHERE gym_name = 'Central Strength Club';

-- ---------------------------------------------------------------------------
-- 5. Courses & Coach-Course Pricing
-- ---------------------------------------------------------------------------
INSERT INTO course
    (course_name, description, difficulty, default_duration, default_break, is_active)
VALUES
    (
        'Strength & Conditioning',
        'Progressive overload, foundational movement patterns, and tailored barbell work.',
        'INTERMEDIATE', 60, 10, 1
    ),
    (
        'Mobility & Core',
        'Hip opening, shoulder health, deep core engagement, and joint longevity.',
        'BEGINNER', 60, 10, 1
    ),
    (
        'HIIT & Athletic Conditioning',
        'Interval training designed to improve work capacity, speed, and recovery.',
        'ADVANCED', 60, 10, 1
    )
ON DUPLICATE KEY UPDATE
    description = VALUES(description),
    difficulty = VALUES(difficulty),
    default_duration = VALUES(default_duration),
    default_break = VALUES(default_break),
    is_active = 1;

SELECT course_id INTO @strength_course_id FROM course WHERE course_name = 'Strength & Conditioning';
SELECT course_id INTO @mobility_course_id FROM course WHERE course_name = 'Mobility & Core';
SELECT course_id INTO @hiit_course_id FROM course WHERE course_name = 'HIIT & Athletic Conditioning';

INSERT INTO coach_course (coach_id, course_id, price_per_session, is_active)
VALUES
    (@tan_coach_id, @strength_course_id, 800.00, 1),
    (@tan_coach_id, @mobility_course_id, 750.00, 1),
    (@tan_coach_id, @hiit_course_id, 850.00, 1),
    (@may_coach_id, @mobility_course_id, 650.00, 1),
    (@may_coach_id, @strength_course_id, 700.00, 1)
ON DUPLICATE KEY UPDATE
    price_per_session = VALUES(price_per_session),
    is_active = 1;

INSERT INTO coach_service
    (coach_id, gym_id, is_home_service, service_area, is_active)
VALUES
    (@tan_coach_id, @nimman_gym_id, 0, NULL, 1),
    (@tan_coach_id, @old_city_gym_id, 0, NULL, 1),
    (@tan_coach_id, @central_gym_id, 1, 'NIMMAN', 1),
    (@may_coach_id, @old_city_gym_id, 0, NULL, 1)
ON DUPLICATE KEY UPDATE
    is_home_service = VALUES(is_home_service),
    service_area = VALUES(service_area),
    is_active = 1;

INSERT INTO coach_weekly_template (coach_id, weekday, start_time, end_time)
VALUES
    (@tan_coach_id, 1, '08:00:00', '18:00:00'),
    (@tan_coach_id, 3, '08:00:00', '18:00:00'),
    (@tan_coach_id, 5, '08:00:00', '18:00:00'),
    (@may_coach_id, 2, '09:00:00', '17:00:00'),
    (@may_coach_id, 4, '09:00:00', '17:00:00')
ON DUPLICATE KEY UPDATE
    end_time = VALUES(end_time);

-- ---------------------------------------------------------------------------
-- 6. Member Packages
-- ---------------------------------------------------------------------------
INSERT INTO member_package
    (member_id, package_type, total_sessions, remaining_sessions, price,
     purchase_date, expire_date, status)
SELECT @alex_member_id, '10+3', 13, 9, 8970.00, '2026-09-01', '2027-02-28', 'ACTIVE'
WHERE NOT EXISTS (
    SELECT 1 FROM member_package
    WHERE member_id = @alex_member_id AND package_type = '10+3'
      AND purchase_date = '2026-09-01'
);

INSERT INTO member_package
    (member_id, package_type, total_sessions, remaining_sessions, price,
     purchase_date, expire_date, status)
SELECT @maya_member_id, '5+1', 6, 6, 3400.00, '2026-10-01', '2027-03-30', 'ACTIVE'
WHERE NOT EXISTS (
    SELECT 1 FROM member_package
    WHERE member_id = @maya_member_id AND package_type = '5+1'
      AND purchase_date = '2026-10-01'
);

SELECT package_id INTO @alex_package_id
FROM member_package
WHERE member_id = @alex_member_id AND package_type = '10+3'
  AND purchase_date = '2026-09-01'
LIMIT 1;

SELECT package_id INTO @maya_package_id
FROM member_package
WHERE member_id = @maya_member_id AND package_type = '5+1'
  AND purchase_date = '2026-10-01'
LIMIT 1;

-- ---------------------------------------------------------------------------
-- 7. Bookings
-- ---------------------------------------------------------------------------
-- Completed booking
INSERT INTO booking
    (member_id, coach_id, course_id, gym_id, package_id, booking_date,
     start_time, end_time, duration_minutes, break_minutes, service_mode,
     service_district, service_address, price, status, completed_at)
SELECT
    @alex_member_id, @tan_coach_id, @strength_course_id, @nimman_gym_id,
    @alex_package_id, '2026-10-09', '08:00:00', '09:00:00', 60, 10, 'GYM',
    NULL, NULL, 800.00, 'COMPLETED', '2026-10-09 09:00:00'
WHERE NOT EXISTS (
    SELECT 1 FROM booking
    WHERE member_id = @alex_member_id AND coach_id = @tan_coach_id
      AND booking_date = '2026-10-09' AND start_time = '08:00:00'
);

-- Confirmed booking
INSERT INTO booking
    (member_id, coach_id, course_id, gym_id, package_id, booking_date,
     start_time, end_time, duration_minutes, break_minutes, service_mode,
     service_district, service_address, price, status)
SELECT
    @alex_member_id, @tan_coach_id, @strength_course_id, @nimman_gym_id,
    @alex_package_id, '2026-10-13', '09:10:00', '10:10:00', 60, 10, 'GYM',
    NULL, NULL, 800.00, 'CONFIRMED'
WHERE NOT EXISTS (
    SELECT 1 FROM booking
    WHERE member_id = @alex_member_id AND coach_id = @tan_coach_id
      AND booking_date = '2026-10-13' AND start_time = '09:10:00'
);

-- Pending booking
INSERT INTO booking
    (member_id, coach_id, course_id, gym_id, package_id, booking_date,
     start_time, end_time, duration_minutes, break_minutes, service_mode,
     service_district, service_address, price, status, expires_at)
SELECT
    @maya_member_id, @may_coach_id, @mobility_course_id, @old_city_gym_id,
    @maya_package_id, '2026-10-14', '10:30:00', '11:30:00', 60, 10, 'GYM',
    NULL, NULL, 750.00, 'PENDING', DATE_ADD(NOW(), INTERVAL 15 MINUTE)
WHERE NOT EXISTS (
    SELECT 1 FROM booking
    WHERE member_id = @maya_member_id AND coach_id = @may_coach_id
      AND booking_date = '2026-10-14' AND start_time = '10:30:00'
);

SELECT booking_id INTO @completed_booking_id
FROM booking
WHERE member_id = @alex_member_id AND booking_date = '2026-10-09'
  AND start_time = '08:00:00'
LIMIT 1;

SELECT booking_id INTO @confirmed_booking_id
FROM booking
WHERE member_id = @alex_member_id AND booking_date = '2026-10-13'
  AND start_time = '09:10:00'
LIMIT 1;

SELECT booking_id INTO @pending_booking_id
FROM booking
WHERE member_id = @maya_member_id AND booking_date = '2026-10-14'
  AND start_time = '10:30:00'
LIMIT 1;

-- ---------------------------------------------------------------------------
-- 8. Orders Ledger
-- ---------------------------------------------------------------------------
INSERT INTO orders
    (order_type, booking_id, total_amount, discount, final_amount,
     payment_method, payment_status, payment_time)
SELECT 'BOOKING', @completed_booking_id, 800.00, 80.00, 720.00,
       'PROMPTPAY', 'PAID', '2026-10-09 07:50:00'
WHERE NOT EXISTS (
    SELECT 1 FROM orders WHERE booking_id = @completed_booking_id
);

INSERT INTO orders
    (order_type, booking_id, total_amount, discount, final_amount,
     payment_method, payment_status, payment_time)
SELECT 'BOOKING', @confirmed_booking_id, 800.00, 80.00, 720.00,
       'PACKAGE_CREDIT', 'PAID', '2026-10-12 20:00:00'
WHERE NOT EXISTS (
    SELECT 1 FROM orders WHERE booking_id = @confirmed_booking_id
);

INSERT INTO orders
    (order_type, booking_id, total_amount, discount, final_amount,
     payment_method, payment_status, payment_time)
SELECT 'BOOKING', @pending_booking_id, 750.00, 75.00, 675.00,
       'PROMPTPAY', 'UNPAID', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM orders WHERE booking_id = @pending_booking_id
);

INSERT INTO orders
    (order_type, package_id, total_amount, discount, final_amount,
     payment_method, payment_status, payment_time)
SELECT 'PACKAGE', @alex_package_id, 8970.00, 0.00, 8970.00,
       'PROMPTPAY', 'PAID', '2026-09-01 10:00:00'
WHERE NOT EXISTS (
    SELECT 1 FROM orders WHERE package_id = @alex_package_id
);

-- ---------------------------------------------------------------------------
-- 9. Fitness Profiles, Reviews, KPI Records, and Audit Logs
-- ---------------------------------------------------------------------------
INSERT INTO fitness_profile
    (member_id, strongest_area, weakest_area, strongest_score, weakest_score, review_count)
VALUES
    (@alex_member_id, 'LOWER_BODY', 'SHOULDER', 4.60, 3.20, 1),
    (@maya_member_id, 'CORE', 'UPPER_BODY', 4.20, 3.50, 0)
ON DUPLICATE KEY UPDATE
    strongest_area = VALUES(strongest_area),
    weakest_area = VALUES(weakest_area),
    strongest_score = VALUES(strongest_score),
    weakest_score = VALUES(weakest_score),
    review_count = VALUES(review_count);

INSERT INTO review_coach
    (booking_id, reviewer_id, rating_professional, rating_communication,
     rating_punctuality, rating_effectiveness, comment)
SELECT @completed_booking_id, @alex_member_id, 5, 5, 5, 4,
       'Coach Tan is motivating, professional, and keeps every session focused.'
WHERE NOT EXISTS (
    SELECT 1 FROM review_coach WHERE booking_id = @completed_booking_id
);

INSERT INTO review_member
    (booking_id, coach_id, member_id, completion_score, proficiency_score,
     training_area, training_type, coach_note)
SELECT @completed_booking_id, @tan_coach_id, @alex_member_id, 5, 4,
       'LOWER_BODY', 'STRENGTH', 'Excellent effort and consistent form.'
WHERE NOT EXISTS (
    SELECT 1 FROM review_member WHERE booking_id = @completed_booking_id
);

INSERT INTO coach_kpi_record
    (coach_id, kpi_year, kpi_month, total_hours, completed_sessions,
     avg_rating, retention_rate, target_hours, target_avg_rating,
     target_retention_rate, is_achieved)
SELECT @tan_coach_id, 2026, 10, 76.50, 24, 4.90, 82.00,
       min_monthly_hours, min_avg_rating, min_retention_rate, 1
FROM kpi_rule
WHERE coach_level = 'ADVANCED'
ON DUPLICATE KEY UPDATE
    total_hours = VALUES(total_hours),
    completed_sessions = VALUES(completed_sessions),
    avg_rating = VALUES(avg_rating),
    retention_rate = VALUES(retention_rate),
    is_achieved = VALUES(is_achieved);

INSERT INTO audit_log
    (user_id, action, entity_type, entity_id, detail, ip_address)
VALUES
    (
        @admin_user_id, 'DEMO_DATA_SEEDED', 'SYSTEM', NULL,
        JSON_OBJECT('source', 'dml.sql', 'purpose', 'CMU DB Term Project DML Delivery'),
        '127.0.0.1'
    );

-- ---------------------------------------------------------------------------
-- 10. Dynamic Schedule Grid Initialization (Coach 1001)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `coach_schedule_1001` (
    `slot_start` DATETIME NOT NULL,
    `slot_year` SMALLINT UNSIGNED GENERATED ALWAYS AS (YEAR(`slot_start`)) STORED,
    `slot_month` TINYINT UNSIGNED GENERATED ALWAYS AS (MONTH(`slot_start`)) STORED,
    `slot_day` TINYINT UNSIGNED GENERATED ALWAYS AS (DAY(`slot_start`)) STORED,
    `slot_hour` TINYINT UNSIGNED GENERATED ALWAYS AS (HOUR(`slot_start`)) STORED,
    `slot_minute` TINYINT UNSIGNED GENERATED ALWAYS AS (MINUTE(`slot_start`)) STORED,
    `status` ENUM('AVAILABLE','BOOKED','BREAK','BLOCKED') NOT NULL DEFAULT 'AVAILABLE',
    `booking_id` BIGINT UNSIGNED NULL,
    `remark` VARCHAR(100) NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`slot_start`),
    KEY `idx_cs_1001_status` (`status`, `slot_start`),
    KEY `idx_cs_1001_booking` (`booking_id`),
    CONSTRAINT `chk_cs_1001_grid`
        CHECK (MINUTE(`slot_start`) % 10 = 0 AND SECOND(`slot_start`) = 0),
    CONSTRAINT `chk_cs_1001_booking`
        CHECK (
            (`status` IN ('BOOKED','BREAK') AND `booking_id` IS NOT NULL)
            OR (`status` IN ('AVAILABLE','BLOCKED') AND `booking_id` IS NULL)
        ),
    CONSTRAINT `fk_cs_1001_booking`
        FOREIGN KEY (`booking_id`) REFERENCES booking (`booking_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO schedule_registry (coach_id, table_name, generated_until, status)
VALUES (@tan_coach_id, 'coach_schedule_1001', '2026-10-20', 'ACTIVE')
ON DUPLICATE KEY UPDATE
    table_name = VALUES(table_name),
    generated_until = VALUES(generated_until),
    status = 'ACTIVE';

INSERT INTO coach_schedule_1001 (slot_start)
WITH RECURSIVE
    days AS (
        SELECT DATE('2026-10-09') AS slot_date
        UNION ALL
        SELECT slot_date + INTERVAL 1 DAY
        FROM days
        WHERE slot_date < DATE('2026-10-20')
    ),
    slots AS (
        SELECT 0 AS slot_number
        UNION ALL
        SELECT slot_number + 1
        FROM slots
        WHERE slot_number < 60
    )
SELECT TIMESTAMP(slot_date, '08:00:00') + INTERVAL (slot_number * 10) MINUTE
FROM days
CROSS JOIN slots
ON DUPLICATE KEY UPDATE slot_start = VALUES(slot_start);

UPDATE coach_schedule_1001
SET status = CASE
        WHEN slot_start < TIMESTAMP('2026-10-09', '09:00:00') THEN 'BOOKED'
        ELSE 'BREAK'
    END,
    booking_id = @completed_booking_id
WHERE slot_start >= TIMESTAMP('2026-10-09', '08:00:00')
  AND slot_start < TIMESTAMP('2026-10-09', '09:10:00');

UPDATE coach_schedule_1001
SET status = CASE
        WHEN slot_start < TIMESTAMP('2026-10-13', '10:10:00') THEN 'BOOKED'
        ELSE 'BREAK'
    END,
    booking_id = @confirmed_booking_id
WHERE slot_start >= TIMESTAMP('2026-10-13', '09:10:00')
  AND slot_start < TIMESTAMP('2026-10-13', '10:20:00');

COMMIT;


-- ###########################################################################
-- PART 2: Core Operational Backend DML Templates
-- (Extracted directly from FastAPI services and route handlers)
-- ###########################################################################

-- ===========================================================================
-- Scenario 1: Member Authentication & Profile Lifecycle
-- Source: backend/app/api/routes/auth.py & members.py
-- ===========================================================================

-- 1.1 Register New Member Account
-- Inserts credential record into users, then links business profile in member.
START TRANSACTION;
INSERT INTO users (
    username, password_hash, display_name, email, phone, role, status
) VALUES (
    'john.doe', '$scrypt$demo_hash_sample_value', 'John Doe',
    'john.doe@example.com', '+66899998888', 'MEMBER', 'ACTIVE'
);
SET @new_user_id = LAST_INSERT_ID();

INSERT INTO member (
    user_id, level_id, total_spend, gender, birth_date, height_cm, weight_kg, fitness_goal
) VALUES (
    @new_user_id, 1, 0.00, 'MALE', '1995-05-15', 180.0, 75.0, 'Fat loss and functional agility'
);
COMMIT;

-- 1.2 Record Successful User Login Timestamp
UPDATE users
SET last_login_at = NOW()
WHERE user_id = @new_user_id;

-- 1.3 Update Member Profile Settings
UPDATE member
SET display_name = 'John D.',
    phone = '+66899998899',
    gender = 'MALE',
    birth_date = '1995-05-15',
    height_cm = 180.5,
    weight_kg = 74.2,
    fitness_goal = 'Hypertrophy and core stability'
WHERE member_id = 1;


-- ===========================================================================
-- Scenario 2: Coach Schedule Availability & Slot Blocking / Unblocking
-- Source: backend/app/api/routes/schedules.py & coaches.py
-- ===========================================================================

-- 2.1 Coach Locks Schedule Slot for Personal Leave
-- Validates no existing booking occupies the slot, then marks slots as BLOCKED.
START TRANSACTION;
-- Verify no conflict
SELECT COUNT(*) AS conflict_count
FROM coach_schedule_1001
WHERE slot_start >= '2026-10-25 14:00:00'
  AND slot_start < '2026-10-25 16:00:00'
  AND status = 'BOOKED'
FOR UPDATE;

-- If conflict_count = 0:
UPDATE coach_schedule_1001
SET status = 'BLOCKED', remark = 'Personal medical appointment'
WHERE slot_start >= '2026-10-25 14:00:00'
  AND slot_start < '2026-10-25 16:00:00'
  AND status = 'AVAILABLE';
COMMIT;

-- 2.2 Coach Unblocks Previously Locked Schedule Slot
UPDATE coach_schedule_1001
SET status = 'AVAILABLE', remark = NULL
WHERE slot_start >= '2026-10-25 14:00:00'
  AND slot_start < '2026-10-25 16:00:00'
  AND status = 'BLOCKED';


-- ===========================================================================
-- Scenario 3: Course Booking & Order Generation (Core Booking Transaction)
-- Source: backend/app/services/booking_service.py
-- ===========================================================================

START TRANSACTION;

-- 3.1 Lock and Verify Slot Availability (Pessimistic Locking)
SELECT slot_start, status
FROM coach_schedule_1001
WHERE slot_start >= '2026-10-18 10:00:00'
  AND slot_start < '2026-10-18 11:10:00'
FOR UPDATE;

-- 3.2 Insert Booking Master Record
-- Calculates automatic discount based on member's current level
INSERT INTO booking (
    member_id, coach_id, course_id, gym_id, package_id,
    booking_date, start_time, end_time,
    duration_minutes, break_minutes, service_mode,
    service_district, service_address, price, status, expires_at
) VALUES (
    1, 1, 1, 1, NULL,
    '2026-10-18', '10:00:00', '11:00:00',
    60, 10, 'GYM',
    NULL, NULL, 720.00, 'PENDING', DATE_ADD(NOW(), INTERVAL 15 MINUTE)
);
SET @created_booking_id = LAST_INSERT_ID();

-- 3.3 Create Associated Financial Order
INSERT INTO orders (
    order_type, booking_id, total_amount, discount, final_amount, payment_status
) VALUES (
    'BOOKING', @created_booking_id, 800.00, 80.00, 720.00, 'UNPAID'
);
SET @created_order_id = LAST_INSERT_ID();

-- 3.4 Update Schedule Grid Slots (Training slots -> BOOKED; Break slot -> BREAK)
UPDATE coach_schedule_1001
SET status = CASE
        WHEN slot_start < '2026-10-18 11:00:00' THEN 'BOOKED'
        ELSE 'BREAK'
    END,
    booking_id = @created_booking_id
WHERE slot_start >= '2026-10-18 10:00:00'
  AND slot_start < '2026-10-18 11:10:00';

COMMIT;


-- ===========================================================================
-- Scenario 4: Package Purchase & Order Activation Transaction
-- Source: backend/app/api/routes/member_features.py (purchase_package)
-- ===========================================================================

START TRANSACTION;

-- 4.1 Lookup Catalog Offer
SELECT paid_sessions, bonus_sessions, price, validity_days
FROM package_catalog
WHERE package_type = '5+1' AND is_active = 1;

-- 4.2 Insert Member Package Asset
INSERT INTO member_package (
    member_id, package_type, total_sessions, remaining_sessions,
    price, purchase_date, expire_date, status
) VALUES (
    1, '5+1', 6, 6,
    3400.00, CURDATE(), DATE_ADD(CURDATE(), INTERVAL 180 DAY), 'ACTIVE'
);
SET @new_package_id = LAST_INSERT_ID();

-- 4.3 Create Associated Package Purchase Order
INSERT INTO orders (
    order_type, package_id, total_amount, discount, final_amount,
    payment_method, payment_status, payment_time
) VALUES (
    'PACKAGE', @new_package_id, 3400.00, 0.00, 3400.00,
    'PROMPTPAY', 'PAID', NOW()
);
SET @package_order_id = LAST_INSERT_ID();

COMMIT;


-- ===========================================================================
-- Scenario 5: Simulated / PromptPay Payment Settlement & Auto Tier Upgrade
-- Source: backend/app/api/routes/orders.py (mock_confirm_order_payment)
-- ===========================================================================

START TRANSACTION;

-- 5.1 Lock Order Row for Update
SELECT * FROM orders WHERE order_id = @created_order_id FOR UPDATE;

-- 5.2 Mark Order as PAID with Timestamp
UPDATE orders
SET payment_status = 'PAID',
    payment_time = NOW(),
    updated_at = NOW()
WHERE order_id = @created_order_id;

-- 5.3 Activate Booking
UPDATE booking
SET status = 'CONFIRMED',
    updated_at = NOW()
WHERE booking_id = @created_booking_id AND status = 'PENDING';

-- 5.4 Accumulate Member Total Spend
UPDATE member
SET total_spend = total_spend + 720.00
WHERE member_id = 1;

-- 5.5 Automatic Membership Tier Evaluation & Upgrade
UPDATE member
SET level_id = (
    SELECT level_id
    FROM membership_level
    WHERE min_total_spend <= (SELECT total_spend FROM (SELECT total_spend FROM member WHERE member_id = 1) AS m)
    ORDER BY min_total_spend DESC, sort_order DESC
    LIMIT 1
)
WHERE member_id = 1;

COMMIT;


-- ===========================================================================
-- Scenario 6: Booking Cancellation & Schedule Slot Release
-- Source: backend/app/api/routes/member_features.py (cancel_my_booking)
-- ===========================================================================

START TRANSACTION;

-- 6.1 Update Booking Status to CANCELLED
UPDATE booking
SET status = 'CANCELLED',
    cancelled_by = 'MEMBER',
    cancel_reason = 'Schedule conflict',
    updated_at = NOW()
WHERE booking_id = @created_booking_id
  AND member_id = 1
  AND status IN ('PENDING', 'CONFIRMED');

-- 6.2 Cancel Pending Order
UPDATE orders
SET payment_status = 'CANCELLED',
    updated_at = NOW()
WHERE booking_id = @created_booking_id AND payment_status = 'UNPAID';

-- 6.3 Release Occupied Schedule Grid Slots Back to AVAILABLE
UPDATE coach_schedule_1001
SET status = 'AVAILABLE',
    booking_id = NULL
WHERE booking_id = @created_booking_id;

-- 6.4 Refund Package Session Credit (if booked via package)
-- UPDATE member_package
-- SET remaining_sessions = remaining_sessions + 1,
--     status = 'ACTIVE'
-- WHERE package_id = :pkg_id;

COMMIT;


-- ===========================================================================
-- Scenario 7: Post-Session Trainee Evaluation & Coach Reviews
-- Source: backend/app/api/routes/member_features.py & coaches.py
-- ===========================================================================

-- 7.1 Member Reviews Coach After Session Completion
INSERT INTO review_coach (
    booking_id, reviewer_id,
    rating_professional, rating_communication,
    rating_punctuality, rating_effectiveness,
    comment
) VALUES (
    @confirmed_booking_id, 1,
    5, 5, 5, 5,
    'Exceptional workout! Coach Tan customized the intensity perfectly for my shoulder recovery.'
);

-- 7.2 Coach Evaluates Trainee Performance & Biometrics
INSERT INTO review_member (
    booking_id, coach_id, member_id,
    completion_score, proficiency_score,
    training_area, training_type, coach_note
) VALUES (
    @confirmed_booking_id, 1, 1,
    5, 4,
    'LOWER_BODY', 'STRENGTH',
    'Demonstrated solid bracing on Romanian deadlifts. Increased working set weight by 5kg.'
);


-- ===========================================================================
-- Scenario 8: Member-Coach Real-Time Messaging Stream
-- Source: backend/app/api/routes/member_features.py & chat_ws.py
-- ===========================================================================

CREATE TABLE IF NOT EXISTS `member_message` (
    `message_id`      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `member_id`       INT UNSIGNED NOT NULL,
    `coach_id`        INT UNSIGNED NOT NULL,
    `sender_role`     ENUM('MEMBER','COACH') NOT NULL,
    `message_text`    VARCHAR(2000) NOT NULL,
    `read_at`         DATETIME NULL,
    `created_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 8.1 Trainee Sends Message to Coach
INSERT INTO member_message (
    member_id, coach_id, sender_role, message_text, read_at
) VALUES (
    1, 1, 'MEMBER', 'Hi Coach Tan, do I need to bring my own lifting straps tomorrow?', NULL
);

-- 8.2 Coach Replies to Trainee
INSERT INTO member_message (
    member_id, coach_id, sender_role, message_text, read_at
) VALUES (
    1, 1, 'COACH', 'Not needed! We have professional gym straps at Nimman Fitness Club.', NULL
);

-- 8.3 Mark Unread Messages as Read
UPDATE member_message
SET read_at = NOW()
WHERE member_id = 1 AND coach_id = 1 AND sender_role = 'MEMBER' AND read_at IS NULL;


-- ===========================================================================
-- Scenario 9: Administrative Auditing & Catalog Management
-- Source: backend/app/api/routes/admin.py
-- ===========================================================================

-- 9.1 Admin Creates or Modifies a Training Course
INSERT INTO course (
    course_name, description, difficulty, default_duration, default_break, is_active
) VALUES (
    'Kettlebell Foundations',
    'Master explosive hip hinge mechanics, kettlebell swings, and Turkish get-ups.',
    'BEGINNER', 60, 10, 1
);
SET @new_course_id = LAST_INSERT_ID();

-- 9.2 Record Audit Log for Compliance
INSERT INTO audit_log (
    user_id, action, entity_type, entity_id, detail, ip_address
) VALUES (
    @admin_user_id, 'COURSE_CREATED', 'course', @new_course_id,
    JSON_OBJECT('course_name', 'Kettlebell Foundations', 'difficulty', 'BEGINNER', 'duration', 60),
    '192.168.1.100'
);

-- 9.3 System Generates Monthly Coach KPI Snapshot
INSERT INTO coach_kpi_record (
    coach_id, kpi_year, kpi_month, total_hours, completed_sessions,
    avg_rating, retention_rate, target_hours, target_avg_rating,
    target_retention_rate, is_achieved
)
SELECT
    c.coach_id,
    YEAR(CURDATE()),
    MONTH(CURDATE()),
    COALESCE(SUM(b.duration_minutes) / 60.0, 0),
    COUNT(b.booking_id),
    COALESCE(AVG(rc.avg_rating), 5.00),
    85.00,
    kr.min_monthly_hours,
    kr.min_avg_rating,
    kr.min_retention_rate,
    CASE
        WHEN COALESCE(SUM(b.duration_minutes) / 60.0, 0) >= kr.min_monthly_hours
         AND COALESCE(AVG(rc.avg_rating), 5.00) >= kr.min_avg_rating
        THEN 1
        ELSE 0
    END
FROM coach c
JOIN kpi_rule kr ON kr.coach_level = c.coach_level
LEFT JOIN booking b ON b.coach_id = c.coach_id AND b.status = 'COMPLETED'
LEFT JOIN review_coach rc ON rc.booking_id = b.booking_id
WHERE c.coach_id = 1
GROUP BY c.coach_id, kr.min_monthly_hours, kr.min_avg_rating, kr.min_retention_rate;

-- ===========================================================================
-- End of DML Script
-- ===========================================================================
