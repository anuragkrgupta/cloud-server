# Agent Context & Engineering Guidelines

This document serves as the master engineering guide for AI agents working on the "Cloud Server" project. Always consult this document before proposing or implementing architectural changes.

---

## 1. System Overview & Repository Layout

The project is a cloud storage platform utilizing Telegram's infrastructure as an unlimited object/blob store, with **PostgreSQL (Supabase)** handling user and file metadata.

- **Monorepo Layout:**
  - `/backend`: FastAPI Python application, SQLAlchemy ORM, Telethon MTProto client, Uvicorn ASGI server.
  - `/frontend`: Decoupled Vanilla HTML5, CSS3, and JavaScript (ES6+). Zero build step, hosted on Vercel (or statically served by FastAPI locally).
- **Deployment Targets:**
  - Backend deployed to **Render** (configured via `render.yaml`).
  - Frontend deployed to **Vercel** (configured via `vercel.json`).

---

## 2. Cryptographic Hardware Acceleration (`cryptg`)

- **Crucial Performance Factor:** Telethon defaults to a pure Python software implementation (`pyaes`) for AES-IGE MTProto payload encryption. Pure Python encryption caps upload throughput to ~1–2 MB/s and pins CPU at 100%.
- **Solution:** We mandate and enforce `cryptg` (native C extension utilizing CPU hardware AES-NI instructions). This yields a **400x cryptographic speedup** and unlocks full network interface saturation (~3.9+ MB/s over standard broadband).
- **Automated Verification:** `backend/app/main.py` runs `ensure_hardware_acceleration()` during startup. If `cryptg` is absent, it automatically installs and verifies it across any host or container.
- **Agent Rule:** Always ensure `cryptg>=0.5.0` remains in `requirements.txt`. Never remove or bypass hardware acceleration verification.

---

## 3. Parallel Transfer Architecture & MTProto Rules

File transfers are orchestrated by `backend/app/services/parallel_transfer.py` using `DCSenderPool`.

### The Single-Socket Pipelining Rule (CRITICAL)
- **The Pitfall:** Opening multiple raw TCP sockets with the identical Telegram `auth_key` causes Telegram's security systems to trigger `AuthKeyDuplicatedError` and permanently revoke the user's session.
- **The Correct Architecture:** Parallelism MUST be achieved via **asynchronous MTProto request pipelining over a single authenticated connection per DC**.
- `DCSenderPool` distributes chunks across an asynchronous worker pool (default `WORKERS_PER_TRANSFER=4`), queuing up to 4 concurrent `SaveBigFilePartRequest` or `GetFileRequest` RPC calls over the single connection.
- **Agent Rule:** NEVER attempt to spawn multiple `TelegramClient` instances or raw TCP sockets using the same session string.

---

## 4. Authentication, Sessions & Token Lifetime

- **JWT Lifetime:** Access tokens are configured with `ACCESS_TOKEN_EXPIRE_MINUTES=43200` (30 days) in `.env` and `render.yaml`. This ensures that long multi-gigabyte uploads (which may span hours) are never aborted mid-flight by an HTTP 401 Unauthorized token expiry.
- **Session String Encryption:** User Telegram `StringSession` strings are encrypted at rest using Fernet with a key derived from `JWT_SECRET_KEY`.
- **Session Invalidation Handling:**
  - `handle_telegram_error()` in `backend/app/routes/files.py` catches `AuthKeyDuplicatedError`, `AuthKeyUnregisteredError`, `SessionExpiredError`, `SessionRevokedError`, and `UserDeactivatedError`.
  - On detection, it safely sets `telegram_session = None` in PostgreSQL so the user can re-authenticate via QR code.
  - **Important:** It preserves `channel_id` and `telegram_user_id` so existing stored files are never orphaned.

---

## 5. Large File Multi-Volume Slicing

- Telegram imposes a strict 2 GB per-document limit.
- Files exceeding ~1.90 GB are partitioned on the frontend into sequential volumes (aligned to 3,890 parts of 512 KB = 2,039,480,320 bytes).
- Each volume is uploaded as a distinct Telegram document message via `/api/upload/stream`.
- Once all volumes finish, the frontend commits them via `POST /api/upload/complete`, storing a parent `FileRecord` and sequential `FilePartRecord` entries.
- Downloads via `GET /api/download/{file_id}` dynamically stream all parts in contiguous sequence to the browser without local disk buffering.

---

## 6. Frontend Rules

1. **Centralized Fetch Wrapper:** Always use `apiFetch` from `frontend/js/api.js`. Never use raw `fetch()`. `apiFetch` handles base URL resolution, credentials (`credentials: 'include'`), and Bearer auth headers.
2. **Vanilla JS Only:** Keep the frontend lightweight with Vanilla ES6+. No npm, Node.js, or heavyweight frameworks.
3. **CORS Awareness:** The frontend and backend live on separate domains in production. All new backend endpoints must be supported by FastAPI's CORS middleware.

---

## 7. Testing & Verification

- Backend unit and integration tests reside in `backend/tests/`.
- Run tests via `pytest -v` within the backend virtual environment.
- When testing live transfers, verify that `cryptg` is logged as active in startup output.
