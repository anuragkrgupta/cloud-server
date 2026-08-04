-- Reference schema for the `users` table.
-- Note: app/main.py calls Base.metadata.create_all() on startup, which
-- creates this automatically. This file is provided for reference and for
-- environments where you'd rather run migrations by hand.

CREATE DATABASE IF NOT EXISTS auth_app
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE auth_app;

CREATE TABLE IF NOT EXISTS users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50)  NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_username (username),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
