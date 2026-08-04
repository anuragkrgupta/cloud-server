"""
Registration, login, and logout JSON API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    COOKIE_NAME,
    create_access_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import Message, Token, UserCreate, UserLogin, UserOut

router = APIRouter()

@router.post("/api/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(User)
        .filter(User.email == payload.email)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already registered.",
        )

    user = User(
        name=payload.name,
        email=payload.email,
        password=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        )
    db.refresh(user)
    return user


@router.post("/api/login", response_model=Token)
def login(payload: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password.",
    )

    if not user or not verify_password(payload.password, user.password):
        raise invalid_credentials

    access_token = create_access_token(data={"sub": user.email})

    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.IS_PRODUCTION,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    return Token(access_token=access_token)


@router.post("/api/logout", response_model=Message)
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return Message(message="Logged out.")

@router.get("/api/me", response_model=UserOut)
def get_me(request: Request, db: Session = Depends(get_db)):
    """Used by frontend to check if user is logged in."""
    from app.auth import get_current_user
    user = get_current_user(request, db)
    return user
