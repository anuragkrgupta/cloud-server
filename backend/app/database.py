"""
SQLAlchemy engine, session factory, and declarative base for MySQL.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

import sqlalchemy

# Ensure the database exists before connecting to it
def _ensure_database_exists():
    pwd = f":{settings.DB_PASSWORD}" if settings.DB_PASSWORD else ""
    base_url = f"mysql+pymysql://{settings.DB_USER}{pwd}@{settings.DB_HOST}:{settings.DB_PORT}/"
    temp_engine = create_engine(base_url)
    with temp_engine.connect() as conn:
        conn.execute(sqlalchemy.text(f"CREATE DATABASE IF NOT EXISTS {settings.DB_NAME}"))
    # temp_engine.dispose()

# _ensure_database_exists()

# pool_pre_ping avoids "MySQL server has gone away" errors on idle connections
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
