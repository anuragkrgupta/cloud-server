"""
Pydantic schemas for request validation and response serialization.
"""
import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not (3 <= len(v) <= 50):
            raise ValueError("Name must be between 3 and 50 characters")
        if not re.fullmatch(r"[A-Za-z0-9_]+", v):
            raise ValueError(
                "Name may only contain letters, numbers, and underscores"
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    is_telegram_connected: bool
    channel_id: str | None = None
    
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Message(BaseModel):
    message: str


class TelegramQRStartResponse(BaseModel):
    token: str
    url: str

class TelegramQRStatusResponse(BaseModel):
    status: str
    message: str | None = None


class Telegram2FARequest(BaseModel):
    token: str
    password: str
    force_new_channel: bool = False

class TelegramMismatchOverrideRequest(BaseModel):
    token: str


class FileOut(BaseModel):
    id: int
    original_name: str
    file_size: int
    uploaded_at: datetime
    is_shared: bool = False
    share_token: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
