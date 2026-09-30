# System Architecture

## Overview
The Cloud Server utilizes a decoupled architecture where the frontend and backend are hosted on separate platforms but communicate via REST APIs. Telegram serves as the underlying file storage infrastructure, utilizing multi-connection parallel uploads/downloads for maximum throughput.

## Components

### 1. Frontend (Vercel)
- **Technology:** HTML5, CSS3, Vanilla JavaScript.
- **Routing:** Handled via `vercel.json` for seamless SPA-like navigation and static asset serving.
- **API Communication:** A centralized `apiFetch` module (`frontend/js/api.js`) abstracts away the complexities of cross-origin requests, authentication headers, and dynamic base URL resolution (`config.js`).
- **QR Authentication:** Uses polling to verify Telegram QR Code login completion.

### 2. Backend (Render)
- **Technology:** Python (FastAPI).
- **Server:** Uvicorn running ASGI.
- **Concurrency:** Fully asynchronous handling of requests, parallel chunk streaming, and background tasks (for inter-user file transfers).
- **Lifecycle Management:** Uses FastAPI `lifespan` context managers to gracefully handle database connections and disconnect Telegram clients on shutdown.

### 3. Database (PostgreSQL (Supabase))
- **Models:**
  - `User`: Stores credentials, Telegram session string, and designated `channel_id`.
  - `FileRecord`: Stores file metadata (original name, size, sharing token, shared state).
  - `FilePartRecord`: Tracks multiple Telegram messages for a single file, supporting large files >2GB split across chunks.

### 4. Storage Backend (Telegram) & Cryptographic Acceleration
- **Library:** Telethon (Python, AsyncIO MTProto).
- **Hardware Acceleration:** Native `cryptg` C extension utilizing CPU AES-NI instructions for hardware-accelerated AES-IGE encryption/decryption (400x cryptographic speedup over pure Python `pyaes`). Auto-verified on startup.
- **Connection & Session Architecture:** 
  - Each user gets a dedicated private storage channel (`CloudStorage_{tg_user_id}`).
  - Files are streamed to/from Telegram using `DCSenderPool`, which pipelines multiple concurrent requests asynchronously (default: 4 workers) over an authenticated session.
  - Avoids opening multiple raw TCP sockets with the identical `auth_key`, strictly protecting user accounts from Telegram's `AuthKeyDuplicatedError` / session revocation.
  - For cross-DC file transfers, `DCSenderPool` exports authorization and initializes a dedicated connection to the media's host DC.
  - Large files (>10MB) utilize `SaveBigFilePartRequest` (512KB chunks).
  - Multi-gigabyte files exceeding Telegram's single-document limit are automatically split by the frontend into sequential volumes (~1.90 GB each, aligned to 3,890 parts) and assembled into a contiguous document set.

## Data Flow (High-Speed Stream Upload)
1. User selects a file on the frontend (e.g. 5GB file).
2. The frontend calculates volume slices (e.g. 3 volumes of max 1.90 GB each).
3. The browser streams raw binary data directly via HTTP POST to `/api/upload/stream?filename=...&filesize=...`.
4. The backend initializes `upload_stream_parallel` with `DCSenderPool`.
5. Incoming byte chunks are buffered into 512KB parts and encrypted at memory speeds via `cryptg` (hardware AES-NI).
6. 4 parts are dispatched in flight concurrently using asynchronous task pipelining to Telegram.
7. Upon completing each volume, Telegram returns a `message_id` for that document.
8. Once all volumes finish, the frontend sends `/api/upload/complete` with all `message_ids`.
9. The backend saves a parent `FileRecord` and sequential `FilePartRecord` entries in PostgreSQL (Supabase).
10. The file immediately appears in the user's dashboard.

## Data Flow (File Transfer Between Users)
1. User A shares a file, generating a secure `share_token`.
2. User B opens the shared link (`/share.html?token=...`) and selects "Save to my Cloud".
3. The backend initiates an asynchronous background task (`transfer_file_between_users`).
4. The background task fetches parts from User A's channel and streams them directly into User B's private channel in parallel.
5. Upon completion, User B receives a new `FileRecord` referencing the new message IDs without server disk I/O.
