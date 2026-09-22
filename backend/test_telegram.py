import sys
import logging
import asyncio
from telethon import TelegramClient
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_telegram():
    if not settings.TG_API_ID or not settings.TG_API_HASH:
        logger.error("TG_API_ID or TG_API_HASH is missing from .env")
        sys.exit(1)
        
    client = TelegramClient('test_session', settings.TG_API_ID, settings.TG_API_HASH)
    
    try:
        logger.info("Connecting to Telegram...")
        await client.connect()
        if client.is_connected():
            logger.info("Success! Connected to Telegram servers.")
        else:
            logger.error("Failed to connect.")
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_telegram())
