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

PART_SIZE = 512 * 1024                 # Telegram-mandated chunk size
BIG_FILE_THRESHOLD = 10 * 1024 * 1024  # files above this use "big file" upload mode
DEFAULT_WORKERS = 4                    # start conservative; 4-8 is the usual sweet spot


class DCSenderPool:
    """N authenticated MTProtoSender connections to one Telegram DC,
    all sharing the account's auth key via exported authorization."""

    def __init__(self, client: TelegramClient, workers: int = DEFAULT_WORKERS):
        self.client = client
        self.workers = workers
        self.dc_id = client.session.dc_id
        self.senders: list[MTProtoSender] = []
        self._exported_auth = None  # cached so we only export once per pool

    async def _open_one(self) -> MTProtoSender:
        dc = await self.client._get_dc(self.dc_id)
        sender = MTProtoSender(self.client.session.auth_key, loggers=self.client._log)
        await sender.connect(
            self.client._connection(
                dc.ip_address, dc.port, dc.id,
                loggers=self.client._log, proxy=self.client._proxy,
            )
        )
        # Only needed if this pool targets a DC different from the main
        # session's home DC — same-DC senders inherit the auth key directly.
        if self.dc_id != self.client.session.dc_id:
            if self._exported_auth is None:
                self._exported_auth = await self.client(ExportAuthorizationRequest(self.dc_id))
            req = ImportAuthorizationRequest(
                id=self._exported_auth.id, bytes=self._exported_auth.bytes
            )
            await sender.send(InvokeWithLayerRequest(LAYER, req))
        return sender

    async def open(self):
        self.senders = await asyncio.gather(*(self._open_one() for _ in range(self.workers)))

    async def close(self):
        await asyncio.gather(*(s.disconnect() for s in self.senders), return_exceptions=True)


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
        if pending[sender_idx] is not None:
            await pending[sender_idx]
        req = (
            SaveBigFilePartRequest(file_id, part_index, part_count, data)
            if is_big else
            SaveFilePartRequest(file_id, part_index, data)
        )
        pending[sender_idx] = asyncio.create_task(client._call(pool.senders[sender_idx], req))

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
        # Always tear down every sender — a crash or a dropped client
        # connection mid-upload must not leave sockets dangling, or you
        # risk exactly the auth-key-ban scenario brain.md already flags
        # for the main cached client.
        await pool.close()

    if is_big:
        return InputFileBig(file_id, part_count, "upload")
    return InputFile(file_id, part_count, "upload", md5.hexdigest())


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

    pool = DCSenderPool(client, workers)
    await pool.open()

    # Ensure the location is correctly converted for raw API requests
    _dc_id, input_location = utils.get_input_location(location)

    async def fetch_part(sender_idx: int, part_index: int) -> bytes:
        req = GetFileRequest(input_location, offset=part_index * part_size, limit=part_size)
        result = await client._call(pool.senders[sender_idx], req)
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
