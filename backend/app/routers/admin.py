from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import DB, AdminUser, today
from app.models import Enrollment, GradingStatus, Notification, Submission, User
from app.schemas import GradeOverride, SubmissionOut, UserOut
from app.scoring import recompute_enrollment
from app.services.notifications import run_lag_check, run_weekly_digest

router = APIRouter(prefix="/admin", tags=["admin"])


class NotificationOut(BaseModel):
    id: int
    user_id: int
    challenge_id: int | None
    type: str
    message_sent: str
    status: str
    error: str | None
    sent_at: str


@router.post("/notify/run")
def trigger_lag_check(db: DB, _: AdminUser, dry_run: bool = True):
    """Run the nightly lag check now. Defaults to a dry run that sends nothing."""
    return {"dry_run": dry_run, "lagging": run_lag_check(db, today(), dry_run=dry_run)}


@router.post("/digest/run")
def trigger_digest(db: DB, _: AdminUser, dry_run: bool = True):
    return {"dry_run": dry_run, "message": run_weekly_digest(db, today(), dry_run=dry_run)}


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(db: DB, _: AdminUser, limit: int = 100):
    rows = db.scalars(select(Notification).order_by(Notification.sent_at.desc()).limit(min(limit, 500))).all()
    return [
        NotificationOut(
            id=n.id,
            user_id=n.user_id,
            challenge_id=n.challenge_id,
            type=n.type.value,
            message_sent=n.message_sent,
            status=n.status.value,
            error=n.error,
            sent_at=n.sent_at.isoformat(),
        )
        for n in rows
    ]


@router.patch("/submissions/{submission_id}/grade", response_model=SubmissionOut)
def override_grade(submission_id: int, body: GradeOverride, db: DB, _: AdminUser):
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    sub.ai_score = body.ai_score
    if body.ai_feedback is not None:
        sub.ai_feedback = body.ai_feedback
    sub.grade_overridden = True
    sub.grading_status = GradingStatus.done
    recompute_enrollment(db, sub.enrollment, today())
    db.commit()
    return sub


@router.post("/recompute")
def recompute_all(db: DB, _: AdminUser):
    """Rebuild every cached streak/points row from submissions."""
    enrollments = db.scalars(select(Enrollment)).all()
    for e in enrollments:
        recompute_enrollment(db, e, today())
    db.commit()
    return {"recomputed": len(enrollments)}


@router.patch("/members/{user_id}/role", response_model=UserOut)
def set_admin(user_id: int, is_admin: bool, db: DB, admin: AdminUser):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if user.id == admin.id and not is_admin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't remove your own admin role")
    user.is_admin = is_admin
    db.commit()
    return user
