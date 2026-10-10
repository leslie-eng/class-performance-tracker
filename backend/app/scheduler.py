"""In-process APScheduler jobs (design doc section 5).

Fine for a single API instance. If you run several workers/replicas, disable it
there (SCHEDULER_ENABLED=false) and run exactly one instance with it on, or move
these jobs to Celery beat.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db import SessionLocal
from app.deps import today
from app.services.notifications import run_lag_check, run_weekly_digest
from app.services.weekly import maybe_run_weekly_drop

log = logging.getLogger(__name__)


def nightly_lag_check() -> None:
    with SessionLocal() as db:
        results = run_lag_check(db, today())  # also recomputes streaks for active enrollments
        log.info("Lag check: %d lagging, %d nudged", len(results), sum(r["notified"] for r in results))


def weekly_digest() -> None:
    with SessionLocal() as db:
        run_weekly_digest(db, today())


def weekly_drop() -> None:
    maybe_run_weekly_drop()


def build_scheduler() -> BackgroundScheduler:
    s = get_settings()
    scheduler = BackgroundScheduler(timezone=s.tz)
    scheduler.add_job(nightly_lag_check, CronTrigger(hour=s.lag_check_hour, minute=0, timezone=s.tz), id="lag_check")
    scheduler.add_job(
        weekly_digest,
        CronTrigger(day_of_week=s.weekly_digest_day, hour=s.lag_check_hour, minute=30, timezone=s.tz),
        id="weekly_digest",
    )
    # Friday Drop. Idempotent; also triggered by the startup catch-up and the
    # /internal/jobs/weekly-drop cron endpoint in case this instance was asleep.
    scheduler.add_job(
        weekly_drop,
        CronTrigger(day_of_week=s.weekly_drop_day, hour=s.weekly_drop_hour, minute=0, timezone=s.tz),
        id="weekly_drop",
        misfire_grace_time=3600,
    )
    return scheduler
