import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.deps import today
from app.routers import (
    admin,
    admin_quizzes,
    admin_weekly,
    auth,
    challenges,
    coding,
    internal,
    job_applications,
    leaderboard,
    materials,
    members,
    quizzes,
    submissions,
    weekly,
)
from app.scheduler import build_scheduler
from app.services.materials import MAX_UPLOAD_BYTES
from app.services.weekly import maybe_run_weekly_drop

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = build_scheduler() if get_settings().scheduler_enabled else None
    if scheduler:
        scheduler.start()
        # Catch-up: a sleeping free-tier instance misses the 08:00 cron trigger, so run a
        # due drop on wake. In a thread, so startup (and the health check) isn't held up.
        threading.Thread(target=maybe_run_weekly_drop, name="weekly-drop-catchup", daemon=True).start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


settings = get_settings()
# Browsers send Origin without a trailing slash, so "https://x.onrender.com/" would never match.
cors_origins = [o.strip().rstrip("/") for o in settings.cors_origins.split(",") if o.strip()]
logging.getLogger(__name__).info("CORS allowed origins: %s", cors_origins)

app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    # Starlette parses (and spools) a multipart body before auth or size checks run,
    # so refuse oversized uploads up front from the declared length.
    if request.url.path.endswith("/upload"):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_UPLOAD_BYTES + 64 * 1024:
            return JSONResponse({"detail": "Files are limited to 5 MB"}, status_code=413)
    return await call_next(request)


# Added after the size guard so CORS wraps it and its 413 still carries CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    auth, challenges, submissions, leaderboard, members, job_applications, admin,
    weekly, quizzes, admin_weekly, internal, materials, admin_quizzes, coding,
):
    app.include_router(r.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/meta", tags=["meta"])
def meta():
    """Server timezone and date, so clients count down to the same midnight the backend uses."""
    return {"timezone": settings.timezone, "today": today(), "specializations": settings.specialization_list}
