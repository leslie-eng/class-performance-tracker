import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.deps import today
from app.routers import admin, auth, challenges, job_applications, leaderboard, members, submissions
from app.scheduler import build_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = build_scheduler() if get_settings().scheduler_enabled else None
    if scheduler:
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


settings = get_settings()
# Browsers send Origin without a trailing slash, so "https://x.onrender.com/" would never match.
cors_origins = [stripped.rstrip("/") for o in settings.cors_origins.split(",") if (stripped := o.strip())]
logging.getLogger(__name__).info("CORS allowed origins: %s", cors_origins)

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, challenges, submissions, leaderboard, members, job_applications, admin):
    app.include_router(r.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/meta", tags=["meta"])
def meta():
    """Server timezone and date, so clients count down to the same midnight the backend uses."""
    return {"timezone": settings.timezone, "today": today()}
