"""
Centralized application configuration.

All values are read from environment variables (loaded from a .env file in
development). Never commit a real .env file - only .env.example is tracked.
"""
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


def _require(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill in real values."
        )
    return value


class Settings:
    # Database configuration
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "cloud_db")
    _DATABASE_URL: str | None = os.getenv("DATABASE_URL")

    @property
    def DATABASE_URL(self) -> str:
        # If full DATABASE_URL is provided (e.g., in cloud environments like Render), use it
        if self._DATABASE_URL:
            url = self._DATABASE_URL
            # Normalize postgres:// to postgresql:// for SQLAlchemy 1.4+
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url

        user = quote_plus(self.DB_USER)
        pwd = f":{quote_plus(self.DB_PASSWORD)}" if self.DB_PASSWORD else ""
        return (
            f"postgresql://{user}{pwd}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # CORS Settings
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "")

    # JWT
    JWT_SECRET_KEY: str = _require("JWT_SECRET_KEY", "dev-only-insecure-secret-change-me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "259200"))

    # Supabase SDK
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # Telegram
    TG_API_ID: int = int(os.getenv("TG_API_ID", "0"))
    TG_API_HASH: str = os.getenv("TG_API_HASH", "")
    WORKERS_PER_TRANSFER: int = int(os.getenv("WORKERS_PER_TRANSFER", "1"))

    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


settings = Settings()
