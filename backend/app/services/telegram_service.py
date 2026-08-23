import math
import random
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.errors import SessionPasswordNeededError
from app.config import settings

logger = logging.getLogger(__name__)

import asyncio
import uuid

pending_logins = {}

_client_cache = {}

_client_locks = {}

async def get_client_for_session(session_string: str) -> TelegramClient:
    """Returns a connected TelegramClient for the given session string."""
    if session_string not in _client_locks:
        _client_locks[session_string] = asyncio.Lock()
        
    async with _client_locks[session_string]:
        if session_string in _client_cache:
            client = _client_cache[session_string]
            if not client.is_connected():
                await client.connect()
            return client
    
        from app.auth import decrypt_telegram_session
        decrypted_session = decrypt_telegram_session(session_string)
        session = StringSession(decrypted_session)
        client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
        await client.connect()
        _client_cache[session_string] = client
        return client

async def disconnect_all_clients():
    """Disconnects all Telegram clients gracefully to prevent AuthKeyDuplicatedError on reload."""
    for session_string, client in _client_cache.items():
        if client.is_connected():
            await client.disconnect()
    _client_cache.clear()

# ---------------------------------------------------------------------------
# Persistent upload-client pool
# Keyed by file_id (int). Entries: {"client": TelegramClient, "lock": asyncio.Lock}
# Created on the first chunk, torn down inside finalize_telegram_upload.
# ---------------------------------------------------------------------------
_upload_clients = {}

async def _get_upload_client(file_id: int, session_string: str) -> TelegramClient:
    if file_id not in _upload_clients:
        client = await get_client_for_session(session_string)
        _upload_clients[file_id] = {
            "client": client,
            "lock": asyncio.Lock()
        }
    return _upload_clients[file_id]["client"]

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
            
            await cli.disconnect()
            
        except SessionPasswordNeededError:
            logger.info(f"2FA required for {tid}")
            pending_logins[tid]["status"] = "2fa_required"
            pending_logins[tid]["client"] = cli
            return # Keep connection open for password submission
        except Exception as e:
            logger.error(f"QR Login failed for {tid}: {e}")
            pending_logins[tid]["status"] = "failed"
            await cli.disconnect()

    # Start listening in background
    task = asyncio.create_task(wait_for_login(token_id, client, qr_login_obj))
    
    pending_logins[token_id] = {
        "status": "pending",
        "task": task
    }
    
    return token_id, qr_login_obj.url

async def submit_qr_password(token_id: str, password: str) -> dict:
    if token_id not in pending_logins:
        return {"status": "not_found"}
        
    info = pending_logins[token_id]
    if info["status"] != "2fa_required":
        return {"status": "invalid_state"}
        
    client = info["client"]
    try:
        user = await client.sign_in(password=password)
        
        # Create a private channel for Cloud Storage
        channel_id = ""
        try:
            result = await client(CreateChannelRequest(
                title="Personal Cloud Storage",
                about="Storage channel managed by Cloud Server Web App",
                megagroup=False
            ))
            channel = result.chats[0]
            channel_id = str(channel.id)
        except Exception as e:
            logger.error(f"Failed to create storage channel: {e}")
            
        session_string = client.session.save()
        tg_user_id = str(user.id)
        
        pending_logins[token_id]["status"] = "success"
        pending_logins[token_id]["session_string"] = session_string
        pending_logins[token_id]["channel_id"] = channel_id
        pending_logins[token_id]["tg_user_id"] = tg_user_id
        
        await client.disconnect()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to submit 2FA password: {e}")
        pending_logins[token_id]["status"] = "failed"
        await client.disconnect()
        return {"status": "failed", "error": str(e)}

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
    client = await get_client_for_session(session_string)
    
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
    
        
    return msg_id

from typing import AsyncGenerator

async def download_file_stream(session_string: str, channel_id: str, message_id: int) -> AsyncGenerator[bytes, None]:
    """
    Returns an async generator that streams the file directly from Telegram.
    Disconnects automatically when the stream completes.
    """
    from app.auth import decrypt_telegram_session
    client = await get_client_for_session(session_string)
    
    try:
        entity = await get_resolved_entity(client, channel_id)
        message = await client.get_messages(entity, ids=message_id)
        
        if not message or not message.media:
            raise Exception("Media not found in the specified message.")
            
        async for chunk in client.iter_download(message.media):
            yield chunk
            
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise e

async def download_multiple_messages_stream(session_string: str, channel_id: str, message_ids: list[int]) -> AsyncGenerator[bytes, None]:
    """
    Returns an async generator that streams the file directly from multiple Telegram messages.
    Maintains a single connection for all parts.
    """
    from app.auth import decrypt_telegram_session
    client = await get_client_for_session(session_string)
    
    try:
        entity = await get_resolved_entity(client, channel_id)
        
        for msg_id in message_ids:
            message = await client.get_messages(entity, ids=msg_id)
            if not message or not message.media:
                raise Exception(f"Media not found in the specified message (ID: {msg_id}).")
                
            async for chunk in client.iter_download(message.media):
                yield chunk
                
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise e

async def delete_file_from_telegram(session_string: str, channel_id: str, message_id: int):
    """
    Deletes the specific message (and its media) from the Telegram channel.
    """
    from app.auth import decrypt_telegram_session
    client = await get_client_for_session(session_string)
    
    try:
        entity = await get_resolved_entity(client, channel_id)
        await client.delete_messages(entity, message_ids=[message_id])
    
    except Exception as e:
        logger.error(f"Delete error: {e}")
        raise e

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
    Sends one frontend chunk (e.g. 5 MB) to Telegram as sequential 512 KB parts,
    reusing a single persistent connection for the lifetime of the upload.
    Sequential sending avoids Telegram flood-wait caused by parallel RPC calls.
    """
    PART_SIZE = 524288  # 512 KB — Telegram's required part size

    client = await _get_upload_client(file_id, session_string)
    lock = _upload_clients[file_id]["lock"]

    async with lock:
        for i in range(0, len(chunk_data), PART_SIZE):
            part_data = chunk_data[i : i + PART_SIZE]
            part_index = start_part_index + (i // PART_SIZE)

            if is_big:
                req = SaveBigFilePartRequest(
                    file_id=file_id,
                    file_part=part_index,
                    file_total_parts=total_parts,
                    bytes=part_data,
                )
            else:
                req = SaveFilePartRequest(
                    file_id=file_id,
                    file_part=part_index,
                    bytes=part_data,
                )

            await client(req)


async def upload_stream_to_telegram(
    session_string: str,
    channel_id: str,
    filename: str,
    file_size: int,
    stream: AsyncGenerator[bytes, None]
) -> int:
    PART_SIZE = 524288
    total_parts = math.ceil(file_size / PART_SIZE)
    is_big = file_size > 10 * 1024 * 1024
    file_id = random.randint(1, 2**63 - 1)
    
    client = await get_client_for_session(session_string)
    
    buffer = b""
    part_index = 0
    
    try:
        async for chunk in stream:
            buffer += chunk
            while len(buffer) >= PART_SIZE:
                part_data = buffer[:PART_SIZE]
                buffer = buffer[PART_SIZE:]
                
                if is_big:
                    req = SaveBigFilePartRequest(file_id=file_id, file_part=part_index, file_total_parts=total_parts, bytes=part_data)
                else:
                    req = SaveFilePartRequest(file_id=file_id, file_part=part_index, bytes=part_data)
                
                await client(req)
                part_index += 1
        
        if buffer:
            if is_big:
                req = SaveBigFilePartRequest(file_id=file_id, file_part=part_index, file_total_parts=total_parts, bytes=buffer)
            else:
                req = SaveFilePartRequest(file_id=file_id, file_part=part_index, bytes=buffer)
            
            await client(req)
            part_index += 1

        entity = await get_resolved_entity(client, channel_id)
        if is_big:
            input_file = InputFileBig(id=file_id, parts=total_parts, name=filename)
        else:
            input_file = InputFile(id=file_id, parts=total_parts, name=filename, md5_checksum="")

        message = await client.send_file(entity, file=input_file, force_document=True)
        return message.id
    except Exception as e:
        logger.error(f"Stream upload error: {e}")
        raise e


