import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# We'll use the user's DB to get a valid session and message ID
from app.database import SessionLocal
from app.models import User, FileRecord, FilePartRecord
from app.auth import decrypt_telegram_session
from app.config import settings

async def main():
    db = SessionLocal()
    file_record = db.query(FileRecord).first()
    if not file_record:
        print("No files found")
        return
        
    user = db.query(User).filter(User.id == file_record.user_id).first()
    session_string = decrypt_telegram_session(user.telegram_session)
    client = TelegramClient(StringSession(session_string), settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    try:
        part = file_record.parts[0]
        entity = await client.get_entity(int(user.channel_id))
        message = await client.get_messages(entity, ids=part.telegram_message_id)
        
        request_size = 512 * 1024
        
        async def fetch_chunk(offset):
            async for chunk in client.iter_download(message.media, offset=offset, limit=1, request_size=request_size):
                return chunk
            return b""
            
        print(f"File part size: {message.document.size}")
        
        # Fetch first 3 chunks concurrently
        tasks = []
        for offset in range(0, min(message.document.size, request_size * 3), request_size):
            tasks.append(fetch_chunk(offset))
            
        import time
        start = time.time()
        results = await asyncio.gather(*tasks)
        print(f"Time taken: {time.time() - start:.2f}s")
        for i, res in enumerate(results):
            print(f"Chunk {i} size: {len(res)}")
            
    finally:
        await client.disconnect()

asyncio.run(main())
