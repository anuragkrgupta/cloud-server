
import os
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine, check_database_connection
from app.routes import auth_routes, telegram, files, share


def ensure_hardware_acceleration():
    """Verifies that cryptg (AES-NI hardware acceleration) is active.
    If missing on any device/server, attempts auto-installation and reloads the Telethon cipher engine."""
    try:
        import cryptg
        from telethon.crypto import aes
        if getattr(aes, "cryptg", None) is not None:
            logging.info("Hardware acceleration (AES-NI via cryptg) is ACTIVE and verified.")
            return
    except ImportError:
        pass

    logging.warning("Hardware acceleration (cryptg) not detected. Attempting automatic installation...")
    try:
        import sys
        import subprocess
        import importlib
        subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptg>=0.5.0"])
        from telethon.crypto import aes
        importlib.reload(aes)
        logging.info("Successfully installed and enabled cryptg hardware acceleration.")
    except Exception as err:
        logging.error("Could not automatically install cryptg: %s. Using standard cipher fallback.", err)

ensure_hardware_acceleration()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify hardware acceleration on server startup
    ensure_hardware_acceleration()
    # Verify the database before attempting table creation.
check_database_connection()
Base.metadata.create_all(bind=engine)
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
    # Enforce custom header for state-changing operations to statelessly mitigate CSRF.
    # OPTIONS (CORS preflight) must always pass through untouched.
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

