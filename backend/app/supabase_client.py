"""
Supabase client singleton.

Used for Supabase SDK operations (Auth, Storage, Realtime, PostgREST).
For raw SQL / ORM queries, continue using the SQLAlchemy session in database.py.
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_supabase_url: str = os.environ.get("SUPABASE_URL", "")
_supabase_key: str = os.environ.get("SUPABASE_KEY", "")

if not _supabase_url or not _supabase_key:
    raise RuntimeError(
        "Missing SUPABASE_URL or SUPABASE_KEY environment variables. "
        "Copy .env.example to .env and fill in the Supabase credentials."
    )

supabase: Client = create_client(_supabase_url, _supabase_key)
