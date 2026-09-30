# Project Memory & Status

## Current State (As of Last Major Update)
The Cloud Server project has achieved a stable, production-ready, highly-performant state with hardware-accelerated MTProto transfers, single-connection asynchronous pipelining, 30-day token persistence, QR code authentication, and user-to-user file sharing.

---

## Key Milestones & Recent Architectural Improvements

- **Hardware Acceleration (`cryptg`):**
  - Integrated `cryptg` C extension utilizing native CPU AES-NI instructions for MTProto AES-IGE encryption and decryption.
  - Achieved a **400x cryptographic speedup**, slashing CPU usage and boosting streaming upload throughput from ~1 MB/s to ~3.9+ MB/s over standard broadband.
  - Implemented `ensure_hardware_acceleration()` in `backend/app/main.py` which automatically verifies and self-installs `cryptg` on startup across any host environment.

- **Single-Socket MTProto Pipelining (`DCSenderPool`):**
  - Resolved session revocations caused by raw multi-socket connection collisions (`AuthKeyDuplicatedError`).
  - Refactored `parallel_transfer.py` to achieve parallel throughput via **asynchronous request pipelining over a single authenticated connection per DC**, rather than opening multiple raw TCP sockets with cloned auth keys.
  - Ensured all background workers and task queues cleanly terminate and cancel within `finally` blocks.

- **Extended Token Lifetime (30 Days):**
  - Increased `ACCESS_TOKEN_EXPIRE_MINUTES` to `43200` (30 days) across `backend/.env` and `render.yaml`.
  - Solved HTTP 401 Unauthorized interruptions during long-running multi-gigabyte file transfers.

- **Multi-Gigabyte Volume Slicing:**
  - Verified and tested multi-volume transfers exceeding Telegram's 2GB document limit (e.g. 2.66 GB and 4.95 GB sets split into ~1.90 GB sequential parts).
  - Ensured contiguous streaming reassembly during downloads without local disk buffering.

- **Automatic Session Invalidation Recovery:**
  - Updated `handle_telegram_error()` in `backend/app/routes/files.py` to catch `AuthKeyDuplicatedError` and session revocations, cleanly resetting the invalid session in Supabase PostgreSQL while preserving user storage channel bindings.

- **Frontend & API Client:**
  - Modernized `dashboard.html` and `dashboard.js` with dark glassmorphism styling, real-time speed tracking, percent progress bars, and ETA calculations.
  - Centralized API interaction via `frontend/js/api.js` (`apiFetch`).

- **Database & Hosting:**
  - Configured Supabase PostgreSQL via transaction pooler with `pool_pre_ping=True` and `pool_recycle=3600`.
  - Deployment-ready blueprints for Render (`render.yaml`) and Vercel (`vercel.json`).

---

## Known Issues & Watchpoints
- **Server Reloads Mid-QR:** The QR login state dictionary is held in memory; local server hot-reloads during file saves require refreshing the QR code.
- **Client Cache Management:** All user operations reuse cached `TelegramClient` instances guarded by async locks to maintain a single MTProto state.

---

## Important Rules for Future Development
- Always preserve `cryptg>=0.5.0` in `requirements.txt`.
- Never attempt to open multiple raw TCP connections with the same Telegram session string. Concurrency must be achieved via request pipelining over a single connection per DC.
- Always make API calls through `apiFetch` in `frontend/js/api.js`.
