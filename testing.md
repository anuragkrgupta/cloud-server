# Testing & Quality Assurance Strategy

## 1. Overview

The testing strategy for the Cloud Server ensures reliability, performance, and security across the backend API, database layer, cryptographic acceleration subsystem, and asynchronous MTProto streaming pipeline.

Key testing priorities include:
- **CORS & Preflight Handling:** Cross-origin communication between the Vercel frontend and Render backend.
- **Authentication & Security:** Registration, bcrypt hashing, JWT issuance, 30-day token persistence, and Fernet session encryption.
- **Hardware Cryptography Verification:** Ensuring native AES-NI acceleration via `cryptg` is loaded on startup.
- **Parallel MTProto Streaming:** Validating `DCSenderPool` async request pipelining without socket collisions or `AuthKeyDuplicatedError`.
- **Large Multi-Volume Slicing:** Ensuring files exceeding 2 GB are partitioned, streamed, and downloaded contiguously without byte corruption.
- **File Sharing & Background Transfers:** Validating token generation, public streaming, and asynchronous channel-to-channel transfers.

---

## 2. Test Suite Organization

```
backend/
├── tests/
│   ├── test_auth.py             # User registration, login, 30-day JWT validation
│   ├── test_cors.py             # Cross-origin headers and OPTIONS preflights
│   ├── test_files.py            # Upload, download, deletion, and metadata handling
│   ├── test_parallel.py         # DCSenderPool pipelining and mock MTProto senders
│   └── test_sharing.py          # Share tokens, access permissions, background copy
├── scripts/
│   ├── manual_parallel_test.py  # Standalone benchmark for MTProto transfer throughput
│   └── verify_hardware_accel.py # Dedicated check for AES-NI cryptg acceleration
└── pytest.ini                   # Pytest async configuration
```

---

## 3. Running Automated Tests

### 3.1 Activating the Virtual Environment & Running Pytest

From the `backend` directory:

```bash
cd backend

# On Windows:
.\venv\Scripts\activate

# On Linux / macOS:
source venv/bin/activate

# Execute all tests verbosely
pytest -v
```

### 3.2 Testing Specific Modules
```bash
# Run authentication tests
pytest tests/test_auth.py -v

# Run parallel transfer and DCSenderPool tests
pytest tests/test_parallel.py -v

# Run CORS preflight tests
pytest tests/test_cors.py -v
```

---

## 4. Hardware Acceleration & Performance Verification

### 4.1 Verifying `cryptg` AES-NI
Start the server and observe startup logs, or verify in Python:
```bash
python -c "import telethon.crypto.aes as a; print('AES backend:', a.__file__)"
```
When `cryptg` is installed and active, the backend output confirms:
```
[INFO] telethon.crypto.aes: cryptg detected, it will be used for encryption
[INFO] root: Hardware acceleration (AES-NI via cryptg) is ACTIVE and verified.
```
If pure Python `pyaes` is reported instead, hardware acceleration has failed and must be resolved.

### 4.2 Live Transfer Speed Benchmarking
To test real transfer speeds and multi-volume integrity on a live server:
1. Ensure the backend server is running (`uvicorn app.main:app --port 8000`).
2. Run test transfers against the streaming endpoint:
```bash
# Direct stream upload benchmark
python -u scratch/test_direct_upload.py
```
Observed speeds on live broadband should reach ~3.9+ MB/s, validating full bandwidth utilization with minimal CPU overhead.

---

## 5. Async Testing Guidelines

- The test suite uses `pytest-asyncio`. Ensure async test functions are decorated with `@pytest.mark.asyncio`.
- When simulating HTTP endpoints, use `httpx.AsyncClient` with `transport=ASGITransport(app=app)`.
- Mock external Telegram RPC calls in automated CI tests so tests execute deterministically without hitting Telegram rate limits.
