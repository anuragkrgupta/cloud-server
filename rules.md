# Coding Standards & Project Rules

This document establishes the mandatory development standards and architectural rules for the Cloud Server project.

---

## 1. Backend (Python/FastAPI)

1. **Hardware Acceleration Enforcement:**
   - Always maintain `cryptg>=0.5.0` in `requirements.txt`.
   - Never disable or remove `ensure_hardware_acceleration()` in `backend/app/main.py`. Pure Python `pyaes` encryption creates severe CPU bottlenecks and drops upload throughput to ~1 MB/s.

2. **Single-Socket MTProto Pipelining Rule:**
   - **CRITICAL:** NEVER attempt to open multiple concurrent raw TCP connections with the same Telegram session string.
   - Concurrency must always be achieved via **asynchronous request pipelining over a single connection per DC** using `DCSenderPool` in `parallel_transfer.py`.
   - Violating this rule triggers Telegram's `AuthKeyDuplicatedError` and permanently revokes user sessions.

3. **Zero Local Disk Footprint:**
   - File uploads and downloads must stream directly through memory using `request.stream()` and asynchronous chunk generators.
   - Never write file bytes to local server disk or temporary directories (`/tmp`, scratch, etc.).

4. **Session Error Handling & Channel Preservation:**
   - When catching Telegram authentication errors (`AuthKeyDuplicatedError`, `SessionExpiredError`, `SessionRevokedError`, etc.) in `files.py`, safely set `telegram_session = None` in the database.
   - **NEVER** null or delete `channel_id` or `telegram_user_id` on session errors. Preserving these fields ensures users don't lose access to their uploaded files upon re-login.

5. **Token Expiration Settings:**
   - Keep `ACCESS_TOKEN_EXPIRE_MINUTES=43200` (30 days) in `.env` and `render.yaml` to ensure multi-gigabyte transfers are never aborted mid-flight by token expiry.

6. **Asynchronous Lifespan Management:**
   - Use `async/await` for all I/O operations (database queries, Telegram MTProto calls, streaming endpoints).
   - Long-lived clients and pools must be managed within FastAPI's `lifespan` context manager (`main.py`). Never use deprecated `@app.on_event`.

7. **Background Tasks:**
   - Long-running operations (like inter-user file transfers via `save_shared_file`) must run as background `asyncio` tasks so HTTP requests return immediately.

8. **Strict Environment Secrets:**
   - Never hardcode credentials, JWT secrets, database connection strings, or Telegram API credentials. Always use `backend/app/config.py` backed by environment variables.

---

## 2. Frontend (JavaScript/HTML/CSS)

1. **Mandatory `apiFetch` Wrapper:**
   - **NEVER** use raw browser `fetch()`. All backend communications must use `apiFetch` from `frontend/js/api.js`.
   - `apiFetch` ensures uniform handling of base URLs, Bearer authorization headers, cross-origin cookies (`credentials: 'include'`), and HTTP 401 token expiration.

2. **Vanilla JavaScript Standard:**
   - Adhere strictly to Vanilla ES6+ JavaScript. Do not introduce React, Vue, Angular, or Node.js/npm dependencies without explicit approval.

3. **Large File Volume Slicing:**
   - Any upload exceeding ~1.90 GB must be sliced client-side into clean ~1.90 GB volumes (aligned to 3,890 parts of 512 KB = 2,039,480,320 bytes) before streaming to `/api/upload/stream`.

4. **Real-Time User Feedback:**
   - Provide accurate progress tracking, transfer speed (MB/s), and estimated time remaining (ETA) during uploads and downloads.

---

## 3. Deployment & Infrastructure

1. **Render Deployment:**
   - Backend configurations are declared in `render.yaml`. Any environment variable additions or system requirement changes must be reflected in `render.yaml`.

2. **Vercel Deployment:**
   - Frontend routing and static file handling are governed by `vercel.json`. Ensure any new HTML pages or asset routes conform to these rules.
