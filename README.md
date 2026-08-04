# Telegram Cloud Storage Web App (MVP)

A modern, fast, and scalable cloud storage web application that uses **Telegram** as the backend storage layer. Uploaded files are securely stored inside a private Telegram channel automatically created for each user, while lightweight metadata is managed locally via a SQL database.

## Current Progress

### Phase 1: Project Foundation & Authentication (Completed)
- Configured FastAPI project structure with SQLAlchemy (SQLite for local dev, production-ready for MySQL).
- Implemented secure JWT-based authentication and bcrypt password hashing.
- Built User Registration, Login, and protected Dashboard APIs.
- Applied modern, dark glassmorphism styling for the frontend using Tailwind CSS.

### Phase 2: Telegram Account Integration (Completed)
- Integrated `Telethon` for asynchronous Telegram communication.
- Built a streamlined UI for users to connect their Telegram account securely via OTP.
- Automatically provisions a private "Personal Cloud Storage" Telegram channel upon linking.
- Securely stores the Telegram Session String, User ID, and Channel ID in the database.

### Phase 3: File Upload (Completed)
- Built a dedicated file upload API (`/api/upload`) that receives multipart form data.
- Uploaded files are temporarily cached on the server, pushed to the user's private Telegram channel asynchronously, and immediately deleted from the server to ensure zero local footprint.
- Saved lightweight metadata (`FileRecord`) in the local database including filename, size, and the Telegram `message_id` for future retrieval.
- Updated the Dashboard UI with a drag-and-drop enabled Tailwind CSS upload form and live progress state.

### Phase 4: File Management (Completed)
- Users can view a list of all files uploaded during their session via the `/api/files` endpoint.
- Implemented file downloading via FastAPI `StreamingResponse` which leverages Telethon's `iter_download()` to stream the file directly from Telegram to the user, completely bypassing local disk storage.
- Added file deletion support: instantly deletes the Telegram message and cleans up the local MySQL `FileRecord`.

### Phase 5: Testing & Finalization (Completed)
- Re-architected project into a clear `frontend/` (Static HTML/JS/CSS) and `backend/` (FastAPI JSON APIs) separation.
- Completely migrated from Jinja2 templates to pure REST API architecture.
- Improved Error handling, JWT token management, and automatic Telegram session validation.
- Standardized database column naming to `users` and `files` according to the core requirements.
- Polished the modern web UI for seamless AJAX workflow (Login -> OTP -> Upload -> Download -> Delete).

## Prerequisites
- Python 3.10+
- Telegram API Credentials (`API_ID` and `API_HASH`) from [my.telegram.org](https://my.telegram.org).
- MySQL Server (optional for production, SQLite used by default).

## Installation and Setup

1. **Clone the repository and prepare the virtual environment.**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\Activate.ps1
   # On Mac/Linux:
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Configure Environment Variables:**
   - Open the `.env` file located in the `backend/` directory.
   - Insert your Telegram API credentials (required to use the Telethon client):
     ```env
     TG_API_ID=your_api_id
     TG_API_HASH=your_api_hash
     ```

4. **Initialize Database:**
   - The SQLite database (`auth_app.db`) will be automatically created in the root directory upon startup. If you wish to use MySQL, configure the variables inside `backend/.env`.

5. **Run the Server:**
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```