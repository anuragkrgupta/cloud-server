-- Reference schema for the `users` table.
-- Note: app/main.py calls Base.metadata.create_all() on startup, which
-- creates this automatically. This file is provided for reference and for
-- environments where you'd rather run migrations by hand.

CREATE DATABASE IF NOT EXISTS auth_app
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE auth_app;

CREATE TABLE IF NOT EXISTS users (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(50)  NOT NULL,
    email            VARCHAR(255) NOT NULL UNIQUE,
    password         VARCHAR(255) NOT NULL,
    telegram_phone   VARCHAR(50),
    telegram_user_id VARCHAR(50),
    telegram_session VARCHAR(1000),
    channel_id       VARCHAR(50),
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_name (name),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
