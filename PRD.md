# Product Requirements Document (PRD)

## Project Overview
The "Cloud Server" is a high-performance web cloud storage system that leverages the Telegram API (via Telethon) as an unlimited, cost-free object storage backend. User files are stored as document messages within a dedicated private Telegram channel, while a PostgreSQL (Supabase) database manages structural metadata, user authentication, and file indexing.

---

## 1. System Goals & Performance Targets

- **Zero-Cost Object Storage:** Utilize Telegram's API infrastructure for file storage without incurring commercial cloud storage costs (S3, GCS, Azure).
- **Maximum Transfer Throughput:** Attain near-line-rate broadband speeds (~4 MB/s+) by leveraging hardware-accelerated AES-NI cryptography (`cryptg`) and asynchronous MTProto request pipelining (`DCSenderPool`).
- **Zero Local Footprint:** Stream all incoming and outgoing bytes directly through memory without buffering files to local server disk.
- **Bypass 2 GB File Limits:** Seamlessly support arbitrary file sizes (tested up to 5 GB+) through client-side volume slicing and contiguous server-side reassembly.
- **Enterprise-Grade Session Stability:** Prevent session invalidations (`AuthKeyDuplicatedError`) and avoid mid-upload 401 token expirations through 30-day JWT persistence.

---

## 2. Core Functional Requirements

### 2.1 User Authentication & Account Linking
- **Local Account Management:** Email and password registration/login with bcrypt password hashing and 30-day JWT cookies/bearer tokens (`ACCESS_TOKEN_EXPIRE_MINUTES=43200`).
- **Telegram Account Integration:**
  - Secure linking via interactive QR code scanning (or phone number fallback with 2FA password support).
  - Fernet encryption for Telethon `StringSession` strings at rest.
  - Automatic creation and binding of a private storage channel (`CloudStorage_{tg_user_id}`).
  - Automatic detection and recovery for revoked Telegram sessions, preserving existing file and channel bindings.

### 2.2 File Management & High-Speed Transfers
- **Direct Stream Uploads:**
  - Files <= 1.90 GB stream directly into the user's storage channel via `/api/upload/stream`.
  - Files > 1.90 GB are partitioned client-side into ~1.90 GB sequential volumes and uploaded as distinct document messages.
  - Hardware-accelerated AES-IGE encryption via `cryptg` (AES-NI).
  - Concurrent chunk pipelining over authenticated DC connection (512 KB chunks).
- **Streaming Downloads:**
  - Contiguous streaming of multi-part files via `/api/download/{file_id}` without disk caching.
  - Multi-worker chunk prefetching to saturate download bandwidth.
- **File Deletion:**
  - Deletes database records and purges the corresponding document messages from the Telegram storage channel.

### 2.3 Peer-to-Peer File Sharing
- **Share Link Generation:** Generate unique, secure share tokens for any uploaded file (`/share.html?token=...`).
- **Direct Download for Recipients:** External visitors can download shared files directly without logging in.
- **"Save to my Cloud" Import:** Authenticated recipients can clone shared files directly into their own private Telegram storage channel via asynchronous server-side background tasks (`transfer_file_between_users`), transferring true ownership without downloading to their device.

### 2.4 User Interface & Dashboard
- **Glassmorphism UI:** Modern dark glassmorphic dashboard built in Vanilla JS and Tailwind CSS.
- **Live Transfer Metrics:** Real-time transfer speed calculation (MB/s), percentage progress bars, and accurate dynamic ETA displays.
- **Search & Filter:** Instant in-memory search and filtering across the user's file library.

---

## 3. Technical & Non-Functional Requirements

| Layer | Specification |
|---|---|
| Frontend | HTML5, Vanilla JavaScript (ES6+), Tailwind CSS (CDN). Hosted on Vercel. |
| Backend | Python 3.10+, FastAPI, Uvicorn ASGI server. Hosted on Render. |
| Cryptography | `cryptg` (Native C AES-NI extension for AES-IGE), `cryptography` (Fernet). |
| Database | PostgreSQL (Supabase) via SQLAlchemy ORM (Transaction Pooler). |
| MTProto Client | Telethon with `DCSenderPool` request pipelining. |
| Concurrency | Single-connection pipelining per DC; zero duplicate auth keys. |
| API Communication | Centralized `apiFetch` wrapper with dynamic base URL resolution and CORS support. |
