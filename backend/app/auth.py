"""
Security utilities: password hashing (bcrypt) and JWT authentication.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import base64
import hashlib

from fastapi import Depends, HTTPException, status, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_NAME = "access_token"


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# --------------------------------------------------------------------------
# Telegram Session Encryption
# --------------------------------------------------------------------------
def _get_fernet() -> Fernet:
    # Derive a valid 32-byte url-safe base64 key from our JWT_SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest())
    return Fernet(key)

def encrypt_telegram_session(session_string: str) -> str:
    if not session_string:
        return session_string
    # Fernet tokens start with gAAAAA, avoid double encryption
    if session_string.startswith("gAAAAA"):
        return session_string
    return _get_fernet().encrypt(session_string.encode()).decode()

def decrypt_telegram_session(encrypted_string: str) -> str:
    if not encrypted_string:
        return encrypted_string
    # Backward compatibility with unencrypted legacy sessions
    if not encrypted_string.startswith("gAAAAA"):
        return encrypted_string
    return _get_fernet().decrypt(encrypted_string.encode()).decode()


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises JWTError if invalid or expired."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# --------------------------------------------------------------------------
# Extracting the token from a request (cookie first, then Authorization header)
# --------------------------------------------------------------------------
def _extract_token(request: Request) -> Optional[str]:
    # Check query parameters (for direct file downloads to bypass ITP)
    token = request.query_params.get("token")
    if token:
        return token

    # Check cookies
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token

    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1]

    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    FastAPI dependency that protects a route. Raises 401 if the caller does
    not have a valid, unexpired JWT (via httpOnly cookie or Bearer header).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_token(request)
    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)
        email: Optional[str] = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    return user


def get_current_user_optional(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    """Same as get_current_user but returns None instead of raising - used to
    decide whether to redirect an already-logged-in user away from /login."""
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None
