from typing import Literal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DB, AdminUser
from app.models import JobRun, WeeklyBrief
from app.routers.weekly import brief_out
from app.schemas_weekly import BriefOut
from app.services import jobs
from app.services.weekly import run_monthly, run_weekly_drop, summarize_brief
from app.weeks import current_month_key, current_week_key, upcoming_week_key

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/weekly/drop/run")
def trigger_weekly_drop(db: DB, _: AdminUser, dry_run: bool = True, week: Literal["current", "upcoming"] = "current"):
    """Preview (default) or send a Friday Drop. `upcoming` previews next Friday's drop
    from the notes and proposals collected so far; it can't be sent early."""
    if week == "upcoming":
        if not dry_run:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The upcoming drop can only be previewed")
        return run_weekly_drop(db, upcoming_week_key(), dry_run=True)
    week_key = current_week_key()
    if dry_run:
        return run_weekly_drop(db, week_key, dry_run=True)
    run = jobs.claim(db, "weekly_drop", week_key.isoformat())
    if run is None:
        existing = db.scalar(select(JobRun).where(JobRun.job == "weekly_drop", JobRun.run_key == week_key.isoformat()))
        if existing and existing.status == "running":
            raise HTTPException(status.HTTP_409_CONFLICT, "This week's drop is being sent right now")
        # Already done: re-running only reaches members whose send failed.
        return run_weekly_drop(db, week_key)
    result = run_weekly_drop(db, week_key)
    jobs.finish(db, run, ok=True, detail=f"sent {result['sent']} (admin)")
    return result


@router.post("/monthly/run")
def trigger_monthly(db: DB, _: AdminUser, dry_run: bool = True):
    """Pre-generate this month's course and interview quizzes and tell members."""
    return run_monthly(db, current_month_key(), dry_run=dry_run)


@router.post("/weekly/brief/{brief_id}/regenerate", response_model=BriefOut)
def regenerate_summary(brief_id: int, db: DB, _: AdminUser):
    brief = db.get(WeeklyBrief, brief_id)
    if brief is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brief not found")
    if not brief.source_notes.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This brief has no notes to summarise")
    summarize_brief(db, brief)
    return brief_out(brief)
