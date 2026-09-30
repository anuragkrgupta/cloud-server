import asyncio
import hashlib
import math
from typing import AsyncIterator, Optional

from telethon import TelegramClient, helpers, utils
from telethon.network import MTProtoSender
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import GetFileRequest, SaveFilePartRequest, SaveBigFilePartRequest
from telethon.tl.types import InputFile, InputFileBig, TypeInputFile
from telethon.sessions import StringSession

PART_SIZE = 512 * 1024                 # Telegram-mandated chunk size
BIG_FILE_THRESHOLD = 10 * 1024 * 1024  # files above this use "big file" upload mode
DEFAULT_WORKERS = 4                    # 4 parallel DC connections — good balance of speed vs flood-wait risk
READ_BUFFER = 2 * 1024 * 1024          # 2 MB internal read buffer — reduces async iteration overhead


class DCSenderPool:
    """Pipelines requests over a single connection per DC to avoid AuthKeyDuplicatedError.
    For the current DC, it reuses the main client. For a cross-DC transfer, it creates 1 new client."""

    def __init__(self, client: TelegramClient, workers: int = DEFAULT_WORKERS, dc_id: Optional[int] = None):
        self.client = client
        self.workers = workers
        self.dc_id = dc_id or client.session.dc_id
        self.senders: list[TelegramClient] = []
        self._cross_dc_client = None

    async def open(self):
        is_same_dc = (self.dc_id == self.client.session.dc_id)
        
        if is_same_dc:
            # Safest: reuse the main client for pipelining requests concurrently.
            self.senders = [self.client] * self.workers
        else:
            # Different DC: export auth, create ONE new client, and pipeline over it.
            auth = await self.client(ExportAuthorizationRequest(self.dc_id))
            
            sender = TelegramClient(StringSession(), self.client.api_id, self.client.api_hash)
            dc = await self.client._get_dc(self.dc_id)
            sender.session.set_dc(self.dc_id, dc.ip_address, dc.port)
            
            await sender.connect()
            await sender(ImportAuthorizationRequest(id=auth.id, bytes=auth.bytes))
            
            self._cross_dc_client = sender
            self.senders = [sender] * self.workers

    async def close(self):
        if self._cross_dc_client:
            await self._cross_dc_client.disconnect()


async def upload_stream_parallel(
    client: TelegramClient,
    byte_chunks: AsyncIterator[bytes],   # your existing request.stream() iterator
    file_size: int,
    workers: int = DEFAULT_WORKERS,
) -> TypeInputFile:
    """Consumes your existing raw-body byte stream and uploads it to
    Telegram using `workers` parallel connections instead of one
    sequential connection. Returns the InputFile/InputFileBig handle to
    attach to your finalize/send-document call — same as today."""

    file_id = helpers.generate_random_long()
    part_count = math.ceil(file_size / PART_SIZE)
    is_big = file_size > BIG_FILE_THRESHOLD
    md5 = hashlib.md5() if not is_big else None

    pool = DCSenderPool(client, workers)
    await pool.open()

    # Each sender owns every Nth part (index, index+workers, index+2*workers, ...)
    # so parts can be dispatched round-robin without any coordination beyond
    # "wait for this sender's previous send before handing it the next one."
    pending: dict[int, Optional[asyncio.Task]] = {i: None for i in range(workers)}

    async def send_part(sender_idx: int, part_index: int, data: bytes):
        task = pending[sender_idx]
        if task is not None:
            await task
        req = (
            SaveBigFilePartRequest(file_id, part_index, part_count, data)
            if is_big else
            SaveFilePartRequest(file_id, part_index, data)
        )
        pending[sender_idx] = asyncio.create_task(pool.senders[sender_idx](req))

    try:
        buffer = bytearray()
        part_index = 0
        async for chunk in byte_chunks:
            if md5:
                md5.update(chunk)
            buffer.extend(chunk)
            while len(buffer) >= PART_SIZE:
                part = bytes(buffer[:PART_SIZE])
                del buffer[:PART_SIZE]
                await send_part(part_index % workers, part_index, part)
                part_index += 1

        if buffer:
            await send_part(part_index % workers, part_index, bytes(buffer))
            part_index += 1

        await asyncio.gather(*(t for t in pending.values() if t is not None))
    finally:
        for t in pending.values():
            if t is not None and not t.done():
                t.cancel()
        await pool.close()

    if is_big:
        return InputFileBig(file_id, part_count, "upload")
    
    md5_hash = md5.hexdigest() if md5 else ""
    return InputFile(file_id, part_count, "upload", md5_hash)


async def download_message_parallel(
    client: TelegramClient,
    location,            # message.media / input document location, as you already resolve it
    file_size: int,
    workers: int = DEFAULT_WORKERS,
) -> AsyncIterator[bytes]:
    """Drop-in replacement for a single iter_download() call. Yields
    bytes IN ORDER (safe for StreamingResponse) while pulling `workers`
    offset-striped ranges from Telegram in parallel underneath."""

    part_size = utils.get_appropriated_part_size(file_size) * 1024
    part_count = math.ceil(file_size / part_size)

    # Resolve the media's actual DC *before* creating the pool, so workers
    # connect to the correct Data Center (prevents FileMigrateError).
    _dc_id, input_location = utils.get_input_location(location)

    pool = DCSenderPool(client, workers, dc_id=_dc_id)
    await pool.open()

    async def fetch_part(sender_idx: int, part_index: int) -> bytes:
        req = GetFileRequest(input_location, offset=part_index * part_size, limit=part_size)
        result = await pool.senders[sender_idx](req)
        return result.bytes

    # Fetch `workers` parts at a time, but yield them in strict order so
    # the HTTP response stream stays correctly sequenced.
    try:
        next_to_fetch = 0
        while next_to_fetch < part_count:
            batch = list(range(next_to_fetch, min(next_to_fetch + workers, part_count)))
            results = await asyncio.gather(
                *(fetch_part(i % workers, part_index) for i, part_index in enumerate(batch))
            )
            for data in results:
                if data:
                    yield data
            next_to_fetch += len(batch)
    finally:
        # If the browser disconnects mid-download (closed tab, lost
        # connection), the generator gets cancelled/closed early — this
        # still has to run so the senders don't leak.
        await pool.close()
