"""
Shared test fixtures and configuration.

Uses an in-memory SQLite database so tests never touch the real Supabase DB.
Overrides the FastAPI lifespan so the production startup/shutdown hooks are skipped.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, get_db
from app.config import settings

# Use SQLite in-memory database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Prevent the original app startup event from attempting to connect to MySQL
from contextlib import asynccontextmanager

@asynccontextmanager
async def test_lifespan(app_instance):
    yield

app.router.lifespan_context = test_lifespan


# ── Header helpers ──────────────────────────────────────────────────────
# The CSRF middleware requires X-Requested-With on all state-changing
# API requests.  These helpers keep every test DRY.

CSRF_HEADER = {"X-Requested-With": "XMLHttpRequest"}


def _merge_headers(*dicts):
    """Merge multiple header dicts, later ones overriding earlier ones."""
    merged = {}
    for d in dicts:
        if d:
            merged.update(d)
    return merged


@pytest.fixture(scope="function")
def client():
    # We clear the DB tables and recreate them per function to ensure total isolation
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        # Prevent cookie jar bleeding across tests
        c.cookies.clear()
        yield c

@pytest.fixture(scope="function")
def session():
    """Provides a fresh database session for a test, clearing data after."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        # Clean up tables after each function if isolation is needed
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        db.close()
