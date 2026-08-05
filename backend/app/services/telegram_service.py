import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest
from app.config import settings

logger = logging.getLogger(__name__)

import asyncio
import uuid

pending_logins = {}

async def start_qr_login() -> tuple[str, str]:
    """
    Initiates a Telegram connection and starts QR login.
    Returns (token_id, qr_url)
    """
    token_id = str(uuid.uuid4())
    session = StringSession()
    client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    
    qr_login_obj = await client.qr_login()
    
    async def wait_for_login(tid, cli, qr):
        try:
            # This blocks until the user scans and approves the QR code, or it times out
            user = await qr.wait()
            
            # Create a private channel for Cloud Storage
            channel_id = ""
            try:
                result = await cli(CreateChannelRequest(
                    title="Personal Cloud Storage",
                    about="Storage channel managed by Cloud Server Web App",
                    megagroup=False
                ))
                channel = result.chats[0]
                channel_id = str(channel.id)
            except Exception as e:
                logger.error(f"Failed to create storage channel: {e}")
                
            session_string = cli.session.save()
            tg_user_id = str(user.id)
            
            pending_logins[tid]["status"] = "success"
            pending_logins[tid]["session_string"] = session_string
            pending_logins[tid]["channel_id"] = channel_id
            pending_logins[tid]["tg_user_id"] = tg_user_id
            
        except Exception as e:
            logger.error(f"QR Login failed for {tid}: {e}")
            pending_logins[tid]["status"] = "failed"
        finally:
            await cli.disconnect()

    # Start listening in background
    task = asyncio.create_task(wait_for_login(token_id, client, qr_login_obj))
    
    pending_logins[token_id] = {
        "status": "pending",
        "task": task
    }
    
    return token_id, qr_login_obj.url

def check_qr_login_status(token_id: str) -> dict:
    """
    Checks the status of a pending QR login.
    If success, returns the session data and cleans up the pending login.
    """
    if token_id not in pending_logins:
        return {"status": "not_found"}
        
    info = pending_logins[token_id]
    
    if info["status"] == "success":
        result = {
            "status": "success",
            "session_string": info["session_string"],
            "channel_id": info["channel_id"],
            "tg_user_id": info["tg_user_id"]
        }
        del pending_logins[token_id]
        return result
        
    if info["status"] == "failed":
        del pending_logins[token_id]
        return {"status": "failed"}
        
    return {"status": "pending"}

async def get_resolved_entity(client: TelegramClient, channel_id: str):
    """
    Resolves the integer channel ID into an InputEntity. 
    If the StringSession has no cache of the channel, fetches recent dialogs to populate it.
    """
    entity_id = int(channel_id)
    # Telethon requires -100 prefix for channels/megagroups
    if entity_id > 0:
        entity_id = int(f"-100{entity_id}")
        
    try:
        return await client.get_input_entity(entity_id)
    except ValueError as e:
        if "Could not find the input entity" in str(e):
            # The session lacks the access_hash. Fetching dialogs populates the cache.
            await client.get_dialogs(limit=50)
            return await client.get_input_entity(entity_id)
        raise e


async def upload_file_to_telegram(session_string: str, channel_id: str, file_path: str, filename: str) -> int:
    """
    Uploads a file to a specific Telegram channel and returns the message ID.
    """
    from app.auth import decrypt_telegram_session
    session = StringSession(decrypt_telegram_session(session_string))
    client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    
    # We must explicitly define the entity to send to if channel_id is a raw string ID
    # In Telethon, resolving integer IDs requires the client to have seen it, but we can pass int(channel_id)
    try:
        entity = await get_resolved_entity(client, channel_id)
        
        message = await client.send_file(
            entity,
            file_path,
            force_document=True,
            attributes=[
                # You can add DocumentAttributeFilename if needed, but Telethon infers from path
            ],
            caption=f"Uploaded: {filename}"
        )
        msg_id = message.id
    except Exception as e:
        logger.error(f"Failed to upload file to telegram: {e}")
        raise e
    finally:
        await client.disconnect()
        
    return msg_id

from typing import AsyncGenerator

async def download_file_stream(session_string: str, channel_id: str, message_id: int) -> AsyncGenerator[bytes, None]:
    """
    Returns an async generator that streams the file directly from Telegram.
    Disconnects automatically when the stream completes.
    """
    from app.auth import decrypt_telegram_session
    session = StringSession(decrypt_telegram_session(session_string))
    client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    
    try:
        entity = await get_resolved_entity(client, channel_id)
        message = await client.get_messages(entity, ids=message_id)
        
        if not message or not message.media:
            raise Exception("Media not found in the specified message.")
            
        request_size = 1024 * 1024  # 1MB chunks
        total_size = message.document.size
        
        async def fetch_chunk(offset):
            async for chunk in client.iter_download(message.media, offset=offset, limit=1, request_size=request_size):
                return chunk
            return b""

        CONCURRENT_CHUNKS = 8  # 8MB buffered per active download stream
        
        for batch_start in range(0, total_size, request_size * CONCURRENT_CHUNKS):
            tasks = []
            for offset in range(batch_start, min(total_size, batch_start + request_size * CONCURRENT_CHUNKS), request_size):
                tasks.append(fetch_chunk(offset))
                
            chunks = await asyncio.gather(*tasks)
            
            for chunk in chunks:
                if chunk:
                    yield chunk
    finally:
        await client.disconnect()

async def delete_file_from_telegram(session_string: str, channel_id: str, message_id: int):
    """
    Deletes the specific message (and its media) from the Telegram channel.
    """
    from app.auth import decrypt_telegram_session
    session = StringSession(decrypt_telegram_session(session_string))
    client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    
    try:
        entity = await get_resolved_entity(client, channel_id)
        await client.delete_messages(entity, message_ids=[message_id])
    finally:
        await client.disconnect()

from telethon.tl.functions.upload import SaveBigFilePartRequest, SaveFilePartRequest
from telethon.tl.types import InputFileBig, InputFile

async def upload_chunk_to_telegram(
    session_string: str, 
    file_id: int, 
    start_part_index: int, 
    total_parts: int, 
    chunk_data: bytes, 
    is_big: bool
):
    """
    Takes a larger chunk (e.g. 5MB) from the frontend, splits it into 512KB Telegram parts,
    and uploads them in a single connection.
    """
    from app.auth import decrypt_telegram_session
    session = StringSession(decrypt_telegram_session(session_string))
    client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    try:
        PART_SIZE = 524288  # 512KB
        
        tasks = []
        for i in range(0, len(chunk_data), PART_SIZE):
            part_data = chunk_data[i:i+PART_SIZE]
            current_part_index = start_part_index + (i // PART_SIZE)
            
            if is_big:
                tasks.append(client(SaveBigFilePartRequest(
                    file_id=file_id,
                    file_part=current_part_index,
                    file_total_parts=total_parts,
                    bytes=part_data
                )))
            else:
                tasks.append(client(SaveFilePartRequest(
                    file_id=file_id,
                    file_part=current_part_index,
                    bytes=part_data
                )))
        
        # Run all 512KB part uploads concurrently!
        await asyncio.gather(*tasks)
    finally:
        await client.disconnect()

async def finalize_telegram_upload(
    session_string: str, 
    channel_id: str, 
    file_id: int, 
    total_parts: int, 
    filename: str, 
    is_big: bool
) -> int:
    """
    Sends the completed file part collection as a document to the channel.
    """
    from app.auth import decrypt_telegram_session
    session = StringSession(decrypt_telegram_session(session_string))
    client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    try:
        entity = await get_resolved_entity(client, channel_id)
        
        if is_big:
            input_file = InputFileBig(id=file_id, parts=total_parts, name=filename)
        else:
            input_file = InputFile(id=file_id, parts=total_parts, name=filename, md5_checksum="")
            
        message = await client.send_file(
            entity,
            file=input_file,
            force_document=True,
            caption=f"Uploaded: {filename}"
        )
        return message.id
    finally:
        await client.disconnect()
