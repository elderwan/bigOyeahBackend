-- FitBooking / Chiang Mai Personal Training Booking System
-- MySQL 8.0.16+
-- Purpose: initialize the 19 fixed tables, seed configuration data,
--          and create database-level integrity triggers.
--
-- Notes:
-- 1. Business time is stored in the Chiang Mai timezone (+07:00).
-- 2. Business data uses status-based soft deletion; do not physically delete it.
-- 3. Dynamic coach schedule tables are created by the backend application.
-- 4. Booking, payment, and package operations must run in application
--    transactions and lock schedule slots before packages, bookings, and orders.

SET NAMES utf8mb4;
SET time_zone = '+07:00';
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY';

CREATE DATABASE IF NOT EXISTS `fitbooking`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE `fitbooking`;

-- ============================================================
-- 1. Configuration tables
-- ============================================================

CREATE TABLE IF NOT EXISTS `membership_level` (
    `level_id`          TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `level_code`        VARCHAR(20) NOT NULL,
    `level_name`        VARCHAR(50) NOT NULL,
    `min_total_spend`   DECIMAL(12,2) NOT NULL,
    `discount_rate`     DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    `sort_order`        TINYINT UNSIGNED NOT NULL,
    PRIMARY KEY (`level_id`),
    UNIQUE KEY `uk_membership_level_code` (`level_code`),
    UNIQUE KEY `uk_membership_level_spend` (`min_total_spend`),
    UNIQUE KEY `uk_membership_level_sort` (`sort_order`),
    CONSTRAINT `chk_membership_level_spend`
        CHECK (`min_total_spend` >= 0),
    CONSTRAINT `chk_membership_level_discount`
        CHECK (`discount_rate` BETWEEN 0 AND 1)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Membership level and upgrade discount rules';

CREATE TABLE IF NOT EXISTS `kpi_rule` (
    `coach_level`          ENUM('BEGINNER','INTERMEDIATE','ADVANCED','MASTER') NOT NULL,
    `min_monthly_hours`    DECIMAL(6,2) NOT NULL,
    `min_avg_rating`       DECIMAL(3,2) NOT NULL,
    `min_retention_rate`   DECIMAL(5,2) NOT NULL,
    `updated_at`           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`coach_level`),
    CONSTRAINT `chk_kpi_rule_hours`
        CHECK (`min_monthly_hours` >= 0),
    CONSTRAINT `chk_kpi_rule_rating`
        CHECK (`min_avg_rating` BETWEEN 1 AND 5),
    CONSTRAINT `chk_kpi_rule_retention`
        CHECK (`min_retention_rate` BETWEEN 0 AND 100)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Monthly KPI thresholds by coach level';

-- ============================================================
-- 2. Accounts and profiles
-- ============================================================

CREATE TABLE IF NOT EXISTS `users` (
    `user_id`        INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `username`       VARCHAR(50) NOT NULL,
    `password_hash`  VARCHAR(255) NOT NULL,
    `display_name`   VARCHAR(100) NOT NULL,
    `email`          VARCHAR(100) NOT NULL,
    `phone`          VARCHAR(20) NOT NULL,
    `role`           ENUM('MEMBER','COACH','ADMIN') NOT NULL,
    `status`         ENUM('ACTIVE','DISABLED') NOT NULL DEFAULT 'ACTIVE',
    `last_login_at`  DATETIME NULL,
    `created_at`     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`),
    UNIQUE KEY `uk_users_username` (`username`),
    UNIQUE KEY `uk_users_email` (`email`),
    UNIQUE KEY `uk_users_phone` (`phone`),
    KEY `idx_users_role_status` (`role`, `status`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Unified user account';

CREATE TABLE IF NOT EXISTS `member` (
    `member_id`       INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `user_id`         INT UNSIGNED NOT NULL,
    `level_id`        TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `total_spend`     DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    `gender`          ENUM('MALE','FEMALE','OTHER') NULL,
    `birth_date`      DATE NULL,
    `height_cm`       DECIMAL(5,1) NULL,
    `weight_kg`       DECIMAL(5,1) NULL,
    `fitness_goal`    VARCHAR(200) NULL,
    `registered_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`member_id`),
    UNIQUE KEY `uk_member_user` (`user_id`),
    KEY `idx_member_level` (`level_id`),
    CONSTRAINT `fk_member_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_member_level`
        FOREIGN KEY (`level_id`) REFERENCES `membership_level` (`level_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_member_total_spend`
        CHECK (`total_spend` >= 0),
    CONSTRAINT `chk_member_height`
        CHECK (`height_cm` IS NULL OR `height_cm` > 0),
    CONSTRAINT `chk_member_weight`
        CHECK (`weight_kg` IS NULL OR `weight_kg` > 0)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Member profile';

CREATE TABLE IF NOT EXISTS `coach` (
    `coach_id`          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `coach_no`          VARCHAR(8) NOT NULL,
    `user_id`           INT UNSIGNED NOT NULL,
    `coach_level`       ENUM('BEGINNER','INTERMEDIATE','ADVANCED','MASTER')
                        NOT NULL DEFAULT 'BEGINNER',
    `bio`               TEXT NULL,
    `service_mode`      ENUM('GYM','HOME','BOTH') NOT NULL DEFAULT 'GYM',
    `break_interval`    TINYINT UNSIGNED NOT NULL DEFAULT 10,
    `years_experience`  TINYINT UNSIGNED NULL,
    `certifications`    VARCHAR(500) NULL,
    `avatar_url`        VARCHAR(255) NULL,
    `status`            ENUM('ACTIVE','ON_LEAVE','RESIGNED')
                        NOT NULL DEFAULT 'ACTIVE',
    `hired_at`          DATE NULL,
    `created_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`coach_id`),
    UNIQUE KEY `uk_coach_no` (`coach_no`),
    UNIQUE KEY `uk_coach_user` (`user_id`),
    KEY `idx_coach_status_level` (`status`, `coach_level`),
    CONSTRAINT `fk_coach_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_coach_no`
        CHECK (`coach_no` REGEXP '^[0-9]{4,8}$'),
    CONSTRAINT `chk_coach_break_interval`
        CHECK (`break_interval` IN (10,20,30))
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Coach profile';

-- ============================================================
-- 3. Gyms and courses
-- ============================================================

CREATE TABLE IF NOT EXISTS `gym` (
    `gym_id`          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `gym_name`        VARCHAR(100) NOT NULL,
    `address`         VARCHAR(255) NOT NULL,
    `district`        ENUM('NIMMAN','OLD_CITY','CENTRAL','MAE_RIM','HANG_DONG')
                      NOT NULL,
    `phone`           VARCHAR(20) NULL,
    `facilities`      VARCHAR(500) NULL,
    `opening_time`    TIME NOT NULL DEFAULT '06:00:00',
    `closing_time`    TIME NOT NULL DEFAULT '22:00:00',
    `latitude`        DECIMAL(9,6) NULL,
    `longitude`       DECIMAL(9,6) NULL,
    `is_active`       TINYINT(1) NOT NULL DEFAULT 1,
    `created_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`gym_id`),
    KEY `idx_gym_district` (`district`, `is_active`),
    CONSTRAINT `chk_gym_hours`
        CHECK (`closing_time` > `opening_time`),
    CONSTRAINT `chk_gym_active`
        CHECK (`is_active` IN (0,1))
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Fitness gym';

CREATE TABLE IF NOT EXISTS `course` (
    `course_id`          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `course_name`        VARCHAR(100) NOT NULL,
    `description`        TEXT NULL,
    `equipment`          VARCHAR(255) NULL,
    `difficulty`         ENUM('BEGINNER','INTERMEDIATE','ADVANCED') NOT NULL,
    `default_duration`   SMALLINT UNSIGNED NOT NULL DEFAULT 60,
    `is_active`          TINYINT(1) NOT NULL DEFAULT 1,
    `created_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`course_id`),
    UNIQUE KEY `uk_course_name` (`course_name`),
    CONSTRAINT `chk_course_duration`
        CHECK (`default_duration` > 0 AND `default_duration` % 10 = 0),
    CONSTRAINT `chk_course_active`
        CHECK (`is_active` IN (0,1))
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Training course';

-- ============================================================
-- 4. Coach capabilities and schedule registry
-- ============================================================

CREATE TABLE IF NOT EXISTS `coach_service` (
    `coach_service_id`  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `coach_id`          INT UNSIGNED NOT NULL,
    `gym_id`            INT UNSIGNED NOT NULL,
    `is_home_service`   TINYINT(1) NOT NULL DEFAULT 0,
    `service_area`      ENUM('NIMMAN','OLD_CITY','CENTRAL','MAE_RIM','HANG_DONG')
                        NULL,
    `is_active`         TINYINT(1) NOT NULL DEFAULT 1,
    `created_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`coach_service_id`),
    UNIQUE KEY `uk_coach_gym` (`coach_id`, `gym_id`),
    KEY `idx_coach_service_area` (`service_area`, `is_active`),
    CONSTRAINT `fk_coach_service_coach`
        FOREIGN KEY (`coach_id`) REFERENCES `coach` (`coach_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_coach_service_gym`
        FOREIGN KEY (`gym_id`) REFERENCES `gym` (`gym_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_coach_service_home`
        CHECK (`is_home_service` IN (0,1)),
    CONSTRAINT `chk_coach_service_area`
        CHECK (`is_home_service` = 0 OR `service_area` IS NOT NULL)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Coach gym assignment and home service area';

CREATE TABLE IF NOT EXISTS `coach_course` (
    `coach_id`           INT UNSIGNED NOT NULL,
    `course_id`          INT UNSIGNED NOT NULL,
    `price_per_session`  DECIMAL(10,2) NOT NULL,
    `is_active`          TINYINT(1) NOT NULL DEFAULT 1,
    `created_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`coach_id`, `course_id`),
    KEY `idx_coach_course_course` (`course_id`),
    CONSTRAINT `fk_coach_course_coach`
        FOREIGN KEY (`coach_id`) REFERENCES `coach` (`coach_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_coach_course_course`
        FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_coach_course_price`
        CHECK (`price_per_session` >= 0),
    CONSTRAINT `chk_coach_course_active`
        CHECK (`is_active` IN (0,1))
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Coach and course assignment';

CREATE TABLE IF NOT EXISTS `coach_weekly_template` (
    `template_id`  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `coach_id`     INT UNSIGNED NOT NULL,
    `weekday`      TINYINT UNSIGNED NOT NULL,
    `start_time`   TIME NOT NULL,
    `end_time`     TIME NOT NULL,
    `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`template_id`),
    UNIQUE KEY `uk_coach_weekly_template`
        (`coach_id`, `weekday`, `start_time`),
    CONSTRAINT `fk_coach_weekly_template_coach`
        FOREIGN KEY (`coach_id`) REFERENCES `coach` (`coach_id`)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT `chk_coach_weekly_template_weekday`
        CHECK (`weekday` BETWEEN 1 AND 7),
    CONSTRAINT `chk_coach_weekly_template_range`
        CHECK (`end_time` > `start_time`),
    CONSTRAINT `chk_coach_weekly_template_grid`
        CHECK (
            MINUTE(`start_time`) % 10 = 0
            AND MINUTE(`end_time`) % 10 = 0
            AND SECOND(`start_time`) = 0
            AND SECOND(`end_time`) = 0
        )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Coach weekly availability template';

CREATE TABLE IF NOT EXISTS `schedule_registry` (
    `schedule_id`     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `coach_id`        INT UNSIGNED NOT NULL,
    `table_name`      VARCHAR(64) NOT NULL,
    `generated_until` DATE NULL,
    `status`          ENUM('ACTIVE','ARCHIVED') NOT NULL DEFAULT 'ACTIVE',
    `created_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`schedule_id`),
    UNIQUE KEY `uk_schedule_registry_coach` (`coach_id`),
    UNIQUE KEY `uk_schedule_registry_table` (`table_name`),
    CONSTRAINT `fk_schedule_registry_coach`
        FOREIGN KEY (`coach_id`) REFERENCES `coach` (`coach_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_schedule_registry_table`
        CHECK (`table_name` REGEXP '^coach_schedule_[0-9]{4,8}$')
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Coach and dynamic schedule table registry';

-- ============================================================
-- 5. Transaction tables
-- ============================================================

CREATE TABLE IF NOT EXISTS `member_package` (
    `package_id`          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `member_id`           INT UNSIGNED NOT NULL,
    `package_type`        ENUM('5+1','10+3','20+7') NOT NULL,
    `total_sessions`      SMALLINT UNSIGNED NOT NULL,
    `remaining_sessions`  SMALLINT UNSIGNED NOT NULL,
    `price`               DECIMAL(10,2) NOT NULL,
    `purchase_date`       DATE NOT NULL,
    `expire_date`         DATE NOT NULL,
    `status`              ENUM('ACTIVE','EXHAUSTED','EXPIRED','CANCELLED')
                          NOT NULL DEFAULT 'ACTIVE',
    `created_at`          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`package_id`),
    UNIQUE KEY `uk_package_member` (`package_id`, `member_id`),
    KEY `idx_package_member_status`
        (`member_id`, `status`, `expire_date`),
    CONSTRAINT `fk_member_package_member`
        FOREIGN KEY (`member_id`) REFERENCES `member` (`member_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_member_package_sessions`
        CHECK (
            `total_sessions` > 0
            AND `remaining_sessions` <= `total_sessions`
        ),
    CONSTRAINT `chk_member_package_price`
        CHECK (`price` >= 0),
    CONSTRAINT `chk_member_package_dates`
        CHECK (`expire_date` >= `purchase_date`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Member session package';

CREATE TABLE IF NOT EXISTS `package_catalog` (
    `package_type`     ENUM('5+1','10+3','20+7') NOT NULL,
    `paid_sessions`    SMALLINT UNSIGNED NOT NULL,
    `bonus_sessions`   SMALLINT UNSIGNED NOT NULL,
    `price`            DECIMAL(10,2) NOT NULL,
    `validity_days`    SMALLINT UNSIGNED NOT NULL,
    `is_active`        TINYINT(1) NOT NULL DEFAULT 1,
    `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`package_type`),
    CONSTRAINT `chk_package_catalog_sessions`
        CHECK (`paid_sessions` > 0 AND `bonus_sessions` >= 0),
    CONSTRAINT `chk_package_catalog_price`
        CHECK (`price` >= 0),
    CONSTRAINT `chk_package_catalog_validity`
        CHECK (`validity_days` > 0)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Active package offers';

CREATE TABLE IF NOT EXISTS `booking` (
    `booking_id`       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `member_id`        INT UNSIGNED NOT NULL,
    `coach_id`         INT UNSIGNED NOT NULL,
    `course_id`        INT UNSIGNED NOT NULL,
    `gym_id`           INT UNSIGNED NULL,
    `package_id`       INT UNSIGNED NULL,
    `booking_date`     DATE NOT NULL,
    `start_time`       TIME NOT NULL,
    `end_time`         TIME NOT NULL,
    `duration_minutes` SMALLINT UNSIGNED NOT NULL,
    `break_minutes`    TINYINT UNSIGNED NOT NULL,
    `service_mode`     ENUM('GYM','HOME') NOT NULL,
    `service_district` ENUM('NIMMAN','OLD_CITY','CENTRAL','MAE_RIM','HANG_DONG')
                       NULL,
    `service_address`  VARCHAR(255) NULL,
    `price`            DECIMAL(10,2) NOT NULL,
    `status`           ENUM('PENDING','CONFIRMED','CANCELLED','COMPLETED','NO_SHOW')
                       NOT NULL DEFAULT 'PENDING',
    `expires_at`       DATETIME NULL,
    `cancelled_by`     ENUM('MEMBER','COACH','ADMIN','SYSTEM') NULL,
    `cancel_reason`    VARCHAR(255) NULL,
    `cancelled_at`     DATETIME NULL,
    `completed_at`     DATETIME NULL,
    `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`booking_id`),
    UNIQUE KEY `uk_booking_member` (`booking_id`, `member_id`),
    UNIQUE KEY `uk_booking_coach_member`
        (`booking_id`, `coach_id`, `member_id`),
    KEY `idx_booking_coach_date`
        (`coach_id`, `booking_date`, `start_time`),
    KEY `idx_booking_member_date`
        (`member_id`, `booking_date`),
    KEY `idx_booking_status_exp`
        (`status`, `expires_at`),
    KEY `idx_booking_gym_date`
        (`gym_id`, `booking_date`),
    CONSTRAINT `fk_booking_member`
        FOREIGN KEY (`member_id`) REFERENCES `member` (`member_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_booking_coach_course`
        FOREIGN KEY (`coach_id`, `course_id`)
        REFERENCES `coach_course` (`coach_id`, `course_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_booking_coach_gym`
        FOREIGN KEY (`coach_id`, `gym_id`)
        REFERENCES `coach_service` (`coach_id`, `gym_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_booking_package_member`
        FOREIGN KEY (`package_id`, `member_id`)
        REFERENCES `member_package` (`package_id`, `member_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_booking_start_grid`
        CHECK (
            MINUTE(`start_time`) % 10 = 0
            AND SECOND(`start_time`) = 0
        ),
    CONSTRAINT `chk_booking_time_range`
        CHECK (
            `end_time` > `start_time`
            AND `duration_minutes` > 0
            AND `duration_minutes` % 10 = 0
        ),
    CONSTRAINT `chk_booking_break`
        CHECK (`break_minutes` IN (10,20,30)),
    CONSTRAINT `chk_booking_price`
        CHECK (`price` >= 0),
    CONSTRAINT `chk_booking_service`
        CHECK (
            (`service_mode` = 'GYM'
                AND `gym_id` IS NOT NULL
                AND `service_district` IS NULL
                AND `service_address` IS NULL)
            OR
            (`service_mode` = 'HOME'
                AND `gym_id` IS NULL
                AND `service_district` IS NOT NULL
                AND `service_address` IS NOT NULL)
        ),
    CONSTRAINT `chk_booking_cancelled`
        CHECK (
            (`status` = 'CANCELLED' AND `cancelled_at` IS NOT NULL)
            OR (`status` <> 'CANCELLED')
        )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Member booking record';

CREATE TABLE IF NOT EXISTS `orders` (
    `order_id`        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `order_type`      ENUM('BOOKING','PACKAGE') NOT NULL,
    `booking_id`      BIGINT UNSIGNED NULL,
    `package_id`      INT UNSIGNED NULL,
    `total_amount`    DECIMAL(10,2) NOT NULL,
    `discount`        DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    `final_amount`    DECIMAL(10,2) NOT NULL,
    `payment_method`  ENUM('PROMPTPAY','CARD','CASH','PACKAGE_CREDIT') NULL,
    `payment_status`  ENUM('UNPAID','PAID','CANCELLED','REFUNDED')
                      NOT NULL DEFAULT 'UNPAID',
    `payment_time`    DATETIME NULL,
    `refunded_at`     DATETIME NULL,
    `created_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`order_id`),
    UNIQUE KEY `uk_orders_booking` (`booking_id`),
    UNIQUE KEY `uk_orders_package` (`package_id`),
    KEY `idx_orders_status` (`payment_status`, `created_at`),
    CONSTRAINT `fk_orders_booking`
        FOREIGN KEY (`booking_id`) REFERENCES `booking` (`booking_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_orders_package`
        FOREIGN KEY (`package_id`) REFERENCES `member_package` (`package_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_orders_amount`
        CHECK (
            `total_amount` >= 0
            AND `discount` >= 0
            AND `final_amount` >= 0
            AND `final_amount` = `total_amount` - `discount`
        ),
    CONSTRAINT `chk_orders_target`
        CHECK (
            (`order_type` = 'BOOKING'
                AND `booking_id` IS NOT NULL
                AND `package_id` IS NULL)
            OR
            (`order_type` = 'PACKAGE'
                AND `package_id` IS NOT NULL
                AND `booking_id` IS NULL)
        ),
    CONSTRAINT `chk_orders_paid_time`
        CHECK (
            `payment_status` NOT IN ('PAID','REFUNDED')
            OR `payment_time` IS NOT NULL
        ),
    CONSTRAINT `chk_orders_refund_time`
        CHECK (
            `payment_status` <> 'REFUNDED'
            OR `refunded_at` IS NOT NULL
        )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Booking and package purchase order';

CREATE TABLE IF NOT EXISTS `member_payment_method` (
    `payment_method_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `member_id`        INT UNSIGNED NOT NULL,
    `method_type`      ENUM('PROMPTPAY','CARD','CASH') NOT NULL,
    `label`            VARCHAR(100) NOT NULL,
    `provider_token`   VARCHAR(255) NULL,
    `last_four`        CHAR(4) NULL,
    `is_default`       TINYINT(1) NOT NULL DEFAULT 0,
    `status`            ENUM('ACTIVE','REMOVED') NOT NULL DEFAULT 'ACTIVE',
    `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`payment_method_id`),
    KEY `idx_payment_method_member` (`member_id`, `status`, `is_default`),
    CONSTRAINT `fk_payment_method_member`
        FOREIGN KEY (`member_id`) REFERENCES `member` (`member_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_payment_method_default`
        CHECK (`is_default` IN (0,1))
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Member tokenized payment methods';

CREATE TABLE IF NOT EXISTS `member_message` (
    `message_id`      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `member_id`       INT UNSIGNED NOT NULL,
    `coach_id`        INT UNSIGNED NOT NULL,
    `sender_role`     ENUM('MEMBER','COACH') NOT NULL,
    `message_text`    VARCHAR(2000) NOT NULL,
    `read_at`         DATETIME NULL,
    `created_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`message_id`),
    KEY `idx_member_message_thread` (`member_id`, `coach_id`, `created_at`),
    CONSTRAINT `fk_member_message_member`
        FOREIGN KEY (`member_id`) REFERENCES `member` (`member_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_member_message_coach`
        FOREIGN KEY (`coach_id`) REFERENCES `coach` (`coach_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_member_message_text`
        CHECK (CHAR_LENGTH(`message_text`) BETWEEN 1 AND 2000)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Persistent member-coach messages';

-- ============================================================
-- 6. Reviews, profiles, KPI records, and audit logs
-- ============================================================

CREATE TABLE IF NOT EXISTS `review_coach` (
    `review_coach_id`       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `booking_id`            BIGINT UNSIGNED NOT NULL,
    `reviewer_id`           INT UNSIGNED NOT NULL,
    `rating_professional`   TINYINT UNSIGNED NOT NULL,
    `rating_communication`  TINYINT UNSIGNED NOT NULL,
    `rating_punctuality`    TINYINT UNSIGNED NOT NULL,
    `rating_effectiveness`  TINYINT UNSIGNED NOT NULL,
    `avg_rating` DECIMAL(3,2)
        GENERATED ALWAYS AS (
            (`rating_professional`
             + `rating_communication`
             + `rating_punctuality`
             + `rating_effectiveness`) / 4
        ) STORED,
    `comment`               VARCHAR(1000) NULL,
    `created_at`            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`review_coach_id`),
    UNIQUE KEY `uk_review_coach_booking` (`booking_id`),
    CONSTRAINT `fk_review_coach_booking_member`
        FOREIGN KEY (`booking_id`, `reviewer_id`)
        REFERENCES `booking` (`booking_id`, `member_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_review_coach_professional`
        CHECK (`rating_professional` BETWEEN 1 AND 5),
    CONSTRAINT `chk_review_coach_communication`
        CHECK (`rating_communication` BETWEEN 1 AND 5),
    CONSTRAINT `chk_review_coach_punctuality`
        CHECK (`rating_punctuality` BETWEEN 1 AND 5),
    CONSTRAINT `chk_review_coach_effectiveness`
        CHECK (`rating_effectiveness` BETWEEN 1 AND 5)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Member review of a coach';

CREATE TABLE IF NOT EXISTS `review_member` (
    `review_member_id`  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `booking_id`        BIGINT UNSIGNED NOT NULL,
    `coach_id`          INT UNSIGNED NOT NULL,
    `member_id`         INT UNSIGNED NOT NULL,
    `completion_score`  TINYINT UNSIGNED NOT NULL,
    `proficiency_score` TINYINT UNSIGNED NOT NULL,
    `training_area`     ENUM('UPPER_BODY','CORE','LOWER_BODY','BACK','SHOULDER',
                             'FULL_BODY') NOT NULL,
    `training_type`     ENUM('STRENGTH','CARDIO','FLEXIBILITY','BALANCE','POWER')
                        NOT NULL,
    `coach_note`        VARCHAR(1000) NULL,
    `created_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`review_member_id`),
    UNIQUE KEY `uk_review_member_booking` (`booking_id`),
    KEY `idx_review_member_area` (`member_id`, `training_area`),
    CONSTRAINT `fk_review_member_booking_identity`
        FOREIGN KEY (`booking_id`, `coach_id`, `member_id`)
        REFERENCES `booking` (`booking_id`, `coach_id`, `member_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_review_member_completion`
        CHECK (`completion_score` BETWEEN 1 AND 5),
    CONSTRAINT `chk_review_member_proficiency`
        CHECK (`proficiency_score` BETWEEN 1 AND 5)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Coach review of a member';

CREATE TABLE IF NOT EXISTS `fitness_profile` (
    `profile_id`       INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `member_id`        INT UNSIGNED NOT NULL,
    `strongest_area`   ENUM('UPPER_BODY','CORE','LOWER_BODY','BACK','SHOULDER',
                            'FULL_BODY') NULL,
    `weakest_area`     ENUM('UPPER_BODY','CORE','LOWER_BODY','BACK','SHOULDER',
                            'FULL_BODY') NULL,
    `strongest_score`  DECIMAL(3,2) NULL,
    `weakest_score`    DECIMAL(3,2) NULL,
    `review_count`     INT UNSIGNED NOT NULL DEFAULT 0,
    `updated_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`profile_id`),
    UNIQUE KEY `uk_fitness_profile_member` (`member_id`),
    CONSTRAINT `fk_fitness_profile_member`
        FOREIGN KEY (`member_id`) REFERENCES `member` (`member_id`)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT `chk_fitness_profile_strongest_score`
        CHECK (`strongest_score` IS NULL OR `strongest_score` BETWEEN 1 AND 5),
    CONSTRAINT `chk_fitness_profile_weakest_score`
        CHECK (`weakest_score` IS NULL OR `weakest_score` BETWEEN 1 AND 5)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Cached member fitness profile';

CREATE TABLE IF NOT EXISTS `member_body_measurement` (
    `measurement_id`   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `member_id`        INT UNSIGNED NOT NULL,
    `weight_kg`        DECIMAL(5,1) NOT NULL,
    `body_fat_percent` DECIMAL(5,2) NULL,
    `measured_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`measurement_id`),
    KEY `idx_body_measurement_member_date` (`member_id`, `measured_at`),
    CONSTRAINT `fk_body_measurement_member`
        FOREIGN KEY (`member_id`) REFERENCES `member` (`member_id`)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT `chk_body_measurement_weight`
        CHECK (`weight_kg` > 0),
    CONSTRAINT `chk_body_measurement_fat`
        CHECK (`body_fat_percent` IS NULL OR `body_fat_percent` BETWEEN 0 AND 100)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Historical member body measurements';

CREATE TABLE IF NOT EXISTS `coach_kpi_record` (
    `kpi_record_id`        INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `coach_id`              INT UNSIGNED NOT NULL,
    `kpi_year`              SMALLINT UNSIGNED NOT NULL,
    `kpi_month`             TINYINT UNSIGNED NOT NULL,
    `total_hours`           DECIMAL(6,2) NOT NULL DEFAULT 0.00,
    `completed_sessions`    INT UNSIGNED NOT NULL DEFAULT 0,
    `avg_rating`            DECIMAL(3,2) NULL,
    `retention_rate`        DECIMAL(5,2) NULL,
    `target_hours`          DECIMAL(6,2) NOT NULL,
    `target_avg_rating`     DECIMAL(3,2) NOT NULL,
    `target_retention_rate` DECIMAL(5,2) NOT NULL,
    `is_achieved`           TINYINT(1) NOT NULL DEFAULT 0,
    `calculated_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`kpi_record_id`),
    UNIQUE KEY `uk_kpi_coach_month` (`coach_id`, `kpi_year`, `kpi_month`),
    CONSTRAINT `fk_coach_kpi_record_coach`
        FOREIGN KEY (`coach_id`) REFERENCES `coach` (`coach_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `chk_kpi_record_month`
        CHECK (`kpi_month` BETWEEN 1 AND 12),
    CONSTRAINT `chk_kpi_record_values`
        CHECK (
            `total_hours` >= 0
            AND `target_hours` >= 0
            AND `target_avg_rating` BETWEEN 1 AND 5
            AND `target_retention_rate` BETWEEN 0 AND 100
            AND (`avg_rating` IS NULL OR `avg_rating` BETWEEN 1 AND 5)
            AND (`retention_rate` IS NULL OR `retention_rate` BETWEEN 0 AND 100)
        )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Monthly coach KPI snapshot';

CREATE TABLE IF NOT EXISTS `audit_log` (
    `log_id`       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `user_id`      INT UNSIGNED NULL,
    `action`       VARCHAR(50) NOT NULL,
    `entity_type`  VARCHAR(50) NULL,
    `entity_id`    BIGINT UNSIGNED NULL,
    `detail`       JSON NULL,
    `ip_address`   VARCHAR(45) NULL,
    `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`log_id`),
    KEY `idx_audit_log_entity` (`entity_type`, `entity_id`),
    KEY `idx_audit_log_user_time` (`user_id`, `created_at`),
    KEY `idx_audit_log_time` (`created_at`),
    CONSTRAINT `fk_audit_log_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
        ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='System audit log';

-- ============================================================
-- 7. Initial configuration data
-- ============================================================

INSERT INTO `membership_level`
    (`level_id`, `level_code`, `level_name`, `min_total_spend`,
     `discount_rate`, `sort_order`)
VALUES
    (1, 'BRONZE', 'Bronze', 0.00, 0.000, 1),
    (2, 'SILVER', 'Silver', 5000.00, 0.050, 2),
    (3, 'GOLD',   'Gold',   20000.00, 0.100, 3)
ON DUPLICATE KEY UPDATE
    `level_code` = VALUES(`level_code`),
    `level_name` = VALUES(`level_name`),
    `min_total_spend` = VALUES(`min_total_spend`),
    `discount_rate` = VALUES(`discount_rate`),
    `sort_order` = VALUES(`sort_order`);

INSERT INTO `kpi_rule`
    (`coach_level`, `min_monthly_hours`, `min_avg_rating`, `min_retention_rate`)
VALUES
    ('BEGINNER',     40.00, 4.00, 30.00),
    ('INTERMEDIATE', 60.00, 4.20, 40.00),
    ('ADVANCED',     80.00, 4.40, 50.00),
    ('MASTER',      100.00, 4.60, 60.00)
ON DUPLICATE KEY UPDATE
    `min_monthly_hours` = VALUES(`min_monthly_hours`),
    `min_avg_rating` = VALUES(`min_avg_rating`),
    `min_retention_rate` = VALUES(`min_retention_rate`);

-- ============================================================
-- 8. Cross-table integrity triggers
-- ============================================================
-- Trigger definitions are stored in triggers.sql.
-- They use compound statements and must be executed by a client
-- that supports a custom delimiter, such as the MySQL command-line client.

-- ============================================================
-- 9. Dynamic coach schedule tables are created by backend code.
-- The fixed schema stores only the schedule_registry metadata table.

-- 10. Post-initialization verification
-- ============================================================

SELECT TABLE_NAME, TABLE_ROWS
  FROM information_schema.TABLES
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_TYPE = 'BASE TABLE'
 ORDER BY TABLE_NAME;
