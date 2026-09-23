"""
Application entrypoint.

Run with:
    cd backend
    uvicorn app.main:app --reload
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routes import auth_routes, telegram, files, share


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure database tables are created if DB is accessible
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass
    yield
    # Shutdown: Disconnect active Telegram clients cleanly
    try:
        from app.services.telegram_service import disconnect_all_clients
        await disconnect_all_clients()
    except Exception:
        pass


app = FastAPI(title="Telegram Cloud Storage MVP", lifespan=lifespan)

# CORS configuration for cross-origin frontend (e.g. Vercel)
cors_kwargs = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["Content-Length", "Content-Disposition"],
}

if settings.ALLOWED_ORIGINS:
    origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    cors_kwargs["allow_origins"] = origins
else:
    # Safe local defaults instead of a dangerous wildcard regex
    cors_kwargs["allow_origins"] = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(CORSMiddleware, **cors_kwargs)

@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    # Enforce custom header for state-changing operations to statelessly mitigate CSRF
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        if request.url.path.startswith("/api/"):
            if not request.headers.get("x-requested-with"):
                return JSONResponse(
                    status_code=403, 
                    content={"detail": "CSRF verification failed. Missing X-Requested-With header."}
                )
    return await call_next(request)

# Register API routers
app.include_router(auth_routes.router, tags=["auth"])
app.include_router(telegram.router, tags=["telegram"])
app.include_router(files.router, tags=["files"])
app.include_router(share.router, tags=["share"])

# Mount the frontend directory so HTML/JS/CSS can also be served statically if hosted together
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
frontend_dir = os.path.join(BASE_DIR, "frontend")

if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

