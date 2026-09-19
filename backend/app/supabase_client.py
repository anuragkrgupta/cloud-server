"""
Supabase client singleton.

Used for Supabase SDK operations (Auth, Storage, Realtime, PostgREST).
For raw SQL / ORM queries, continue using the SQLAlchemy session in database.py.

The client is created lazily on first use so that a missing env var does NOT
crash the app at import time — only routes that actually call get_supabase()
will fail if credentials are absent.
"""
import os
from functools import lru_cache
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return the Supabase client, creating it on the first call."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")

    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_KEY environment variables. "
            "Copy .env.example to .env and fill in the Supabase credentials."
        )

    return create_client(url, key)


# Convenience alias — still works for modules that do:
#   from app.supabase_client import supabase
# But now it's resolved lazily, not at import time.
class _LazyClient:
    """Proxy that forwards attribute access to the real client on demand."""
    def __getattr__(self, name):
        return getattr(get_supabase(), name)


supabase: Client = _LazyClient()  # type: ignore[assignment]
