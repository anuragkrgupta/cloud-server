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

### 4. Storage Backend (Telegram)
- **Library:** Telethon (Python).
- **Architecture:** 
  - Each user gets a dedicated private channel (`CloudStorage_{tg_user_id}`).
  - Files are streamed directly to/from Telegram using a `DCSenderPool` which opens multiple `MTProtoSender` connections (e.g. 4-8 workers). This overcomes single-connection limits imposed by Telegram.
  - Large files are uploaded via `SaveBigFilePartRequest` and re-assembled by Telegram.

## Data Flow (Parallel Upload)
1. User selects a file on the frontend.
2. Frontend sends a `multipart/form-data` POST request to the backend.
3. Backend creates a pool of authenticated MTProto connections (`DCSenderPool`).
4. The file stream is consumed, chunked (512KB), and dispatched round-robin to the connection pool.
5. Telegram returns a `message_id` for the assembled document.
6. Backend stores file metadata and `FilePartRecord` in the PostgreSQL (Supabase) database.
7. Backend returns success response to the frontend.

## Data Flow (File Transfer Between Users)
1. User A shares a file, generating a `share_token`.
2. User B clicks the shared link and chooses to save the file.
3. Backend starts an asynchronous background task (`transfer_file_between_users`).
4. The background task fetches parts from User A's channel and streams them directly into User B's channel in parallel.
5. Upon completion, User B receives a new `FileRecord` referencing the new message IDs.
