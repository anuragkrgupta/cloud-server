import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

def test_supabase_connection():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found in .env")
        sys.exit(1)
        
    try:
        print(f"Connecting to {url}...")
        supabase: Client = create_client(url, key)
        
        # Test 1: Check auth (this shouldn't throw an error if connected)
        auth_health = supabase.auth.get_user("fake_token_just_to_check_network")
    except Exception as e:
        if "invalid" in str(e).lower() or "token" in str(e).lower() or "jwt" in str(e).lower():
            # This means network is fine, just auth failed which is expected
            pass
        else:
            print(f"Connection failed during Auth check: {e}")
            sys.exit(1)
            
    try:
        # Test 2: List buckets or query something simple
        response = supabase.storage.list_buckets()
        print(f"Success! Connected to Supabase. Found {len(response)} buckets.")
        for bucket in response:
            print(f" - Bucket: {bucket.name}")
    except Exception as e:
        print(f"Connection failed during Storage check: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_supabase_connection()
