-- FitBooking demo data for local/API testing.
-- Run schema.sql first. This script targets MySQL 8.0.16+.
--
-- Demo password for every seeded account: DemoPass123!
-- These accounts are for development only. Never use them in production.

SET NAMES utf8mb4;
SET time_zone = '+07:00';
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY';

USE fitbooking;

START TRANSACTION;

-- ---------------------------------------------------------------------------
-- Accounts
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
        'Mobility and wellness coach helping members move better every week.',
        'GYM', 10, 4, 'Yoga Alliance, Mobility Specialist',
        'https://images.unsplash.com/photo-1544367567-0f2fcb009e0b',
        'ACTIVE', '2022-08-15'
    )
ON DUPLICATE KEY UPDATE
    bio = VALUES(bio),
    service_mode = VALUES(service_mode),
    years_experience = VALUES(years_experience),
    certifications = VALUES(certifications),
    avatar_url = VALUES(avatar_url),
    status = 'ACTIVE';

SELECT coach_id INTO @tan_coach_id FROM coach WHERE coach_no = '1001';
SELECT coach_id INTO @may_coach_id FROM coach WHERE coach_no = '1002';

-- ---------------------------------------------------------------------------
-- Catalog
-- ---------------------------------------------------------------------------

INSERT INTO gym
    (gym_name, address, district, phone, facilities, opening_time, closing_time,
     latitude, longitude, is_active)
VALUES
    (
        'Nimman Fitness Club',
        'Nimman Soi 9, Suthep, Mueang Chiang Mai',
        'NIMMAN', '+6653001001', 'Free weights, cardio, showers, lockers',
        '06:00:00', '22:00:00', 18.796143, 98.967310, 1
    ),
    (
        'Old City Movement Lab',
        'Ratchadamnoen Road, Si Phum, Mueang Chiang Mai',
        'OLD_CITY', '+6653001002', 'Functional area, yoga studio, mobility tools',
        '06:30:00', '21:00:00', 18.795410, 98.978210, 1
    ),
    (
        'Central Strength House',
        'Superhighway Road, Fa Ham, Mueang Chiang Mai',
        'CENTRAL', '+6653001003', 'Strength floor, recovery room, parking',
        '06:00:00', '22:00:00', 18.814400, 98.995100, 1
    )
ON DUPLICATE KEY UPDATE
    address = VALUES(address),
    is_active = 1;

SELECT gym_id INTO @nimman_gym_id FROM gym WHERE gym_name = 'Nimman Fitness Club';
SELECT gym_id INTO @old_city_gym_id FROM gym WHERE gym_name = 'Old City Movement Lab';
SELECT gym_id INTO @central_gym_id FROM gym WHERE gym_name = 'Central Strength House';

INSERT INTO course
    (course_name, description, equipment, difficulty, default_duration, is_active)
VALUES
    (
        'Strength & Conditioning',
        'Build strength and improve performance with a practical one-to-one plan.',
        'Barbell, dumbbells, resistance bands',
        'INTERMEDIATE', 60, 1
    ),
    (
        'HIIT',
        'High-intensity intervals for efficient conditioning and calorie burn.',
        'Kettlebell, mat, timer',
        'BEGINNER', 50, 1
    ),
    (
        'Mobility & Flexibility',
        'Move freely and improve range of motion with guided mobility work.',
        'Mat, foam roller, bands',
        'BEGINNER', 60, 1
    ),
    (
        'Functional Fitness',
        'Train strength, balance, and conditioning for everyday movement.',
        'Dumbbells, cable machine, medicine ball',
        'ADVANCED', 60, 1
    )
ON DUPLICATE KEY UPDATE
    description = VALUES(description),
    equipment = VALUES(equipment),
    default_duration = VALUES(default_duration),
    is_active = 1;

SELECT course_id INTO @strength_course_id
FROM course WHERE course_name = 'Strength & Conditioning';
SELECT course_id INTO @hiit_course_id
FROM course WHERE course_name = 'HIIT';
SELECT course_id INTO @mobility_course_id
FROM course WHERE course_name = 'Mobility & Flexibility';
SELECT course_id INTO @functional_course_id
FROM course WHERE course_name = 'Functional Fitness';

INSERT INTO coach_course (coach_id, course_id, price_per_session, is_active)
VALUES
    (@tan_coach_id, @strength_course_id, 800.00, 1),
    (@tan_coach_id, @hiit_course_id, 750.00, 1),
    (@tan_coach_id, @functional_course_id, 900.00, 1),
    (@may_coach_id, @mobility_course_id, 750.00, 1),
    (@may_coach_id, @hiit_course_id, 700.00, 1)
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
-- Member packages
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
-- Bookings
-- ---------------------------------------------------------------------------

-- Completed booking: supports the review API and coach rating data.
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

-- Confirmed booking: supports the home dashboard and upcoming bookings UI.
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

-- Pending booking: useful for cancellation and checkout tests.
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
    (order_type, package_id, total_amount, discount, final_amount,
     payment_method, payment_status, payment_time)
SELECT 'PACKAGE', @alex_package_id, 8970.00, 0.00, 8970.00,
       'PROMPTPAY', 'PAID', '2026-09-01 10:00:00'
WHERE NOT EXISTS (
    SELECT 1 FROM orders WHERE package_id = @alex_package_id
);

-- ---------------------------------------------------------------------------
-- Fitness profile, reviews, KPI, and audit data
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
        JSON_OBJECT('source', 'sample_data.sql', 'purpose', 'API testing'),
        '127.0.0.1'
    );

COMMIT;

-- ---------------------------------------------------------------------------
-- Dynamic schedule table for coach 1001.
-- The application normally creates this table through the schedule endpoint.
-- This section makes schedule reads and booking tests work immediately.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `coach_schedule_1001` (
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
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO schedule_registry (coach_id, table_name, generated_until, status)
VALUES (@tan_coach_id, 'coach_schedule_1001', '2026-10-20', 'ACTIVE')
ON DUPLICATE KEY UPDATE
    table_name = VALUES(table_name),
    generated_until = VALUES(generated_until),
    status = 'ACTIVE';

-- Generate 10-minute slots from 08:00 to 18:00 for October 9–20, 2026.
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

-- Mark the seeded completed and confirmed sessions as occupied.
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

-- Verification queries.
SELECT username, role, status
FROM users
WHERE username IN ('alex.demo', 'maya.demo', 'tan.coach', 'may.coach', 'admin.demo')
ORDER BY role, username;

SELECT member_id, package_type, remaining_sessions, status
FROM member_package
WHERE member_id IN (@alex_member_id, @maya_member_id)
ORDER BY member_id, package_id;

SELECT booking_id, member_id, booking_date, start_time, status
FROM booking
WHERE booking_id IN (@completed_booking_id, @confirmed_booking_id, @pending_booking_id)
ORDER BY booking_date, start_time;
