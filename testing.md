# Testing Strategy

## Overview
The testing strategy for the Cloud Server project focuses primarily on ensuring the reliability of the backend API, specifically concerning cross-origin resource sharing (CORS), authentication mechanisms, complex asynchronous file operations, parallel streaming to Telegram, and file sharing logic.

## Test Suite Location
All automated tests are located in the `backend/tests/` directory. Manual load/performance tests reside in `backend/scripts/`.

## Current Test Coverage
The test suite covers:
1.  **CORS Preflight:** Verification that the FastAPI backend correctly handles `OPTIONS` requests from allowed origins with the appropriate `Access-Control-Allow-*` headers.
2.  **Authentication:** Testing user registration, login, and token validation.
3.  **File Streaming & Parallel Transfers:** Verifying the logic for streaming files (uploading and downloading) via the Telethon client, ensuring `DCSenderPool` correctly handles chunks without data loss.
4.  **File Sharing:** Tests ensuring share tokens are correctly generated, validated, and that unauthorized users cannot access non-shared files.

## Running the Tests

To run the tests, ensure you are in the backend directory and your virtual environment is activated:

```bash
cd backend
source myenv/Scripts/activate  # On Windows
pytest -v
```

### Manual Parallel Testing
To verify transfer speeds and chunk integrity outside the standard `pytest` environment:
```bash
python scripts/manual_parallel_test.py
```

### Async Testing Note
The tests utilize `pytest-asyncio` because the FastAPI application is highly asynchronous. Ensure that the event loop scope is correctly configured (usually handled within the tests or `pytest.ini`) to avoid warnings and ensure tests don't interfere with each other's connection pools.

## Adding New Tests
When implementing new features on the backend:
1. Create a corresponding test file in `backend/tests/` (e.g., `test_sharing.py` if expanding).
2. Use `httpx.AsyncClient` for simulating API requests.
3. Mock external dependencies (like the actual Telegram API or the database if necessary) to ensure tests are fast, deterministic, and don't rely on live external services.
