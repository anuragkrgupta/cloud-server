# UI/UX Design & Frontend Structure

## 1. Design Philosophy

- **Dark Glassmorphism Aesthetic:** A modern, sleek dark interface with glassmorphic cards, subtle borders, blurred backdrop filters, and vibrant neon accents (emerald/indigo) providing a premium cloud storage experience.
- **Minimalist & Clean:** The UI prioritizes core operations—uploading, streaming downloads, searching, sharing, and storage monitoring—without visual clutter.
- **Responsive Across Devices:** Fluid CSS grid and flex layouts that adapt gracefully across mobile smartphones, tablets, and wide desktop displays.
- **Accurate Real-Time Feedback:** Upload and download operations provide live speedometers (MB/s), dynamic time-to-completion (ETA) estimates, and byte-accurate progress bars driven by direct TCP stream backpressure.

---

## 2. Frontend Structure & Architecture

The frontend is entirely decoupled from the backend and is built with **Vanilla JavaScript (ES6+), HTML5, and Tailwind CSS**. There are zero Node.js build dependencies, bundling steps, or heavy UI frameworks.

### Directory Layout
```
/frontend
  ├── index.html               # Entry point; redirects to /login.html or /dashboard.html
  ├── login.html               # User sign-in interface
  ├── register.html            # User account registration interface
  ├── setup_telegram.html      # QR-code Telegram linking modal & 2FA prompt
  ├── dashboard.html           # Main file manager, upload zone, search, & file table
  ├── share.html               # Public share link viewer & "Save to my Cloud" import
  ├── css/                     # Custom stylesheet overrides (glassmorphism, scrollbars)
  └── js/
      ├── api.js               # Universal fetch wrapper (apiFetch) with auth handling
      ├── config.js            # Environment-aware backend API base URL resolution
      ├── dashboard.js         # Upload pipeline, multi-volume slicing, UI rendering
      └── share.js             # Share link validation, direct download, and copy logic
```

---

## 3. Key Interaction & UI Patterns

### 3.1 Upload Zone & Real-Time Metrics
- **Drag-and-Drop Zone:** Prominent drop target with dashed borders and hover states.
- **Volume Chunking Progress:** For files exceeding ~1.90 GB, the UI informs the user of multi-volume slicing and displays contiguous progress across all volumes.
- **Speed & ETA Engine:** Calculates rolling transfer speed in MB/s and estimated time remaining based on real TCP backpressure from `/api/upload/stream`.

### 3.2 Telegram QR Code Authentication
- Displays high-contrast QR codes generated directly from Telegram's MTProto login token.
- Background polling via `GET /api/telegram/qr-status` transitions automatically to 2FA password prompts if cloud passwords are enabled, or directly to the dashboard upon successful connection.
- Graceful modal notifications if an account mismatch occurs, giving the user control to override or retry.

### 3.3 Public File Sharing Interface (`share.html`)
- Clean, focused card displaying file metadata (name, human-readable size, upload date).
- Provides two clear actions:
  1. **Direct Download:** Streams the file directly from Telegram through the backend to the recipient's browser.
  2. **Save to my Cloud:** For logged-in users, initiates an instant server-to-server background copy to the user's private channel without local bandwidth consumption.

### 3.4 API Communication Standard (`apiFetch`)
- Every HTTP request originates from `frontend/js/api.js`.
- Automatically attaches `Authorization: Bearer <token>` when tokens are present in `localStorage`.
- Ensures `credentials: 'include'` for secure cookie support.
- Centralizes 401 Unauthorized interceptors, gracefully redirecting expired sessions to `login.html`.
