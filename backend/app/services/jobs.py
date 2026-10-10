"""Claim/finish rows in job_runs so a job runs at most once per key at a time.

The weekly drop can be triggered by APScheduler, the startup catch-up and the
external cron endpoint. Per-member Notification rows de-duplicate sends, but two
runs racing past the check would still double-send, so a run claims its row first.
"""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import JobRun, as_utc, utcnow

STALE_AFTER = timedelta(minutes=30)  # a "running" row older than this was abandoned (crash, redeploy)


def claim(db: Session, job: str, run_key: str) -> JobRun | None:
    """Returns the claimed row, or None if the job is done or running elsewhere."""
    row = db.scalar(select(JobRun).where(JobRun.job == job, JobRun.run_key == run_key))
    now = utcnow()
    if row is None:
        row = JobRun(job=job, run_key=run_key, status="running", started_at=now)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None
        return row
    if row.status == "done":
        return None
    if row.status == "running" and as_utc(row.started_at) > now - STALE_AFTER:
        return None
    # Reclaim a failed or stale run; the WHERE makes it a compare-and-set.
    result = db.execute(
        update(JobRun)
        .where(JobRun.id == row.id, JobRun.status == row.status, JobRun.started_at == row.started_at)
        .values(status="running", started_at=now, finished_at=None)
    )
    db.commit()
    if result.rowcount != 1:
        return None
    db.refresh(row)
    return row


def finish(db: Session, row: JobRun, ok: bool, detail: str | None = None) -> None:
    row.status = "done" if ok else "failed"
    row.finished_at = utcnow()
    row.detail = detail
    db.commit()
