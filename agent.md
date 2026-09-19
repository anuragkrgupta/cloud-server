# Agent Context

This document serves as a contextual guide for AI agents working on the "Cloud Server" project.

## Key Information
- **Project Structure:** A monolithic repository containing both the frontend (`/frontend`) and backend (`/backend`). 
- **Deployment:** The backend is deployed on Render, and the frontend on Vercel. Be mindful of CORS issues and cross-origin resource sharing requirements.
- **Frontend Fetch:** Always use the `apiFetch` wrapper function located in `frontend/js/api.js` for all backend requests. This wrapper handles `Authorization` headers and `credentials: 'include'` for cookies automatically.
- **Backend Architecture:** Built with FastAPI. It relies heavily on the `lifespan` context manager for application startup (database connection pools, Telegram client initialization) and shutdown events.
- **Database:** MySQL. Models include `User`, `FileRecord`, and `FilePartRecord`. `FilePartRecord` handles chunks of files split across multiple Telegram messages.
- **Storage:** Telethon is used to communicate with Telegram for file storage. Files are stored in a dedicated private channel (`CloudStorage_{tg_user_id}`). We use parallel upload/download techniques (`DCSenderPool`) to maximize speed.
- **Background Tasks:** File sharing between users (`save_shared_file`) is handled via asynchronous background tasks (`transfer_file_between_users`) to avoid blocking the API.

## Current State
- The application supports high-speed parallel uploads/downloads, QR code login, and peer-to-peer file sharing.
- A comprehensive test suite (`backend/tests/`) ensures core functionalities (auth, file uploads, parallel transfers) and CORS configurations are correct.
