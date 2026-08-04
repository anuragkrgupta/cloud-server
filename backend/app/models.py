"""
Database schema (SQLAlchemy ORM models).
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    telegram_phone = Column(String(50), nullable=True)
    telegram_user_id = Column(String(50), nullable=True)
    telegram_session = Column(String(1000), nullable=True)
    channel_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} name={self.name!r}>"

    @property
    def is_telegram_connected(self) -> bool:
        return bool(self.telegram_session)

class FileRecord(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    original_name = Column(String(255), nullable=False)
    telegram_file_id = Column(String(255), nullable=True)
    telegram_message_id = Column(Integer, nullable=False)
    file_size = Column(Integer, nullable=False)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    mime_type = Column(String(100), nullable=True) # Kept for internal logic

    def __repr__(self) -> str:
        return f"<FileRecord id={self.id} original_name={self.original_name!r}>"
