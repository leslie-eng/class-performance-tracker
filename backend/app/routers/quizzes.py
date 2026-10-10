from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.deps import DB, CurrentUser
from app.models import QuizAttempt, QuizKind, QuizStatus, User, as_utc, utcnow
from app.models import Quiz as QuizModel
from app.schemas_weekly import AnswersIn, AttemptOut, QuizLeaderRow
from app.services import quizzes
from app.weeks import current_month_key, current_week_key

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


def attempt_out(attempt: QuizAttempt, late: bool = False) -> AttemptOut:
    quiz = attempt.quiz
    submitted = attempt.submitted_at is not None
    deadline = as_utc(attempt.deadline_at)
    return AttemptOut(
        id=attempt.id,
        quiz_id=quiz.id,
        kind=quiz.kind.value,
        specialization=quiz.specialization,
        duration_minutes=quiz.duration_minutes,
        started_at=as_utc(attempt.started_at),
        deadline_at=deadline,
        ends_at=deadline - quizzes.SUBMIT_GRACE,
        server_now=utcnow(),
        submitted=submitted,
        late=late,
        questions=quizzes.public_questions(quiz),
        answers=attempt.answers or {},
        score=attempt.score if submitted else None,
        max_score=attempt.max_score,
        points_awarded=attempt.points_awarded if submitted else 0,
        grading_status=attempt.grading_status.value,
        grading_error=attempt.grading_error if submitted else None,
        results=attempt.per_question if submitted else None,  # answer keys only after submission
    )


def own_attempt(db: DB, attempt_id: int, user: User, allow_admin: bool = False) -> QuizAttempt:
    attempt = db.get(QuizAttempt, attempt_id)
    if attempt is None or (attempt.user_id != user.id and not (allow_admin and user.is_admin)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    return attempt


def http_error(e: quizzes.QuizError) -> HTTPException:
    return HTTPException(e.status_code, str(e))


@router.post("/{kind}/start", response_model=AttemptOut)
def start(kind: QuizKind, db: DB, user: CurrentUser, duration: int = Query(...)):
    """Starts (or resumes) the member's one attempt at this period's quiz."""
    if kind == QuizKind.weekly:
        period, spec = current_week_key().isoformat(), None
    else:
        period, spec = current_month_key(), quizzes.member_specialization(user) if kind == QuizKind.interview else None
    try:
        quiz = quizzes.ensure_quiz(db, kind, period, spec, duration)
    except quizzes.QuizError as e:
        raise http_error(e)
    if quiz.status == QuizStatus.generating:
        raise HTTPException(status.HTTP_409_CONFLICT, "This quiz is being generated; try again in a minute")
    if quiz.status == QuizStatus.failed:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "This quiz couldn't be generated; the admins have been told")
    if quiz.status == QuizStatus.draft:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This quiz is waiting for admin review")
    attempt = quizzes.start_attempt(db, user, quiz)
    quizzes.finalize_if_expired(db, attempt)
    if attempt.submitted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You've already taken this quiz (attempt {attempt.id})")
    return attempt_out(attempt)


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(attempt_id: int, db: DB, user: CurrentUser):
    attempt = own_attempt(db, attempt_id, user, allow_admin=True)
    quizzes.finalize_if_expired(db, attempt)
    return attempt_out(attempt)


@router.patch("/attempts/{attempt_id}/answers", response_model=AttemptOut)
def autosave(attempt_id: int, body: AnswersIn, db: DB, user: CurrentUser):
    attempt = own_attempt(db, attempt_id, user)
    try:
        quizzes.save_answers(db, attempt, body.answers)
    except quizzes.QuizError as e:
        raise http_error(e)
    return attempt_out(attempt)


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptOut)
def submit(attempt_id: int, body: AnswersIn, db: DB, user: CurrentUser):
    """After the deadline the submitted answers are ignored and the autosaved ones graded."""
    attempt = own_attempt(db, attempt_id, user)
    try:
        late = quizzes.submit(db, attempt, body.answers)
    except quizzes.QuizError as e:
        raise http_error(e)
    return attempt_out(attempt, late=late)


@router.get("/leaderboard", response_model=list[QuizLeaderRow])
def leaderboard(db: DB, _: CurrentUser, month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")):
    """Quiz points only; separate from the challenge leaderboard and streaks."""
    q = (
        select(User.id, User.name, func.sum(QuizAttempt.points_awarded), func.count(QuizAttempt.id))
        .join(QuizAttempt, QuizAttempt.user_id == User.id)
        .join(QuizModel, QuizModel.id == QuizAttempt.quiz_id)
        .where(QuizAttempt.submitted_at.is_not(None))
        .group_by(User.id, User.name)
    )
    if month:
        q = q.where(QuizModel.period_key.startswith(month))
    rows = sorted(db.execute(q).all(), key=lambda r: (-(r[2] or 0), r[1]))
    out, rank, prev = [], 0, None
    for i, (uid, name, points, taken) in enumerate(rows, start=1):
        if points != prev:
            rank, prev = i, points
        out.append(QuizLeaderRow(rank=rank, user_id=uid, name=name, points=int(points or 0), quizzes_taken=taken))
    return out
