# brain.md — Developer Reference

Deep-dive technical reference for the Telegram Cloud Storage project. Covers the full architecture, data flows, cryptographic acceleration, MTProto connection rules, security model, known gotchas, and areas for future improvement.

---

## Table of Contents

1. [Project Layout](#1-project-layout)
2. [Architecture Overview](#2-architecture-overview)
3. [Database Schema](#3-database-schema)
4. [Authentication & Security](#4-authentication--security)
5. [Upload Flow (Streaming & Pipelined Parallelism)](#5-upload-flow-streaming--pipelined-parallelism)
6. [Download Flow (Prefetched Streaming)](#6-download-flow-prefetched-streaming)
7. [Telegram Connection Management & DCSenderPool](#7-telegram-connection-management--dcsenderpool)
8. [Frontend Pages & Architecture](#8-frontend-pages--architecture)
9. [Config & Environment](#9-config--environment)
10. [Known Gotchas & Bugs](#10-known-gotchas--bugs)
11. [Areas for Future Improvement](#11-areas-for-future-improvement)

---

## 1. Project Layout

```
cloud server/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory, lifespan hooks, cryptg auto-verification, static mount
│   │   ├── config.py            # Settings class — reads .env via dotenv
│   │   ├── database.py          # SQLAlchemy engine, SessionLocal, Base
│   │   ├── models.py            # ORM models: User, FileRecord, FilePartRecord
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── auth.py              # JWT, bcrypt, Fernet session encryption
│   │   ├── routes/
│   │   │   ├── auth_routes.py   # /api/register /api/login /api/logout /api/me
│   │   │   ├── files.py         # /api/upload/* /api/files /api/download/* /api/files/* /api/share/*
│   │   │   └── telegram.py      # /api/telegram/qr-start /qr-status /2fa /disconnect
│   │   └── services/
│   │       ├── telegram_service.py  # Telethon core: QR login, channel management, client caching
│   │       └── parallel_transfer.py # DCSenderPool, pipelined upload/download, hardware crypto
│   ├── .env                     # Real secrets (gitignored)
│   ├── requirements.txt         # Dependencies (includes cryptg>=0.5.0)
│   ├── render.yaml              # Render deployment blueprint
│   └── tests/                   # Pytest test suite
├── frontend/
│   ├── index.html               # Thin redirect to /login.html
│   ├── login.html               # User login view
│   ├── register.html            # User registration view
│   ├── dashboard.html           # Main file manager UI
│   ├── setup_telegram.html      # QR code Telegram linking view
│   ├── share.html               # Public/Shared file download & import view
│   └── js/
│       ├── api.js               # Centralized fetch wrapper (apiFetch)
│       ├── config.js            # Environment-aware base URL config
│       ├── dashboard.js         # Upload pipeline, multi-volume slicing, UI updates
│       └── share.js             # Share view logic & background transfer trigger
├── .env.example
├── README.md
├── architecture.md
├── agent.md
├── brain.md                     # <- this file
├── decision.md
├── memory.md
├── rules.md
├── PRD.md
└── testing.md
```

---

## 2. Architecture Overview

```
Browser (Vercel)
  │
  │  HTTP (REST + Streaming /api/upload/stream)
  ▼
FastAPI Backend (Render)  ──── SQLAlchemy ───► PostgreSQL (Supabase)
  │                                                   │
  │                                              users, files, file_parts
  │
  │  Telethon MTProto + cryptg (AES-NI)
  │  Pipelined requests via DCSenderPool
  ▼
Telegram Data Centers (DC 1-5)
  └── Private Channel (CloudStorage_{tg_user_id} - dumb blob store)
```

**Key design decisions:**
1. **Telegram as a Dumb Blob Store:** Telegram stores raw document messages in a private channel created for each user.
2. **Zero Server Disk Footprint:** All transfers stream through memory without touching local storage or disk.
3. **Database Stores Only Metadata:** Supabase PostgreSQL stores file metadata, ownership, sharing tokens, and ordered Telegram message IDs.
4. **Hardware-Accelerated Cryptography:** `cryptg` utilizes CPU AES-NI instructions for native AES-IGE encryption, replacing slow pure Python `pyaes`.
5. **Single-Socket MTProto Pipelining:** Avoids opening multiple raw TCP sockets with the same `auth_key`, preventing Telegram's `AuthKeyDuplicatedError` while achieving full network throughput.

---

## 3. Database Schema

### `users`
| Column | Type | Notes |
|---|---|---|
| id | INT PK | Auto-increment primary key |
| name | VARCHAR(50) | User display name |
| email | VARCHAR(255) UNIQUE | Login identifier & JWT subject |
| password | VARCHAR(255) | bcrypt hash via passlib |
| telegram_phone | VARCHAR(50) | Nullable |
| telegram_user_id | VARCHAR(50) | Telegram numeric UID |
| telegram_session | VARCHAR(1000) | Fernet-encrypted Telethon StringSession |
| channel_id | VARCHAR(50) | Raw Telegram storage channel ID (without `-100` prefix) |
| created_at | DATETIME | Timestamp of creation (`server_default=func.now()`) |

*Note:* `is_telegram_connected` is an ORM `@property` returning `bool(telegram_session)`.

### `files`
| Column | Type | Notes |
|---|---|---|
| id | INT PK | Auto-increment primary key |
| user_id | INT FK users.id | Owner reference |
| original_name | VARCHAR(255) | Sanitized original filename |
| telegram_file_id | VARCHAR(255) | Nullable |
| file_size | BIGINT | Total file size in bytes (supports >2 GB) |
| mime_type | VARCHAR(100) | MIME type for HTTP Content-Type headers |
| share_token | VARCHAR(64) | Nullable, unique token for public sharing |
| is_shared | BOOLEAN | Boolean toggle for share access |
| uploaded_at | DATETIME | Timestamp of upload |

### `file_parts`
| Column | Type | Notes |
|---|---|---|
| id | INT PK | Auto-increment primary key |
| file_id | INT FK files.id | CASCADE delete relationship |
| part_index | INT | 0-based volume index |
| telegram_message_id | INT | Telegram message ID inside storage channel |
| channel_id | VARCHAR(50) | Target channel ID for this part |

*Design Rule:* Files <= 1.90 GB have exactly 1 `FilePartRecord`. Files > 1.90 GB are split into multiple sequential volumes, each represented by a `FilePartRecord` with an incrementing `part_index`.

---

## 4. Authentication & Security

### JWT (JSON Web Tokens)
- **Algorithm:** HS256 with `JWT_SECRET_KEY`.
- **Extended Token Lifetime:** `ACCESS_TOKEN_EXPIRE_MINUTES=43200` (30 days). Prevents HTTP 401 token expiration errors during lengthy multi-gigabyte uploads or downloads.
- **Delivery:** Delivered as an `httpOnly` cookie (`access_token`) on login, and accepted via standard `Authorization: Bearer <token>` headers for cross-origin or programmatic clients.
- **Cookie Security:** `secure=True` automatically enabled when `ENVIRONMENT=production`.

### Telegram Session Encryption
- Telethon `StringSession` strings are encrypted with Fernet prior to database persistence.
- The encryption key is derived deterministically: `base64url(sha256(JWT_SECRET_KEY))`.
- **Idempotency Guard:** Strings already starting with `"gAAAAA"` are recognized as ciphertext and not re-encrypted. Legacy unencrypted strings are supported seamlessly.

### Telegram Session Expiry & Revocation Handling
`handle_telegram_error()` in `backend/app/routes/files.py` intercepts Telethon session exceptions:
- `AuthKeyDuplicatedError` (triggered if duplicate raw sessions were opened)
- `AuthKeyUnregisteredError`
- `SessionExpiredError`
- `SessionRevokedError`
- `UserDeactivatedError`, `UserDeactivatedBanError`, `UnauthorizedError`

**Recovery Action:** It safely nulls `telegram_session` in PostgreSQL so the user can re-link via QR code, but **preserves `channel_id` and `telegram_user_id`** to prevent orphaning uploaded files.

---

## 5. Upload Flow (Streaming & Pipelined Parallelism)

```
Browser -> POST /api/upload/stream (Raw Body) -> Backend -> Telegram DC
```

### 1. Volume Slicing (Frontend)
Telegram imposes a hard 2 GB limit per message. The frontend slices files exceeding ~1.90 GB into sequential volumes (aligned to 3,890 parts of 512 KB = 2,039,480,320 bytes).

### 2. Direct HTTP Streaming
The browser streams raw bytes via `XMLHttpRequest.send(volumeBlob)` to `/api/upload/stream?filename=...&filesize=...`. No multipart boundary overhead or local disk buffering.

### 3. Hardware AES-NI Acceleration (`cryptg`)
When sending parts via MTProto, Telethon invokes `cryptg` to encrypt 512 KB chunks using native CPU AES-NI instructions. Cryptographic operations take fractions of a millisecond instead of hundreds of milliseconds per chunk.

### 4. Asynchronous Request Pipelining (`DCSenderPool`)
- Uploads initialize `upload_stream_parallel` in `parallel_transfer.py`.
- Instead of opening multiple TCP sockets (which causes session bans), `DCSenderPool` maintains an authenticated connection to the storage DC and pipelines up to `WORKERS_PER_TRANSFER` (default: 4) concurrent asynchronous `SaveBigFilePartRequest` calls over that connection.
- A producer coroutine reads incoming HTTP stream chunks and places them in an `asyncio.Queue` of 512 KB parts.
- 4 concurrent consumer workers pull from the queue and send them to Telegram, saturating network bandwidth.
- Clean cancellation in `finally` blocks ensures no orphaned background tasks.

### 5. Document Message Assembly
Once all 512 KB parts are uploaded, the backend issues `SendMediaRequest` with an `InputMediaUploadedDocument`, producing a message in the user's private channel.

### 6. Atomic DB Completion
Frontend issues `POST /api/upload/complete` containing the array of message IDs, creating the `FileRecord` and sequential `FilePartRecord` entries.

---

## 6. Download Flow (Prefetched Streaming)

```
GET /api/download/{file_id}
  │
  ├─ Authenticate user and fetch FileRecord + FilePartRecord[]
  ├─ Return StreamingResponse(combined_stream())
       │
       └─ For each FilePartRecord:
            Calls download_file_parallel() via DCSenderPool
            Prefetches 512KB chunks via worker queue
            Streams contiguous byte chunks to HTTP client
```

- Multi-volume files are transparently chained in memory into a seamless single-file download stream for the browser.
- High-throughput prefetching guarantees the browser receives data as fast as the Telegram DC can serve it.

---

## 7. Telegram Connection Management & DCSenderPool

### Channel Entity Resolution
- Stored in the database as an integer string (e.g. `4341384088`).
- Telegram's API requires supergroup/channel IDs to be prefixed with `-100` (e.g. `-1004341384088`).
- `get_resolved_entity()` automatically converts positive IDs to `-100...` and handles access hash resolution caching.

### Single-Socket Pipelining vs. Multi-Socket Sessions
- **Why Multi-Socket Fails:** In MTProto, session keys (`auth_key`) are bound to connection states. Opening multiple raw TCP connections with the exact same `auth_key` triggers Telegram's security heuristics, resulting in `AuthKeyDuplicatedError` and session revocation.
- **How DCSenderPool Succeeds:** `DCSenderPool` exports authorization if the media is on a different DC, establishes a dedicated connection for that DC, and pipelines multiple concurrent RPC requests asynchronously over that single connection.

### QR Login Flow
1. `POST /api/telegram/qr-start`: Initializes a fresh `TelegramClient`, requests a QR login URL, and registers a background monitoring task in `pending_logins`.
2. `GET /api/telegram/qr-status`: Frontend polls login status.
3. On scan: checks if account matches existing ID, verifies/creates the private `CloudStorage_{tg_user_id}` channel, encrypts the session, and saves to PostgreSQL.
4. `POST /api/telegram/2fa`: Submits 2FA password if user has cloud password enabled.

---

## 8. Frontend Pages & Architecture

- **`dashboard.html` / `dashboard.js`:** Drag-and-drop file upload, real-time speed/ETA tracker, multi-volume slicing, file table, download, delete, and share actions.
- **`setup_telegram.html`:** Dynamic QR code display and status polling with account mismatch recovery dialogs.
- **`share.html` / `share.js`:** Public/shared file access. Allows non-owners to download the file directly or use "Save to my Cloud" (background server-side copy).
- **`js/api.js`:** Universal `apiFetch` wrapper providing centralized token management, base URL resolution, and unified error handling.
- **`js/config.js`:** Dynamic environment configuration (`localhost:8000` vs. production Render URL).

---

## 9. Config & Environment

File: `backend/app/config.py` (`Settings` class)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | (required) | Supabase PostgreSQL connection string (Transaction Pooler port 6543) |
| `JWT_SECRET_KEY` | (required) | Secret key for JWT signing and Fernet key derivation |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `43200` | Token lifetime (30 days) |
| `TG_API_ID` | (required) | Telegram API ID from my.telegram.org |
| `TG_API_HASH` | (required) | Telegram API Hash from my.telegram.org |
| `WORKERS_PER_TRANSFER` | `4` | Number of concurrent pipelined transfer workers |
| `ENVIRONMENT` | `development` | Set to `production` for secure cookies |

---

## 10. Known Gotchas & Bugs

### 1. `cryptg` Absence Degradation
Without `cryptg`, Telethon silently falls back to pure Python `pyaes`. Upload speeds drop to ~1 MB/s and CPU usage spikes to 100%. `main.py` solves this via automated startup verification (`ensure_hardware_acceleration()`).

### 2. Multi-Socket `AuthKeyDuplicatedError`
Never attempt to open multiple raw TCP connections with the same session string. MTProto concurrency must be achieved via asynchronous request pipelining over a single connection.

### 3. Server Reloads Clear `pending_logins`
The QR login state dictionary is held in memory. Hot-reloads during local development clear pending logins, requiring the user to refresh and re-scan the QR code.

### 4. Database Pre-Ping
To prevent idle connection timeouts from Supabase's transaction pooler, SQLAlchemy is configured with `pool_pre_ping=True` and `pool_recycle=3600`.

---

## 11. Areas for Future Improvement

1. **Volume-Level Upload Resume:** If an upload fails mid-transfer, allow resuming the specific 512KB chunk or volume rather than restarting the entire file.
2. **Native Download Progress:** Include `Content-Length: <file_size>` in `StreamingResponse` so browsers display an estimated completion time.
3. **Persistent QR State:** Move `pending_logins` to a Redis store or database table to survive server restarts.
4. **Endpoint Rate Limiting:** Add slowapi rate limiting to `/api/register` and `/api/login`.
