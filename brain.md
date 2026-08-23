# brain.md — Developer Reference

Deep-dive technical reference for the Telegram Cloud Storage project. Covers the full architecture, data flows, security model, known gotchas, and areas for future improvement.

---

## Table of Contents

1. [Project Layout](#1-project-layout)
2. [Architecture Overview](#2-architecture-overview)
3. [Database Schema](#3-database-schema)
4. [Authentication & Security](#4-authentication--security)
5. [Upload Flow](#5-upload-flow)
6. [Download Flow](#6-download-flow)
7. [Telegram Connection Management](#7-telegram-connection-management)
8. [Frontend Pages & JS](#8-frontend-pages--js)
9. [Config & Environment](#9-config--environment)
10. [Known Gotchas & Bugs](#10-known-gotchas--bugs)
11. [Areas for Future Improvement](#11-areas-for-future-improvement)

---

## 1. Project Layout

```
cloud server/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory, router registration, static mount
│   │   ├── config.py            # Settings class — reads .env via dotenv
│   │   ├── database.py          # SQLAlchemy engine, SessionLocal, Base
│   │   ├── models.py            # ORM models: User, FileRecord, FilePartRecord
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── auth.py              # JWT, bcrypt, Fernet session encryption
│   │   ├── routes/
│   │   │   ├── auth_routes.py   # /api/register /api/login /api/logout /api/me
│   │   │   ├── files.py         # /api/upload/* /api/files /api/download/* /api/files/*
│   │   │   └── telegram.py      # /api/telegram/qr-start /qr-status /2fa
│   │   └── services/
│   │       └── telegram_service.py  # All Telethon logic: QR login, upload pool, download
│   ├── .env                     # Real secrets (gitignored)
│   ├── requirements.txt
│   └── venv/
├── frontend/
│   ├── index.html               # Thin redirect to /login.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html           # Main file manager UI
│   ├── setup_telegram.html      # QR code linking flow
│   └── js/
│       └── dashboard.js         # Upload pipeline, file listing, download trigger
├── .env.example
├── README.md
└── brain.md                     # <- this file
```

---

## 2. Architecture Overview

```
Browser
  |
  |  HTTP (cookie auth)
  v
FastAPI (Uvicorn)  ---- SQLAlchemy ---> MySQL (cloud_db)
  |                        |
  |                   users, files, file_parts
  |
  |  Telethon (MTProto)
  v
Telegram API
  +-- Private Channel (one per user, stores actual file bytes as messages)
```

**Key design decision:** Telegram is used as a dumb blob store. Files are split into <=1.9 GB "volumes", each uploaded as a single Telegram document message. MySQL only stores message IDs + metadata — never file bytes.

---

## 3. Database Schema

### users
| Column | Type | Notes |
|---|---|---|
| id | INT PK | Auto-increment |
| name | VARCHAR(50) | Alphanumeric + underscore only |
| email | VARCHAR(255) UNIQUE | Used as JWT subject (sub claim) |
| password | VARCHAR(255) | bcrypt hash |
| telegram_phone | VARCHAR(50) | Nullable; not actively used |
| telegram_user_id | VARCHAR(50) | Telegram account numeric UID |
| telegram_session | VARCHAR(1000) | Fernet-encrypted Telethon StringSession |
| channel_id | VARCHAR(50) | Raw Telegram channel ID (no -100 prefix) |
| created_at | DATETIME | server_default=func.now() |

Note: `is_telegram_connected` is a Python @property — not a DB column. Returns bool(telegram_session).

### files
| Column | Type | Notes |
|---|---|---|
| id | INT PK | |
| user_id | INT FK users.id | |
| original_name | VARCHAR(255) | Original filename as uploaded |
| telegram_file_id | VARCHAR(255) | Nullable — currently unused |
| file_size | BIGINT | Supports >2 GB |
| mime_type | VARCHAR(100) | Used for Content-Type header on download |
| uploaded_at | DATETIME | server_default=func.now() |

### file_parts
| Column | Type | Notes |
|---|---|---|
| id | INT PK | |
| file_id | INT FK files.id | CASCADE delete |
| part_index | INT | 0-based; ordering of volumes |
| telegram_message_id | INT | Telegram message ID in user's channel |

A single-volume file (<1.9 GB) has exactly ONE FilePartRecord. Multi-volume files have one record per volume.

---

## 4. Authentication & Security

### JWT
- Algorithm: HS256 with JWT_SECRET_KEY
- Delivered as httpOnly cookie named `access_token` on login
- Also accepted as Bearer token in Authorization header (for API clients / curl)
- Cookie secure=True only when ENVIRONMENT=production
- `get_current_user` FastAPI dependency protects all routes that need auth

### Password Rules (enforced in UserCreate Pydantic schema)
- Min 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- Stored as bcrypt hash via passlib

### Telegram Session Encryption
- Telethon StringSession strings encrypted with Fernet before DB storage
- Fernet key derived as: base64url(sha256(JWT_SECRET_KEY))
- Double-encryption guard: strings already starting with "gAAAAA" are returned as-is
- Backward compat: strings NOT starting with "gAAAAA" treated as legacy unencrypted sessions (returned as-is from decrypt)

### Telegram Session Expiry Handling
handle_telegram_error() in files.py catches these Telethon error names:
  AuthKeyUnregisteredError, SessionExpiredError, SessionRevokedError,
  UserDeactivatedError, UserDeactivatedBanError, UnauthorizedError
On match: nulls telegram_session + channel_id in DB, returns HTTP 401.

---

## 5. Upload Flow

### End-to-end sequence

```
Browser picks file
  |
  |  JS splits file into volumes (<=1.9 GB each)
  |
  +-> For each volume:
  |     |
  |     |  JS splits volume into chunks (e.g. 5 MB each)
  |     |  JS generates random file_id (safe int53) for this volume
  |     |  JS computes total_parts = ceil(volume_size / 524288)
  |     |
  |     +-> POST /api/upload/chunk  [repeated per chunk]
  |     |     form fields: file_id, start_part_index, total_parts, is_big
  |     |     file field:  raw binary chunk
  |     |     backend: _get_upload_client(file_id) -> reuse or create TelegramClient
  |     |     backend: splits chunk into 512KB pieces, sends sequentially
  |     |
  |     +-> POST /api/upload/finalize_volume
  |           body: { file_id, total_parts, filename, is_big }
  |           backend: sends InputFileBig/InputFile to channel as document message
  |           backend: disconnects + removes client from _upload_clients pool
  |           response: { message_id: <int> }
  |
  +-> POST /api/upload/complete
        body: { filename, file_size, mime_type, message_ids: [id1, id2, ...] }
        backend: creates FileRecord + FilePartRecord(s) in MySQL
        response: FileOut
```

### is_big flag
- True when volume has more than 10 Telegram parts (>~5 MB)
- Telegram API requires SaveBigFilePartRequest for files >10 MB; SaveFilePartRequest for smaller
- Frontend computes and passes this correctly

### Persistent upload client pool
```python
# telegram_service.py module-level
_upload_clients: dict[int, dict] = {}
# key   = file_id (int)
# value = {"client": TelegramClient, "lock": asyncio.Lock}
```

Lifecycle:
1. First chunk for file_id -> _get_upload_client() creates + connects TelegramClient, stores in pool
2. Subsequent chunks for same file_id -> reuse existing connected client (no reconnect)
3. finalize_telegram_upload() -> sends file to channel, then disconnects + pops from pool

Lock per entry ensures sequential part sending even if somehow two requests for same file_id arrive concurrently.

WARNING: If finalize is never called (abandoned upload), the client leaks indefinitely.

---

## 6. Download Flow

```
GET /api/download/{file_id}
  |
  +- Auth check (current_user)
  +- Query FileRecord by (file_id, user_id)
  +- Query FilePartRecord[] ordered by part_index
  +- Build message_ids = [part.telegram_message_id for part in parts]
  |
  +- Return StreamingResponse(combined_stream())
       |
       combined_stream() async generator:
         calls download_multiple_messages_stream(session, channel_id, message_ids)
           |
           +- Connect one TelegramClient
           +- For each message_id:
           |    get_messages(entity, ids=msg_id)
           |    iter_download(message.media) -> yield chunks
           +- Disconnect after all parts done
```

Response headers:
- Content-Disposition: attachment; filename*=UTF-8''<url-encoded-filename>
- Content-Type: <stored mime_type>
- NO Content-Length (streaming; browser can't show progress bar)

---

## 7. Telegram Connection Management

### Channel ID -100 prefix quirk
Stored as plain int in DB (e.g. 1234567890).
Telethon internally needs -100 prefix (e.g. -1001234567890).
get_resolved_entity() handles this:
```python
if entity_id > 0:
    entity_id = int(f"-100{entity_id}")
```
If get_input_entity raises "Could not find the input entity" (missing access hash cache),
get_dialogs(limit=50) is called first to populate the session cache, then retried.

### QR Login state machine
```
POST /api/telegram/qr-start
  -> new TelegramClient + connect() + qr_login()
  -> asyncio background task: waits for user to scan
  -> success: create private channel, store in pending_logins[token_id]

GET /api/telegram/qr-status?token=<uuid>
  -> read pending_logins[token]
  -> on success: encrypt session, write to DB, return 200

POST /api/telegram/2fa  (triggered if status == "2fa_required")
  -> client.sign_in(password=...) on still-open client
  -> same channel creation + DB save flow
```

IMPORTANT: pending_logins is module-level dict. Does NOT survive server restart.
Under --reload, any file save restarts the worker and clears all pending logins.

---

## 8. Frontend Pages & JS

| File | Role |
|---|---|
| index.html | Redirects to /login.html |
| login.html | Email + password login form |
| register.html | Registration form |
| setup_telegram.html | QR code display, status polling, 2FA input |
| dashboard.html | File list table, upload button, download/delete |
| js/dashboard.js | Upload pipeline logic, API calls, UI updates |

Static file serving: FastAPI mounts `frontend/` at `/` via StaticFiles(html=True).
API routes (/api/*) are registered before the static mount and take priority.
No Node.js, no bundler, no build step.

---

## 9. Config & Environment

File: backend/app/config.py — class Settings

| Variable | Default | Description |
|---|---|---|
| DB_HOST | localhost | MySQL host |
| DB_PORT | 3307 | Non-standard port — check your MySQL install |
| DB_USER | root | MySQL user |
| DB_PASSWORD | (empty) | MySQL password |
| DB_NAME | cloud_db | Must be created manually before first run |
| JWT_SECRET_KEY | (required) | Also derives the Fernet encryption key |
| JWT_ALGORITHM | HS256 | JWT signing algorithm |
| ACCESS_TOKEN_EXPIRE_MINUTES | 60 | Token lifetime |
| TG_API_ID | 0 | From my.telegram.org |
| TG_API_HASH | (empty) | From my.telegram.org |
| ENVIRONMENT | development | Set to "production" for secure cookies |

DATABASE_URL property format:
  mysql+mysqlconnector://root@localhost:3307/cloud_db

SQLAlchemy engine options:
  pool_pre_ping=True    -- avoids "MySQL server has gone away" on idle connections
  pool_recycle=3600     -- recycles connections older than 1 hour

---

## 10. Known Gotchas & Bugs

### Upload client pool leak
Abandoned uploads (browser closed mid-upload, network drop) never trigger finalize_telegram_upload.
The TelegramClient for that file_id stays in _upload_clients forever.
No cleanup mechanism exists currently.

### _ensure_database_exists() is commented out
database.py has a utility that auto-creates cloud_db, but it's disabled (commented out).
The database must be created manually with: CREATE DATABASE IF NOT EXISTS cloud_db;

### pending_logins does not survive restarts
Any server restart (including --reload hot-reloads triggered by file saves) clears pending_logins.
Users mid-QR-scan must start over.

### telegram_file_id column is unused
FileRecord has a telegram_file_id column that is never written to.
The current design uses telegram_message_id in FilePartRecord instead.

### No Content-Length header on downloads
StreamingResponse with an async generator has no known total size.
The browser shows indeterminate download progress. file_size is in the DB and could be sent as a header.

### is_telegram_connected assignment is a no-op
handle_telegram_error() in files.py sets current_user.is_telegram_connected = False.
is_telegram_connected is a @property with no setter, so this silently does nothing.
The real fix (telegram_session = None) is already done on the previous line.

---

## 11. Areas for Future Improvement

### Upload pool TTL cleanup
Run an asyncio background task that evicts entries from _upload_clients idle for >5 minutes.
Prevents connection leaks from abandoned uploads.

### Content-Length on downloads
```python
headers["Content-Length"] = str(file_record.file_size)
```
Enables native browser download progress bars. file_size is already stored.

### Persist QR login state across restarts
Move pending_logins to Redis or a temporary DB table.
Critical for production where restarts must not invalidate ongoing logins.

### Per-chunk retry without full restart
Frontend should retry only the failed chunk, not restart the entire file.
The server-side pool supports this already (connection stays open between chunks).

### Rate limiting on auth endpoints
/api/register and /api/login have no throttling.
Add slowapi (FastAPI rate limiter) to prevent brute-force attacks.

### JWT refresh / sliding expiry
No token refresh mechanism exists. When the token expires, the user is silently logged out.
Add a refresh endpoint or sliding expiry window.

### Remove unused telegram_file_id column
Either populate it or remove it from the schema to avoid confusion.

### Fix is_telegram_connected property setter
Add a proper @is_telegram_connected.setter or remove the assignment in handle_telegram_error()
since setting telegram_session = None already achieves the same effect.
