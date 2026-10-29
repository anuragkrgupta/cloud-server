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
    Transfers each volume/part independently to respect Telegram's per-document 2GB limit.
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
        
        logger.info(f"Starting background transfer of file {source_file.original_name} from user {source_user_id} to {target_user_id}")
        
        from app.services.telegram_service import upload_stream_to_telegram

        # Transfer each volume/part independently so no single upload exceeds
        # Telegram's 2GB per-document limit (avoids FILE_PARTS_TOO_MUCH).
        new_message_ids = []
        for part_idx, msg_id in enumerate(message_ids):
            message = await source_client.get_messages(source_entity, ids=msg_id)
            if not message or not message.media:
                raise Exception(f"Media not found in source message (ID: {msg_id})")

            part_size = message.document.size

            async def part_stream(src_client, media, size):
                async for chunk in download_message_parallel(
                    src_client,
                    media,
                    size,
                    workers=settings.WORKERS_PER_TRANSFER
                ):
                    yield chunk

            target_msg_id = await upload_stream_to_telegram(
                target_user.telegram_session,
                target_user.channel_id,
                source_file.original_name,
                part_size,
                part_stream(source_client, message.media, part_size)
            )

            if not target_msg_id:
                raise Exception(f"Transfer failed for part {part_idx} (source msg {msg_id})")

            new_message_ids.append(target_msg_id)
            logger.info(f"Transferred part {part_idx + 1}/{len(message_ids)} -> target msg_id={target_msg_id}")

        # All parts transferred — save to DB
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
        
        for idx, target_msg_id in enumerate(new_message_ids):
            part_record = FilePartRecord(
                file_id=new_file.id,
                part_index=idx,
                telegram_message_id=target_msg_id,
                channel_id=target_user.channel_id
            )
            db.add(part_record)
        
        db.commit()
        logger.info(f"Successfully transferred file {new_file.id} ({len(new_message_ids)} parts) to user {target_user_id}")
        
    except Exception:
        db.rollback()
        logger.exception(
            "Background transfer failed: file=%s, source_user=%s, target_user=%s",
            source_file_id, source_user_id, target_user_id,
        )
    finally:
        db.close()

