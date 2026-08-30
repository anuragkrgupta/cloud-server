import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models import User, FileRecord, FilePartRecord
from app.services.telegram_service import get_client_for_session

async def run_recovery():
    print("Starting recovery script for orphaned channels...")
    db = SessionLocal()
    users = db.query(User).all()
    
    for user in users:
        if not user.telegram_session:
            continue
            
        print(f"\nChecking User ID: {user.id} (Name: {user.name})")
        print(f"Current channel_id in DB: {user.channel_id}")
        
        try:
            client = await get_client_for_session(user.telegram_session)
            
            # This populates the cache and gets dialogs
            dialogs = await client.get_dialogs()
            
            candidate_channels = []
            for d in dialogs:
                if d.is_channel:
                    # Deterministic naming or old "Personal Cloud Storage"
                    if d.title == f"CloudStorage_{user.telegram_user_id}" or d.title == "Personal Cloud Storage":
                        candidate_channels.append(d)
                        
            if not candidate_channels:
                print("  No candidate storage channels found.")
                await client.disconnect()
                continue
                
            print(f"  Found {len(candidate_channels)} candidate channels:")
            for c in candidate_channels:
                print(f"    - Title: {c.title}, ID: {c.id}")
                
            if len(candidate_channels) > 1:
                print("  Warning: Multiple channels found! One of these may contain orphaned files.")
                print("  To fix orphaned file parts, you can update the file_parts table with the correct channel ID.")
                
            await client.disconnect()
            
        except Exception as e:
            print(f"  Failed to process user {user.id}: {e}")
            
    db.close()
    print("\nRecovery script finished.")

if __name__ == "__main__":
    asyncio.run(run_recovery())
