"""Endpoints for an external cron, which also wakes a sleeping free-tier instance.

Off unless JOB_TOKEN is set; callers send it in the X-Job-Token header.
"""

import hmac
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from app.config import get_settings
from app.services.weekly import maybe_run_weekly_drop
from app.weeks import is_drop_due

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def require_job_token(x_job_token: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().job_token
    if not expected:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    if not x_job_token or not hmac.compare_digest(x_job_token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad job token")


@router.post("/jobs/weekly-drop", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_job_token)])
def weekly_drop(background: BackgroundTasks):
    """Runs today's drop in the background if it's due and not yet done; returns at once
    so short cron timeouts (cron-job.org: 30 s) aren't hit while quizzes generate."""
    due = is_drop_due()
    if due:
        background.add_task(maybe_run_weekly_drop)
    return {"due": due}
