-- Idempotent migration for member application persistence.
-- Run after schema.sql on an existing database.

CREATE TABLE IF NOT EXISTS package_catalog (
    package_type ENUM('5+1','10+3','20+7') NOT NULL,
    paid_sessions SMALLINT UNSIGNED NOT NULL,
    bonus_sessions SMALLINT UNSIGNED NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    validity_days SMALLINT UNSIGNED NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (package_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS member_payment_method (
    payment_method_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    member_id INT UNSIGNED NOT NULL,
    method_type ENUM('PROMPTPAY','CARD','CASH') NOT NULL,
    label VARCHAR(100) NOT NULL,
    provider_token VARCHAR(255) NULL,
    last_four CHAR(4) NULL,
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    status ENUM('ACTIVE','REMOVED') NOT NULL DEFAULT 'ACTIVE',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (payment_method_id),
    KEY idx_payment_method_member (member_id, status, is_default),
    CONSTRAINT fk_payment_method_member FOREIGN KEY (member_id)
        REFERENCES member (member_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS member_message (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    member_id INT UNSIGNED NOT NULL,
    coach_id INT UNSIGNED NOT NULL,
    sender_role ENUM('MEMBER','COACH') NOT NULL,
    message_text VARCHAR(2000) NOT NULL,
    read_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (message_id),
    KEY idx_member_message_thread (member_id, coach_id, created_at),
    CONSTRAINT fk_member_message_member FOREIGN KEY (member_id)
        REFERENCES member (member_id),
    CONSTRAINT fk_member_message_coach FOREIGN KEY (coach_id)
        REFERENCES coach (coach_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS member_body_measurement (
    measurement_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    member_id INT UNSIGNED NOT NULL,
    weight_kg DECIMAL(5,1) NOT NULL,
    body_fat_percent DECIMAL(5,2) NULL,
    measured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (measurement_id),
    KEY idx_body_measurement_member_date (member_id, measured_at),
    CONSTRAINT fk_body_measurement_member FOREIGN KEY (member_id)
        REFERENCES member (member_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
