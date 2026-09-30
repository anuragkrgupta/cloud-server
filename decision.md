# Key Decisions Log

This document tracks significant architectural, security, and implementation decisions made during the project lifecycle.

---

## 1. Decentralized Storage via Telegram
- **Context:** Needed a cost-effective, scalable, and durable storage backend for personal cloud files.
- **Decision:** Utilize the Telegram API (via Telethon) as a dumb blob storage layer. User files are stored as document messages in dedicated private channels, while PostgreSQL stores only file metadata and message IDs.
- **Rationale:** High availability, zero storage infrastructure costs, generous per-account capacity, and support for multi-gigabyte files via volume slicing.

---

## 2. Hardware Acceleration via `cryptg` (AES-NI)
- **Context:** Streaming upload throughput was severely capped at ~1–2 MB/s, with the server CPU pegged at 100% utilization. Profiling revealed that Telethon defaulted to pure Python `pyaes` for MTProto AES-IGE payload encryption.
- **Decision:** Mandate `cryptg>=0.5.0` (native C extension utilizing CPU AES-NI instructions) and implement automated self-verification (`ensure_hardware_acceleration()`) on server startup in `main.py`.
- **Rationale:** Produces a **400x cryptographic speedup**, eliminates CPU bottlenecks, and unlocks full network interface saturation (~3.9+ MB/s). Startup verification guarantees hardware acceleration is active across all deployment environments.

---

## 3. Asynchronous Request Pipelining vs. Multi-Socket Sessions
- **Context:** To increase transfer speeds, an initial approach attempted to open multiple concurrent raw TCP sockets using cloned authorization keys. This triggered Telegram's security heuristics, resulting in fatal `AuthKeyDuplicatedError` exceptions and permanent session revocation.
- **Decision:** Refactored `DCSenderPool` (`parallel_transfer.py`) to pipeline multiple concurrent RPC requests asynchronously over a **single authenticated connection per DC**, rather than opening multiple raw TCP sockets.
- **Rationale:** Conforms strictly to Telegram's MTProto security specifications, eliminates session collisions, and achieves maximum network saturation through asynchronous concurrent request queuing.

---

## 4. 30-Day JWT Token Lifetime
- **Context:** The previous 60-minute JWT token lifetime caused uploads of large multi-volume files (or slow broadband connections) to fail with HTTP 401 Unauthorized errors mid-transfer.
- **Decision:** Extended `ACCESS_TOKEN_EXPIRE_MINUTES` to `43200` (30 days) across `.env` and `render.yaml`.
- **Rationale:** Long-lived tokens ensure that multi-gigabyte transfers and multi-file batch uploads are never interrupted by authentication expiration.

---

## 5. Preserving Channel Bindings on Session Revocation
- **Context:** When a user's Telegram session expired or became invalid, resetting both session string and channel ID would orphan existing uploaded files.
- **Decision:** In `handle_telegram_error()` (`files.py`), safely null only `telegram_session` while preserving `channel_id` and `telegram_user_id`.
- **Rationale:** Allows users to re-authenticate via QR code without losing access to their previously uploaded files and channel history.

---

## 6. Dedicated Private Channels (`CloudStorage_{tg_user_id}`)
- **Context:** Saving files to Telegram's "Saved Messages" clutters the user's personal chat space and creates collision risks.
- **Decision:** Automatically create an isolated private channel (`CloudStorage_{tg_user_id}`) during the Telegram QR login process.
- **Rationale:** Keeps the user's personal messaging space pristine, isolates storage operations, and provides a clear boundary for cloud files.

---

## 7. File Sharing & Background Server-Side Transfers
- **Context:** When User A shares a file with User B, serving User A's channel directly means User A could delete the file, breaking User B's access.
- **Decision:** Implemented a "Save to my Cloud" feature that creates an asynchronous background task (`transfer_file_between_users`) to stream parts directly from User A's channel into User B's private channel.
- **Rationale:** Grants User B independent ownership of the file without server disk buffering or client-side downloading/re-uploading.

---

## 8. Decoupled Deployment Strategy
- **Context:** Project contains a static frontend and a Python backend.
- **Decision:** Deploy frontend to Vercel and backend to Render.
- **Rationale:** Vercel serves static assets globally via CDN with instant invalidation, while Render provides a managed Python ASGI environment with custom system libraries (`render.yaml`).

---

## 9. Implementation of `apiFetch` Wrapper
- **Context:** Decoupled domains caused CORS, header inconsistencies, and cookie handling challenges.
- **Decision:** Created a centralized `apiFetch` utility (`frontend/js/api.js`).
- **Rationale:** Automatically coordinates `Authorization: Bearer <token>` headers, `credentials: 'include'` for cookies, environment-aware base URL resolution, and unified handling of HTTP 401 errors.
