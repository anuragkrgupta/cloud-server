# Telegram Cloud Storage Web App

A cloud storage web application that uses **Telegram** as an unlimited backend storage layer. Uploaded files are stored inside a private Telegram channel created automatically for each user, while metadata is managed locally via a **PostgreSQL (Supabase)** database.

Files of any size are supported by automatically chunking, streaming, and reassembling them across Telegram messages — both on upload and download — with no data ever written to the server's disk.

## Key Features

### Authentication & Security
- **JWT Authentication** — Secure tokens with 30-day persistence (`ACCESS_TOKEN_EXPIRE_MINUTES=43200`) so multi-gigabyte transfers are never interrupted.
- **QR Code & Phone Telegram Login** — Link Telegram accounts seamlessly with QR code scanning or phone number verification (with 2FA support).
- **AES/Fernet Encryption** — Telegram session strings are encrypted at rest using `JWT_SECRET_KEY`.
- **Automatic Session Recovery** — Proactively handles and clears revoked Telegram auth keys (`AuthKeyDuplicatedError`, `SessionExpiredError`).
- **PostgreSQL (Supabase) Database** — `users`, `files`, and `file_parts` tables managed via SQLAlchemy ORM.

### High-Speed Uploads
- **Hardware-Accelerated AES-NI (`cryptg`)** — Native C-accelerated AES-IGE encryption provides a **400x cryptographic speedup** over pure Python `pyaes`, dramatically reducing CPU load and unlocking full network bandwidth.
- **Auto Hardware Acceleration Verification** — Server automatically verifies and self-installs `cryptg` on startup across every device and OS.
- **Asynchronous Parallel Pipelining** — Dispatches 512 KB chunks concurrently using round-robin task pipelining over authenticated DC connections, maxing out transfer throughput without triggering Telegram multi-socket collision bans.
- **Bypasses 2GB limit** — Files of any size (tested up to 5GB+) are automatically divided into clean ~1.90 GB volumes and assembled seamlessly.
- **Direct Stream Uploads** — Frontend streams raw bytes directly to `/api/upload/stream`, eliminating local disk buffering.
- **Zero Local Footprint** — Nothing is written to the server's disk during upload or download.

### Downloads
- **Parallel Chunk Streaming** — Multi-worker chunk prefetching ensures streaming download response rates are saturated.
- **Contiguous Multi-Volume Reassembly** — Multi-volume files are transparently chained into a single seamless download stream for the browser.

### Frontend
- Decoupled Vanilla HTML, JavaScript, and Tailwind CSS.
- Hosted on Vercel with SPA routing via `vercel.json`.
- Centralized `api.js` client with environment-aware API URL resolution and auth handling.
- Dark glassmorphism UI with real-time transfer speed tracker, percent progress, and ETA calculations.

---

## Architecture

| Layer | Technology |
|---|---|
| Frontend | HTML5, Vanilla JS, Tailwind CSS (CDN) |
| Backend | Python 3.10+, FastAPI, Uvicorn (ASGI) |
| Cryptography | `cryptg` (Hardware AES-NI), `cryptography` (Fernet) |
| Database | PostgreSQL (Supabase) via SQLAlchemy ORM |
| Telegram Client | Telethon (AsyncIO MTProto) |

---

## Prerequisites

- Python 3.10+
- A Supabase Project (for the PostgreSQL database)
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)

---

## Installation & Setup

### 1. Virtual environment

```bash
cd backend
python -m venv venv
.\venv\Scripts\activate   # Windows
source venv/bin/activate  # Mac/Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure `.env`

Create `backend/.env` from `.env.example`:

```env
# Supabase PostgreSQL Connection String (Transaction Pooler)
DATABASE_URL="postgresql://postgres:[your_password]@aws-0-[region].pooler.supabase.com:6543/postgres"

JWT_SECRET_KEY=your_very_long_random_secret_string
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200

TG_API_ID=your_api_id
TG_API_HASH=your_api_hash
WORKERS_PER_TRANSFER=4

ENVIRONMENT=development
```

### 4. Database Setup

Your database is hosted on Supabase. 
All tables are created automatically by SQLAlchemy on first startup when it connects via your `DATABASE_URL`.

### 5. Starting the Server

Every time you want to start or resume working on your cloud server locally, follow these exact steps:

**Step 1: Start the Python Backend**
Open a terminal in the `backend` directory, activate your virtual environment, and start the Uvicorn server:
```bash
cd backend
.\venv\Scripts\activate   # For Windows
# source venv/bin/activate  # For Mac/Linux

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Step 3: Access the App**
Open your browser and navigate to:
**http://localhost:8000**

*(No Node.js, npm, or frontend build steps are required. The HTML/JS is served instantly by FastAPI).*

---

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/register` | Register a new user |
| `POST` | `/api/login` | Login, receive JWT cookie |
| `POST` | `/api/logout` | Clear session |
| `GET` | `/api/me` | Current user info |
| `POST` | `/api/telegram/qr-start` | Start QR login flow |
| `GET` | `/api/telegram/qr-status` | Poll QR login status |
| `POST` | `/api/telegram/2fa` | Submit 2FA password |
| `POST` | `/api/telegram/override-mismatch` | Override account mismatch and create a new channel |
| `POST` | `/api/telegram/disconnect` | Clear Telegram session |
| `POST` | `/api/upload/stream` | Stream raw file bytes |
| `POST` | `/api/upload/complete` | Save file record to DB |
| `GET` | `/api/files` | List files |
| `GET` | `/api/download/{file_id}` | Stream download |
| `DELETE` | `/api/files/{file_id}` | Delete file |

Interactive docs: **http://localhost:8000/docs**

---

## Deployment Notes

- Use a long random `JWT_SECRET_KEY` in production — it encrypts Telegram sessions.
- Run behind **Nginx** with **HTTPS**.
- Set `ENVIRONMENT=production` to enable secure cookies.
- Telegram transfer speed is bounded by MTProto limits — this cannot be bypassed.
