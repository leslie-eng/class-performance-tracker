"""Quiz review and on-demand generation (admin only). Admins see answer keys."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import DB, AdminUser
from app.models import LearningMaterial, MaterialStatus, Quiz, QuizAttempt, QuizKind, QuizStatus, as_utc
from app.schemas_materials import AdminQuizOut, AdminQuizSummary, GenerateQuizIn, QuizUpdate, SourceRef
from app.services import quizzes
from app.weeks import current_month_key, current_week_key, month_key

router = APIRouter(prefix="/admin/quizzes", tags=["admin: quizzes"])


def quiz_summary(db: DB, q: Quiz) -> AdminQuizSummary:
    ids = q.source_material_ids or []
    titles = dict(db.execute(select(LearningMaterial.id, LearningMaterial.title).where(LearningMaterial.id.in_(ids))).all()) if ids else {}
    return AdminQuizSummary(
        id=q.id, kind=q.kind.value, period_key=q.period_key, specialization=q.specialization,
        duration_minutes=q.duration_minutes, status=q.status.value, error=q.error, question_count=len(q.questions or []),
        attempts=db.scalar(select(func.count()).where(QuizAttempt.quiz_id == q.id)) or 0,
        sources=[SourceRef(id=i, title=titles.get(i, f"deleted material {i}")) for i in ids],
        created_at=as_utc(q.created_at),
    )


def get_quiz(db: DB, quiz_id: int) -> Quiz:
    q = db.get(Quiz, quiz_id)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    return q


@router.post("/generate", response_model=list[AdminQuizSummary | dict])
def generate(body: GenerateQuizIn, db: DB, _: AdminUser):
    """Generate (or regenerate) quizzes for chosen materials, a module, or a week."""
    kind = QuizKind(body.kind)
    if kind == QuizKind.weekly:
        period = (body.week_key or current_week_key()).isoformat()
    else:
        period = month_key(body.week_key) if body.week_key else current_month_key()
    spec = (body.specialization or "general") if kind == QuizKind.interview else None

    material_ids = body.material_ids
    if body.module and material_ids is None:
        material_ids = list(db.scalars(select(LearningMaterial.id).where(
            LearningMaterial.module == body.module, LearningMaterial.status == MaterialStatus.active)).all())
    if material_ids is not None and not material_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No active materials match that selection")

    results: list[AdminQuizSummary | dict] = []
    for duration in body.durations:
        try:
            q = quizzes.ensure_quiz(db, kind, period, spec, duration, force=True, material_ids=material_ids)
            results.append(quiz_summary(db, q))
        except quizzes.QuizError as e:
            results.append({"duration_minutes": duration, "status": "skipped", "error": str(e)})
    return results


@router.get("", response_model=list[AdminQuizSummary])
def list_quizzes(db: DB, _: AdminUser, kind: QuizKind | None = None, status_filter: QuizStatus | None = None,
                 period_key: str | None = None):
    q = select(Quiz).order_by(Quiz.created_at.desc()).limit(200)
    if kind:
        q = q.where(Quiz.kind == kind)
    if status_filter:
        q = q.where(Quiz.status == status_filter)
    if period_key:
        q = q.where(Quiz.period_key == period_key)
    return [quiz_summary(db, x) for x in db.scalars(q).all()]


@router.get("/{quiz_id}", response_model=AdminQuizOut)
def get_one(quiz_id: int, db: DB, _: AdminUser):
    q = get_quiz(db, quiz_id)
    return AdminQuizOut(**quiz_summary(db, q).model_dump(), questions=q.questions or [])


@router.patch("/{quiz_id}", response_model=AdminQuizOut)
def edit(quiz_id: int, body: QuizUpdate, db: DB, _: AdminUser):
    """Replace the question list (edit or delete questions) and/or publish or unpublish."""
    q = get_quiz(db, quiz_id)
    if body.questions is not None:
        open_attempts = db.scalar(
            select(func.count()).where(QuizAttempt.quiz_id == q.id, QuizAttempt.submitted_at.is_(None))
        )
        if open_attempts:
            raise HTTPException(status.HTTP_409_CONFLICT, "Members are taking this quiz right now; edit it later")
        ids = [x.id for x in body.questions]
        if len(set(ids)) != len(ids):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Question ids must be unique")
        q.questions = [x.model_dump() for x in body.questions]
        if q.status in (QuizStatus.failed, QuizStatus.generating):
            q.status, q.error = QuizStatus.draft, None
    if body.status is not None:
        if not q.questions:
            raise HTTPException(status.HTTP_409_CONFLICT, "This quiz has no questions")
        q.status = QuizStatus(body.status)
    db.commit()
    return get_one(quiz_id, db, _)


@router.post("/{quiz_id}/publish", response_model=AdminQuizOut)
def publish(quiz_id: int, db: DB, _: AdminUser):
    q = get_quiz(db, quiz_id)
    if q.status not in (QuizStatus.draft, QuizStatus.published) or not q.questions:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A {q.status.value} quiz can't be published")
    q.status = QuizStatus.published
    db.commit()
    return get_one(quiz_id, db, _)
