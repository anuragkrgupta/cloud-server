# Product Requirements Document (PRD)

## Project Overview
The "Cloud Server" is a web-based application that leverages the Telegram API (via Telethon) to provide users with personal cloud storage capabilities. It allows users to register, log in, connect their Telegram accounts via QR code, and upload, download, and share files seamlessly. 

## Goals
- Provide a robust and scalable backend API for file management.
- Offer a lightweight, responsive, and intuitive frontend interface.
- Ensure secure user authentication and cross-origin communication.
- Utilize Telegram's infrastructure for efficient and reliable file storage.
- Achieve high-speed file transfers using parallel connections.

## Core Features
1. **User Authentication:** Registration and login system with token-based authentication.
2. **Telegram Integration:** Users can link their Telegram accounts securely using QR code login. A dedicated private channel (`CloudStorage_{tg_user_id}`) is automatically created for storage.
3. **File Management:** High-speed parallel upload, download, delete, and list files. Files can be >2GB and are split across messages if necessary.
4. **File Sharing & Transfer:** Generate shareable links for specific files. Other users can save shared files directly to their own Telegram cloud storage via background transfer tasks.
5. **Dashboard:** A central hub for users to view and manage their stored files, share files, and view storage space.

## Technical Requirements
- **Frontend:** HTML, CSS, JavaScript (Vanilla). Hosted on Vercel.
- **Backend:** Python (FastAPI). Hosted on Render.
- **Database:** MySQL for user and file metadata.
- **Storage:** Telegram (via Telethon) using multi-connection pools.
- **Communication:** RESTful APIs with strict CORS configurations for cross-origin frontend-backend interaction.
