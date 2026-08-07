# Telegram Cloud Storage Web App (MVP)

A modern, fast, and scalable cloud storage web application that uses **Telegram** as an unlimited backend storage layer. Uploaded files are securely stored inside a private Telegram channel automatically created for each user, while lightweight metadata is managed locally via a **MySQL** database.

This project supports **unlimited file sizes** (bypassing Telegram's standard 2GB limit) by automatically chunking, streaming, and parallelizing uploads and downloads natively in the browser and backend.

## 🚀 Key Features

### Authentication & Security
- **JWT Based Authentication**: Secure, 6-month expiry JSON Web Tokens.
- **QR Code Telegram Login**: Securely links a user's Telegram account without exposing phone numbers or passing OTPs through the frontend.
- **AES/Fernet Encryption**: Telegram Session Strings are heavily encrypted at rest in the database using your `JWT_SECRET_KEY`. Session data is strictly kept on the backend.
- **MySQL Database**: Robust relational architecture utilizing `users`, `files`, and `file_parts` tables.

### Unlimited Uploads & Parallelization
- **Bypasses 2GB Limit**: Files larger than 1.9GB are automatically split into "volumes" in the browser and sequentially tracked in the database.
- **Chunked Uploads**: The frontend securely slices files into 15MB chunks.
- **Parallel Telegram Streaming**: The FastAPI backend takes incoming 15MB chunks, splits them into Telegram's strict 512KB pieces, and fires them to Telegram **concurrently** using `asyncio.gather()`, drastically improving upload speeds.
- **Zero Local Footprint**: Data streams instantly into Telegram memory buffers. Nothing is ever saved to the server's hard drive.

### Seamless Downloads
- **Chained Async Generators**: When downloading a file larger than 1.9GB, the backend dynamically queries the `file_parts` table and streams the segmented Telegram messages back to the user as a single, contiguous file download.

### Modern UI
- Built with **Vanilla HTML, JavaScript, and Tailwind CSS**.
- **Dark Glassmorphism** aesthetics.
- Real-time progress bars, volume tracking, and network retry logic integrated into the frontend.

---

## 🏗️ Architecture

- **Frontend**: HTML5, Vanilla JS, Tailwind CSS (via CDN). Served as static files by FastAPI.
- **Backend**: Python 3.10+, FastAPI, Uvicorn.
- **Database**: MySQL (SQLAlchemy ORM).
- **Telegram Client**: Telethon (Asyncio).

---

## ⚙️ Prerequisites

- Python 3.10+
- Telegram API Credentials (`API_ID` and `API_HASH`) from [my.telegram.org](https://my.telegram.org).
- MySQL Server running on `localhost:3306` (or remotely).

---

## 🛠️ Installation and Setup

1. **Clone the repository and prepare the virtual environment:**
   ```bash
   cd backend
   python -m venv venv
   
   # On Windows:
   .\venv\Scripts\activate
   
   # On Mac/Linux:
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create or open the `.env` file located in the `backend/` directory:
   ```env
   # Telegram App Credentials
   TG_API_ID=your_api_id
   TG_API_HASH=your_api_hash
   
   # Security
   JWT_SECRET_KEY=your_very_long_random_secret_string
   
   # MySQL Database Connection
   DB_USER=root
   DB_PASSWORD=your_password
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_NAME=cloud_db
   ```

4. **Initialize MySQL Database:**
   - Ensure your MySQL service (e.g. XAMPP) is running.
   - You **do not** need to create the database manually. Just ensure your MySQL credentials in `.env` are correct.
   - The application will automatically create the `cloud_db` database and build the `users`, `files`, and `file_parts` tables upon startup.
   - **Note:** Do NOT manually import `schema.sql` or `database/schema.sql`. The SQLAlchemy ORM manages the schema automatically and will create all required tables upon first start.

5. **Run the Server:**
   ```bash
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   *Note: The frontend is served as static files from the FastAPI app directly (no Node.js required).*

## ⚠️ Notes for Deployment
- Ensure `JWT_SECRET_KEY` is highly secure in production as it encrypts the Telegram sessions.
- In production, it is highly recommended to run FastAPI behind a reverse proxy (like Nginx) and configure HTTPS to secure the JWT cookies and chunked data transfers.