from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, CurrentUser, today
from app.models import Enrollment, GradingStatus, Submission, SubmissionType, TaskTypes, User
from app.routers.challenges import get_challenge_or_404
from app.schemas import SubmissionIn, SubmissionOut
from app.scoring import day_number_for, recompute_enrollment, rules_for
from app.services.grading import grade_submission

router = APIRouter(prefix="/submissions", tags=["submissions"])


def get_submission_for(db: DB, submission_id: int, user: User) -> Submission:
    sub = db.get(Submission, submission_id)
    if sub is None or (sub.enrollment.user_id != user.id and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    return sub


@router.post("", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
def create_submission(body: SubmissionIn, db: DB, user: CurrentUser, background: BackgroundTasks):
    challenge = get_challenge_or_404(db, body.challenge_id)
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.challenge_id == challenge.id, Enrollment.user_id == user.id)
    )
    if enrollment is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Enroll in this challenge before submitting")
    if challenge.task_types_allowed not in (TaskTypes.both, body.submission_type.value):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"This challenge only accepts {challenge.task_types_allowed.value} tasks"
        )

    rules = rules_for(challenge)
    today_day = day_number_for(challenge, today())
    day = body.day_number or today_day
    if today_day < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This challenge hasn't started yet")
    if not 1 <= day <= challenge.total_days:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Day must be between 1 and {challenge.total_days}")
    if day > today_day:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't submit for a future day")
    if today_day - day > rules["backfill_days"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Tasks can only be logged up to {rules['backfill_days']} day(s) late"
        )

    needs_ai = body.submission_type == SubmissionType.article or rules["ai_code_review"]
    fields = dict(
        enrollment_id=enrollment.id,
        day_number=day,
        submission_type=body.submission_type,
        content=body.content,
        language=body.language,
        problem_link=str(body.problem_link) if body.problem_link else None,
        grading_status=GradingStatus.pending if needs_ai else GradingStatus.not_applicable,
    )
    # The first submission for a day counts toward the streak; later ones are kept
    # (and still get AI feedback) but earn no points. A partial unique index
    # enforces this even under concurrent requests.
    already_counted = db.scalar(
        select(Submission.id).where(
            Submission.enrollment_id == enrollment.id,
            Submission.day_number == day,
            Submission.counts_for_streak,
        )
    )
    sub = Submission(**fields, counts_for_streak=already_counted is None)
    db.add(sub)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        sub = Submission(**fields, counts_for_streak=False)
        db.add(sub)
        db.flush()

    recompute_enrollment(db, enrollment, today())
    db.commit()
    if needs_ai:
        background.add_task(grade_submission, sub.id)
    return sub


@router.get("/me", response_model=list[SubmissionOut])
def my_submissions(db: DB, user: CurrentUser, challenge_id: int | None = None, limit: int = 100, offset: int = 0):
    q = (
        select(Submission)
        .join(Enrollment)
        .where(Enrollment.user_id == user.id)
        .order_by(Submission.submitted_at.desc())
        .limit(min(limit, 500))
        .offset(offset)
    )
    if challenge_id is not None:
        q = q.where(Enrollment.challenge_id == challenge_id)
    return db.scalars(q).all()


@router.get("/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: int, db: DB, user: CurrentUser):
    """Poll this after submitting an article until grading_status is done/failed."""
    return get_submission_for(db, submission_id, user)


@router.post("/{submission_id}/regrade", response_model=SubmissionOut)
def regrade(submission_id: int, db: DB, user: CurrentUser, background: BackgroundTasks):
    sub = get_submission_for(db, submission_id, user)
    if sub.grading_status != GradingStatus.failed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only failed gradings can be retried")
    sub.grading_status = GradingStatus.pending
    sub.ai_feedback = None
    db.commit()
    background.add_task(grade_submission, sub.id)
    return sub
