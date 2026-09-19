# Coding Standards & Project Rules

## Backend (Python/FastAPI)
1. **Asynchronous Code:** Use `async/await` for all I/O bound operations (database queries, Telegram API calls, file handling).
2. **Resource Management:** Never use deprecated `@app.on_event`. All database connection pools and long-lived clients (Telethon) MUST be initialized and closed within the application's `lifespan` context manager.
3. **CORS Configuration:** Maintain strict but functional CORS policies. Allow origins specifically required for production (Vercel domain) and local development. Ensure `allow_credentials=True`.
4. **Parallelism & Rate Limiting:** Always use `DCSenderPool` for file uploads and downloads. Avoid sequential uploads which trigger Telegram flood waits or slow performance. Ensure `workers` limit is conservative (e.g., 4-8).
5. **Eager Validation:** Eagerly validate Telegram sessions and entities (like channel resolution) before returning stream generators, to catch authentication errors early.
6. **Background Tasks:** Long-running operations like file transfers between users should be executed via `asyncio.create_task` (or Celery if scaled further) to prevent blocking HTTP endpoints.
7. **Environment Variables:** Use `.env` for local development. Never hardcode secrets (database credentials, Telegram API keys, JWT secrets) in the source code.

## Frontend (JavaScript/HTML/CSS)
1. **API Interaction:** DO NOT use raw `fetch()`. You MUST use the `apiFetch` function exported from `frontend/js/api.js`. This guarantees correct headers, CORS configurations, and dynamic URL resolution.
2. **Vanilla JS:** Stick to Vanilla JavaScript (ES6+). Do not introduce frameworks like React or Vue unless explicitly planned and approved.
3. **Modularity:** Keep JavaScript files focused on specific views or functionalities (e.g., `dashboard.js`, `share.js`).
4. **Environment Variables:** The API base URL should be managed centrally in `frontend/js/config.js` to easily switch between local development and production environments.

## Deployment
- **Backend:** Deployments to Render are managed via `render.yaml`. Any infrastructure changes must be reflected in this file.
- **Frontend:** Deployments to Vercel rely on `vercel.json` for routing rules. Ensure any new static assets or HTML files are correctly handled by these rules.
