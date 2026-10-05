import math
import random
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.errors import SessionPasswordNeededError
from app.config import settings
from app.services.parallel_transfer import upload_stream_parallel, download_message_parallel

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
# Telegram Login Helpers
# ---------------------------------------------------------------------------

async def _finalize_login(
    token_id: str, 
    client: TelegramClient, 
    tg_user_id: str, 
    u_channel_id: str = None, 
    u_tg_user_id: str = None, 
    force_new_channel: bool = False
) -> dict:
    """
    Helper to perform post-login checks and setup.
    Handles account mismatch, channel creation, and session saving.
    Returns the resulting info dict to be returned to the caller or saved in pending_logins.
    """
    if u_channel_id and u_tg_user_id and tg_user_id != u_tg_user_id and not force_new_channel:
        session_str = client.session.save()
        await client.disconnect()
        return {
            "status": "account_mismatch",
            "session_string": session_str,
            "tg_user_id": tg_user_id
        }
        
    channel_id = u_channel_id
    if not channel_id or force_new_channel:
        # Create a private channel for Cloud Storage
        try:
            result = await client(CreateChannelRequest(
                title=f"CloudStorage_{tg_user_id}",
                about="Storage channel managed by Cloud Server Web App",
                megagroup=False
            ))
            channel = result.chats[0]
            channel_id = str(channel.id)
        except Exception as e:
            logger.error(f"Failed to create storage channel: {e}")
            await client.disconnect()
            return {"status": "failed", "error": f"Could not create storage channel: {e}"}
    else:
        try:
            await get_resolved_entity(client, channel_id)
        except Exception as e:
            logger.warning(f"Failed to resolve existing channel during login: {e}")
            
    session_string = client.session.save()
    await client.disconnect()
    
    return {
        "status": "success",
        "session_string": session_string,
        "channel_id": channel_id,
        "tg_user_id": tg_user_id
    }

import time

async def cleanup_stale_logins(max_age_seconds=300):
    now = time.time()
    for tid in list(pending_logins.keys()):
        if now - pending_logins[tid].get("created_at", now) > max_age_seconds:
            info = pending_logins.pop(tid, {})
            client = info.get("client")
            if client and hasattr(client, 'is_connected') and client.is_connected():
                await client.disconnect()
            task = info.get("task")
            if task and not task.done():
                task.cancel()

async def start_qr_login(user_channel_id: str = None, user_tg_user_id: str = None) -> tuple[str, str]:
    """
    Initiates a Telegram connection and starts QR login.
    Returns (token_id, qr_url)
    """
    token_id = str(uuid.uuid4())
    session = StringSession()
    client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    
    qr_login_obj = await client.qr_login()
    
    async def wait_for_login(tid, cli, qr, u_channel_id, u_tg_user_id):
        try:
            # This blocks until the user scans and approves the QR code, or it times out
            user = await qr.wait()
            tg_user_id = str(user.id)
            
            result = await _finalize_login(tid, cli, tg_user_id, u_channel_id, u_tg_user_id)
            pending_logins[tid].update(result)
            
            
        except SessionPasswordNeededError:
            logger.info(f"2FA required for {tid}")
            pending_logins[tid]["status"] = "2fa_required"
            pending_logins[tid]["client"] = cli
            pending_logins[tid]["user_channel_id"] = u_channel_id
            pending_logins[tid]["user_tg_user_id"] = u_tg_user_id
            return # Keep connection open for password submission
        except Exception as e:
            logger.error(f"QR Login failed for {tid}: {e}")
            pending_logins[tid]["status"] = "failed"
            await cli.disconnect()

    # Start listening in background
    task = asyncio.create_task(wait_for_login(token_id, client, qr_login_obj, user_channel_id, user_tg_user_id))
    
    await cleanup_stale_logins()
    
    pending_logins[token_id] = {
        "status": "pending",
        "task": task,
        "created_at": time.time(),
        "client": client
    }
    
    return token_id, qr_login_obj.url

async def submit_qr_password(token_id: str, password: str, force_new_channel: bool = False) -> dict:
    if token_id not in pending_logins:
        return {"status": "not_found"}
        
    info = pending_logins[token_id]
    if info["status"] != "2fa_required":
        return {"status": "invalid_state"}
        
    client = info["client"]
    u_channel_id = info.get("user_channel_id")
    u_tg_user_id = info.get("user_tg_user_id")
    
    try:
        user = await client.sign_in(password=password)
        tg_user_id = str(user.id)
        
        result = await _finalize_login(token_id, client, tg_user_id, u_channel_id, u_tg_user_id, force_new_channel)
        pending_logins[token_id].update(result)
        return result
    except Exception as e:
        logger.error(f"Failed to submit 2FA password: {e}")
        pending_logins[token_id]["status"] = "failed"
        await client.disconnect()
        return {"status": "failed", "error": str(e)}

async def start_phone_login(phone_number: str, user_channel_id: str = None, user_tg_user_id: str = None) -> str:
    """
    Initiates a Telegram connection and requests a phone code.
    Returns token_id.
    """
    token_id = str(uuid.uuid4())
    session = StringSession()
    client = TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)
    
    await client.connect()
    
    try:
        sent_code = await client.send_code_request(phone_number)
        
        await cleanup_stale_logins()
        
        pending_logins[token_id] = {
            "status": "waiting_for_code",
            "client": client,
            "created_at": time.time(),
            "phone_number": phone_number,
            "phone_code_hash": sent_code.phone_code_hash,
            "user_channel_id": user_channel_id,
            "user_tg_user_id": user_tg_user_id
        }
        return token_id
    except Exception as e:
        logger.error(f"Failed to send code for phone login: {e}")
        await client.disconnect()
        raise e

async def submit_phone_code(token_id: str, code: str) -> dict:
    if token_id not in pending_logins:
        return {"status": "not_found"}
        
    info = pending_logins[token_id]
    if info["status"] != "waiting_for_code":
        return {"status": "invalid_state"}
        
    client = info["client"]
    phone_number = info["phone_number"]
    phone_code_hash = info["phone_code_hash"]
    u_channel_id = info.get("user_channel_id")
    u_tg_user_id = info.get("user_tg_user_id")
    
    try:
        user = await client.sign_in(phone=phone_number, code=code, phone_code_hash=phone_code_hash)
        tg_user_id = str(user.id)
        
        result = await _finalize_login(token_id, client, tg_user_id, u_channel_id, u_tg_user_id)
        pending_logins[token_id].update(result)
        return result
        
    except SessionPasswordNeededError:
        logger.info(f"2FA required for {token_id}")
        pending_logins[token_id]["status"] = "2fa_required"
        # The client remains connected for 2FA submission.
        return {"status": "2fa_required"}
    except Exception as e:
        logger.error(f"Failed to submit phone code: {e}")
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
        
    if info["status"] == "account_mismatch":
        result = {
            "status": "account_mismatch",
            "session_string": info["session_string"],
            "tg_user_id": info["tg_user_id"]
        }
        # DO NOT delete pending_logins yet so they can confirm/override
        return result
        
    if info["status"] == "failed":
        del pending_logins[token_id]
        return {"status": "failed"}
        
    return {"status": info["status"]}

async def override_account_mismatch(token_id: str) -> dict:
    if token_id not in pending_logins:
        return {"status": "not_found"}
    info = pending_logins[token_id]
    if info["status"] != "account_mismatch":
        return {"status": "invalid_state"}
        
    session_string = info["session_string"]
    tg_user_id = info["tg_user_id"]
    
    client = await get_client_for_session(session_string)
    channel_id = ""
    try:
        result = await client(CreateChannelRequest(
            title=f"CloudStorage_{tg_user_id}",
            about="Storage channel managed by Cloud Server Web App",
            megagroup=False
        ))
        channel = result.chats[0]
        channel_id = str(channel.id)
    except Exception as e:
        logger.error(f"Failed to create storage channel on override: {e}")
        
    session_string = client.session.save()
    
    pending_logins[token_id]["status"] = "success"
    pending_logins[token_id]["session_string"] = session_string
    pending_logins[token_id]["channel_id"] = channel_id
    
    await client.disconnect()
    return {"status": "success"}

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
            
        async for chunk in download_message_parallel(
            client, 
            message.media, 
            message.document.size, 
            workers=settings.WORKERS_PER_TRANSFER
        ):
            yield chunk
            
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise e

async def download_multiple_messages_stream(session_string: str, channel_id: str, message_ids: list[int]) -> AsyncGenerator[bytes, None]:
    """
    Returns an async generator that streams the file directly from multiple Telegram messages.
    Maintains a single connection for all parts.
    Eagerly validates the session before returning the stream.
    """
    from app.auth import decrypt_telegram_session
    client = await get_client_for_session(session_string)
    
    # Eager validation: this will raise AuthKeyUnregisteredError immediately if session is invalid
    entity = await get_resolved_entity(client, channel_id)
    
    if not message_ids:
        raise ValueError("No message IDs provided")
        
    # Eagerly fetch the first message to force a network request and catch session errors before streaming
    first_message = await client.get_messages(entity, ids=message_ids[0])
    if not first_message or not first_message.media:
        raise Exception(f"Media not found in the specified message (ID: {message_ids[0]}).")

    async def _stream():
        try:
            for i, msg_id in enumerate(message_ids):
                if i == 0:
                    message = first_message
                else:
                    message = await client.get_messages(entity, ids=msg_id)
                    if not message or not message.media:
                        raise Exception(f"Media not found in the specified message (ID: {msg_id}).")
                    
                async for chunk in download_message_parallel(
                    client, 
                    message.media, 
                    message.document.size, 
                    workers=settings.WORKERS_PER_TRANSFER
                ):
                    yield chunk
        except Exception as e:
            logger.error(f"Download stream error: {e}")
            raise e

    return _stream()

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

# Upload client pool was removed because upload_stream_parallel handles connections now.


async def upload_stream_to_telegram(
    session_string: str,
    channel_id: str,
    filename: str,
    file_size: int,
    stream: AsyncGenerator[bytes, None]
) -> int:
    client = await get_client_for_session(session_string)
    
    try:
        input_file = await upload_stream_parallel(
            client, 
            stream, 
            file_size, 
            workers=settings.WORKERS_PER_TRANSFER
        )
        input_file.name = filename

        entity = await get_resolved_entity(client, channel_id)

        message = await client.send_file(entity, file=input_file, force_document=True)
        return message.id
    except Exception as e:
        logger.exception(f"Stream upload error: {e}")
        raise e


