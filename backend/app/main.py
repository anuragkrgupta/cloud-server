"""
Application entrypoint.

Run with:
    cd backend
    uvicorn app.main:app --reload
"""
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routes import auth_routes, telegram, files

app = FastAPI(title="Telegram Cloud Storage MVP")

app.include_router(auth_routes.router, tags=["auth"])
app.include_router(telegram.router, tags=["telegram"])
app.include_router(files.router, tags=["files"])

@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)

# Mount the frontend directory so HTML/JS/CSS are served statically
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
frontend_dir = os.path.join(BASE_DIR, "frontend")

if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
