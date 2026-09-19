# Key Decisions Log

This document tracks significant architectural and implementation decisions made during the project.

## 1. Decentralized Storage via Telegram
- **Context:** Needed a cost-effective and scalable storage solution for personal cloud files.
- **Decision:** Utilize the Telegram API (via Telethon) as the backend storage layer. Files are sent as messages to a dedicated channel/chat, and message IDs are stored in the database for retrieval.
- **Rationale:** Free, high capacity, handles large files efficiently, and highly available.

## 2. Parallel Transfer Architecture
- **Context:** Standard Telegram uploads/downloads via a single MTProto connection are artificially rate-limited, leading to slow transfer speeds for large files.
- **Decision:** Implemented a `DCSenderPool` that exports the user's authorization and distributes 512KB chunks round-robin across multiple `MTProtoSender` worker connections.
- **Rationale:** Massively increases throughput, fully utilizing server bandwidth and dramatically improving the user experience for large cloud files.

## 3. Dedicated Private Channels
- **Context:** Initially, files could be saved to 'Saved Messages', but this clutters the user's personal chat space.
- **Decision:** Automatically create a dedicated private channel (`CloudStorage_{tg_user_id}`) during the Telegram QR login process.
- **Rationale:** Keeps the user's primary Telegram experience clean while organizing all cloud files in an isolated space.

## 4. File Sharing & Background Transfers
- **Context:** Users need to share files. If we just serve the stream from User A's channel to User B, User A retains control and could delete it.
- **Decision:** Provide a "Save to my Cloud" feature that creates a background `asyncio` task. This task streams the file from User A's channel directly into User B's channel.
- **Rationale:** Ensures true ownership transfer. The background task approach prevents the HTTP request from timing out on large file copies.

## 5. Decoupled Deployment Strategy
- **Context:** Project consists of a static frontend and a Python backend.
- **Decision:** Deploy the frontend to Vercel and the backend to Render.
- **Rationale:** Vercel excels at serving static assets globally via CDN. Render provides an easy-to-use PaaS environment for Python/FastAPI applications. This separation of concerns allows for independent scaling and management.

## 6. Implementation of `apiFetch` Wrapper
- **Context:** The decoupled deployment (Vercel -> Render) caused significant CORS and cross-origin authentication issues.
- **Decision:** Created a global `apiFetch` utility (`frontend/js/api.js`) to encapsulate all backend API calls.
- **Rationale:** Centralizes API configuration, manages Authorization headers, handles 401 Unauthorized responses, and mandates `credentials: 'include'` for cross-origin cookies.
