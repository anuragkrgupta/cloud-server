
"""
SQLAlchemy engine, session factory, and declarative base for PostgreSQL.
"""
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)


def _build_engine():
    """Configure PostgreSQL connections for local or hosted environments."""
    url = make_url(settings.DATABASE_URL)
    host = (url.host or "").lower()

    is_supabase = (
        host.endswith(".supabase.co")
        or host.endswith(".pooler.supabase.com")
    )

    if is_supabase and "sslmode" not in url.query:
        url = url.update_query_dict({"sslmode": "require"})

    options = {
        "pool_pre_ping": True,
        "connect_args": {"connect_timeout": 10},
    }

    # Avoid retaining pooled connections when using Supabase's pooler.
    if host.endswith(".pooler.supabase.com"):
        options["poolclass"] = NullPool
    else:
        options["pool_recycle"] = 1800

    return create_engine(url, **options)


engine = _build_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def check_database_connection():
    """Verify the database is reachable and report failures clearly."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        logger.info("PostgreSQL connection established successfully.")

    except Exception:
        logger.exception(
            "PostgreSQL connection failed. Check DATABASE_URL, "
            "database credentials, host, port, SSL configuration, "
            "and network access."
        )
        raise


def get_db():
    """Yield a database session and always close it."""
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()