# Telegram Cloud Storage Web App

A cloud storage web application that uses **Telegram** as an unlimited backend storage layer. Uploaded files are stored inside a private Telegram channel created automatically for each user, while metadata is managed locally via a **PostgreSQL (Supabase)** database.

Files of any size are supported by automatically chunking, streaming, and reassembling them across Telegram messages — both on upload and download — with no data ever written to the server's disk.

## Key Features

### Authentication & Security
- **JWT Authentication** — Secure tokens with configurable expiry (default 60 min).
- **QR Code Telegram Login** — Links a Telegram account via QR scan. Supports 2FA.
- **AES/Fernet Encryption** — Telegram session strings are encrypted at rest using `JWT_SECRET_KEY`.
- **PostgreSQL (Supabase) Database** — `users`, `files`, and `file_parts` tables managed via SQLAlchemy ORM.

### Uploads
- **Bypasses 2GB limit** — Files > 1.9 GB are split into sequential "volumes".
- **Raw Streaming** — Frontend streams raw bytes directly to `/api/upload/stream`, eliminating chunk overhead.
- **Shared Connection Pool** — One `TelegramClient` per user, cached and locked to prevent `AuthKeyDuplicatedError`. Disconnected cleanly on server shutdown.
- **Sequential Part Sending** — 512 KB parts are uploaded sequentially to Telegram. This prevents aggressive MTProto socket closures (WinError 10054) and wrong session ID security errors.
- **Zero Local Footprint** — Nothing is written to the server's disk.

### Downloads
- **Single-connection streaming** — `iter_download` streams directly to the HTTP response.
- **Multi-part reassembly** — Multi-volume files chained into one contiguous download stream.

### Frontend
- Vanilla HTML, JavaScript, Tailwind CSS. Served as static files by FastAPI.
- Dark glassmorphism UI with real-time upload progress bars.

---

## Architecture

| Layer | Technology |
|---|---|
| Frontend | HTML5, Vanilla JS, Tailwind CSS (CDN) |
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Database | PostgreSQL (Supabase) via SQLAlchemy ORM |
| Telegram Client | Telethon (asyncio) |

---

## Prerequisites

- Python 3.10+
- PostgreSQL (Supabase) running at `localhost:3307`
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
DB_HOST=localhost
DB_PORT=3307
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=cloud_db

JWT_SECRET_KEY=your_very_long_random_secret_string
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

TG_API_ID=your_api_id
TG_API_HASH=your_api_hash

ENVIRONMENT=development
```

### 4. Create PostgreSQL (Supabase) database

```sql
CREATE DATABASE IF NOT EXISTS cloud_db;
```

All tables are created automatically by SQLAlchemy on first startup.

### 5. Starting the Server

Every time you want to start or resume working on your cloud server, follow these exact steps:

**Step 1: Start the Database**
Because this app relies on PostgreSQL (Supabase), your database must be running first.
1. Open your database manager (like **XAMPP Control Panel** or Docker).
2. Start the **PostgreSQL (Supabase)** module.
3. Ensure it is running on the port specified in your `.env` (default is `3307`).

**Step 2: Start the Python Backend**
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
