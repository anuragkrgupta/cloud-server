import asyncio
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, FileRecord, FilePartRecord
from app.services.telegram_service import get_client_for_session, get_resolved_entity
from app.services.parallel_transfer import download_message_parallel, upload_stream_parallel
from app.config import settings
from telethon import utils

logger = logging.getLogger(__name__)

async def transfer_file_between_users(source_user_id: int, target_user_id: int, source_file_id: int, message_ids: list[int]):
    """
    Background task to stream a file from source user's Telegram channel to target user's Telegram channel.
    """
    db: Session = SessionLocal()
    try:
        source_user = db.query(User).filter(User.id == source_user_id).first()
        target_user = db.query(User).filter(User.id == target_user_id).first()
        source_file = db.query(FileRecord).filter(FileRecord.id == source_file_id).first()
        
        if not source_user or not target_user or not source_file:
            logger.error("Transfer failed: User or file not found in DB.")
            return

        if not source_user.is_telegram_connected or not target_user.is_telegram_connected:
            logger.error("Transfer failed: One of the users is not connected to Telegram.")
            return

        # 1. Setup Source Client
        source_client = await get_client_for_session(source_user.telegram_session)
        source_entity = await get_resolved_entity(source_client, source_user.channel_id)
        
        # 2. Setup Target Client
        target_client = await get_client_for_session(target_user.telegram_session)
        target_entity = await get_resolved_entity(target_client, target_user.channel_id)
        
        # Create a new FileRecord for target user immediately so they see it (with 0 size initially, or full size but maybe pending status? We'll just do it after transfer finishes to avoid complexity)
        
        # We will stream parts one by one.
        # However, upload_stream_parallel expects an async generator that yields chunks.
        # We can create an async generator that yields all chunks of all parts sequentially.
        
        async def combined_stream():
            for msg_id in message_ids:
                message = await source_client.get_messages(source_entity, ids=msg_id)
                if not message or not message.media:
                    raise Exception(f"Media not found in source message (ID: {msg_id})")
                
                async for chunk in download_message_parallel(
                    source_client,
                    message.media,
                    message.document.size,
                    workers=settings.WORKERS_PER_TRANSFER
                ):
                    yield chunk

        logger.info(f"Starting background transfer of file {source_file.original_name} from user {source_user_id} to {target_user_id}")
        
        # Do the upload to target
        sent_messages = await upload_stream_parallel(
            target_client,
            target_entity,
            combined_stream(),
            filename=source_file.original_name,
            total_size=source_file.file_size,
            mime_type=source_file.mime_type or "application/octet-stream",
            workers=settings.WORKERS_PER_TRANSFER,
            part_size_kb=settings.PART_SIZE_KB
        )
        
        if not sent_messages:
            raise Exception("Transfer uploaded 0 messages.")
            
        # Success! Now save to DB
        new_file = FileRecord(
            user_id=target_user.id,
            original_name=source_file.original_name,
            file_size=source_file.file_size,
            mime_type=source_file.mime_type,
            is_shared=False,
            share_token=None
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)
        
        for idx, msg in enumerate(sent_messages):
            part_record = FilePartRecord(
                file_id=new_file.id,
                part_index=idx,
                telegram_message_id=msg.id,
                channel_id=target_user.channel_id
            )
            db.add(part_record)
        
        db.commit()
        logger.info(f"Successfully transferred file {new_file.id} to user {target_user_id}")
        
    except Exception as e:
        logger.error(f"Transfer between users failed: {e}")
    finally:
        db.close()
