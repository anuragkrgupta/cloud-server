# Project Memory & Status

## Current State (As of Last Major Update)
The Cloud Server project has achieved a stable, highly-performant state with advanced features like parallelized Telegram uploads, QR code authentication, and user-to-user file sharing.

## Recent Milestones
- **Parallel File Transfers:** Implemented `DCSenderPool` and parallel streaming architecture (`parallel_transfer.py`), completely bypassing Telegram's single-connection speed limits for both uploads and downloads.
- **File Sharing & Transfers:** Implemented the ability to generate shareable links (`/share.html`) and asynchronously transfer files between users' Telegram cloud storage channels in the background.
- **QR Code Authentication:** Replaced standard phone number login with a smooth QR Code login flow for Telegram connection, including automatic private storage channel creation.
- **Database Schema Expansion:** Refactored the database to use `FilePartRecord` allowing files larger than 2GB to be chunked across multiple Telegram messages.
- **Deployment Configuration:** Successfully created `render.yaml` for backend deployment and `vercel.json` for frontend routing. The project is ready for multi-platform cloud hosting.
- **Test Suite Verification:** A comprehensive test suite verifies CORS, auth, and file streaming passes reliably. Added `manual_parallel_test.py` for performance testing.

## Known Issues / To-Do
- N/A currently. The focus is on maintaining stability post-deployment.
- Future enhancement: Consider chunk size optimization and dynamic worker scaling based on network conditions.

## Important Context for Future Work
When modifying the frontend, always remember that the backend is hosted on a different domain. Use `apiFetch`. When modifying the backend, ensure any new endpoints are covered by the existing CORS policy and that async resources (like the Telethon client) are managed within the established `lifespan` context. Do not break the parallel streaming logic.
