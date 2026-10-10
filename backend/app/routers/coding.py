"""Coding exercises. Member code is stored and, if configured, forwarded to an external
sandbox; it is never executed on this host. Members never see hidden tests."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, AdminUser, CurrentUser
from app.models import (
    CodeAttempt,
    CodeDraft,
    CodingExercise,
    ExerciseStatus,
    GradingStatus,
    LearningMaterial,
    RunnerKind,
    User,
    as_utc,
)
from app.schemas_coding import (
    AdminExerciseOut,
    AttemptOut,
    DraftIn,
    ExerciseIn,
    ExerciseOut,
    ExerciseSummary,
    ExerciseUpdate,
    GenerateExercisesIn,
    SubmitIn,
    VerifyIn,
)
from app.services import coding, grading, materials
from app.services.code_runner import RunnerError, get_runner

log = logging.getLogger(__name__)

router = APIRouter(tags=["coding"])


# --- members --------------------------------------------------------------------------

def attempt_out(a: CodeAttempt) -> AttemptOut:
    return AttemptOut(
        id=a.id, exercise_id=a.exercise_id, passed_count=a.passed_count, total_count=a.total_count,
        runner=a.runner.value, verified=a.verified, results=a.results, runner_error=a.runner_error,
        grading_status=a.grading_status.value, ai_feedback=a.ai_feedback, points_awarded=a.points_awarded,
        created_at=as_utc(a.created_at),
    )


def published(db: DB, exercise_id: int) -> CodingExercise:
    ex = db.get(CodingExercise, exercise_id)
    if ex is None or ex.status != ExerciseStatus.published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found")
    return ex


def progress(db: DB, user: User) -> dict[int, dict]:
    full_pass = (CodeAttempt.passed_count == CodeAttempt.total_count) & (CodeAttempt.total_count > 0)
    rows = db.execute(
        select(
            CodeAttempt.exercise_id,
            func.count(CodeAttempt.id),
            func.sum(CodeAttempt.points_awarded),
            func.max(case((full_pass, 1), else_=0)),  # max(bool) doesn't exist in Postgres
            func.max(case((full_pass & CodeAttempt.verified, 1), else_=0)),
        )
        .where(CodeAttempt.user_id == user.id)
        .group_by(CodeAttempt.exercise_id)
    ).all()
    return {r[0]: {"attempts": r[1], "points_earned": int(r[2] or 0), "solved": bool(r[3]), "verified": bool(r[4])} for r in rows}


def summary(ex: CodingExercise, mine: dict | None) -> ExerciseSummary:
    return ExerciseSummary(
        id=ex.id, title=ex.title, language=ex.language, difficulty=ex.difficulty, points=ex.points,
        module=ex.module, week_key=ex.week_key, **(mine or {}),
    )


@router.get("/coding/exercises", response_model=list[ExerciseSummary])
def list_exercises(db: DB, user: CurrentUser, module: str | None = None, difficulty: int | None = None):
    q = select(CodingExercise).where(CodingExercise.status == ExerciseStatus.published).order_by(
        CodingExercise.module, CodingExercise.difficulty, CodingExercise.id
    )
    if module:
        q = q.where(CodingExercise.module == module)
    if difficulty:
        q = q.where(CodingExercise.difficulty == difficulty)
    mine = progress(db, user)
    return [summary(ex, mine.get(ex.id)) for ex in db.scalars(q).all()]


@router.get("/coding/exercises/{exercise_id}", response_model=ExerciseOut)
def get_exercise(exercise_id: int, db: DB, user: CurrentUser):
    ex = published(db, exercise_id)
    draft = db.scalar(select(CodeDraft).where(CodeDraft.exercise_id == ex.id, CodeDraft.user_id == user.id))
    recent = db.scalars(
        select(CodeAttempt).where(CodeAttempt.exercise_id == ex.id, CodeAttempt.user_id == user.id)
        .order_by(CodeAttempt.id.desc()).limit(5)
    ).all()
    return ExerciseOut(
        **summary(ex, progress(db, user).get(ex.id)).model_dump(),
        description_md=ex.description_md, starter_code=ex.starter_code, entrypoint=ex.entrypoint,
        time_limit_seconds=ex.time_limit_seconds, visible_tests=coding.visible_tests(ex),
        hidden_test_count=sum(1 for t in ex.tests if t.get("hidden")),
        draft=draft.code if draft else None, draft_updated_at=as_utc(draft.updated_at) if draft else None,
        runner="remote" if get_runner().verifies else "browser",
        unverified_points=int(ex.points * coding.UNVERIFIED_POINTS_FACTOR),
        recent_attempts=[attempt_out(a) for a in recent],
    )


@router.put("/coding/exercises/{exercise_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def save_draft(exercise_id: int, body: DraftIn, db: DB, user: CurrentUser):
    ex = published(db, exercise_id)
    for _ in range(2):
        draft = db.scalar(select(CodeDraft).where(CodeDraft.exercise_id == ex.id, CodeDraft.user_id == user.id))
        if draft:
            draft.code = body.code
        else:
            db.add(CodeDraft(exercise_id=ex.id, user_id=user.id, code=body.code))
        try:
            db.commit()
            break
        except IntegrityError:  # two autosaves raced to create it
            db.rollback()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/coding/exercises/{exercise_id}/submit", response_model=AttemptOut, status_code=status.HTTP_201_CREATED)
def submit(exercise_id: int, body: SubmitIn, db: DB, user: CurrentUser, background: BackgroundTasks):
    ex = published(db, exercise_id)
    if coding.rate_limited(db, user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many submissions; wait a minute and try again")

    attempt = CodeAttempt(exercise_id=ex.id, user_id=user.id, code=body.code, runner=RunnerKind.browser, verified=False)
    runner = get_runner()
    ran_remotely = False
    if runner.verifies:
        try:
            result = runner.run(ex.language, body.code, ex.entrypoint, ex.tests, ex.time_limit_seconds)
            attempt.runner, attempt.verified, ran_remotely = RunnerKind.remote, True, True
            attempt.passed_count, attempt.total_count = result.passed, len(ex.tests)
            attempt.results, attempt.runner_error = coding.member_results(result), result.error
        except RunnerError as e:
            log.warning("Remote runner failed for exercise %s: %s", ex.id, e)
            attempt.runner_error = f"{e}; using your browser results instead"
    if not ran_remotely:
        # Browser runs only see the visible tests, so a "full pass" means all of those.
        visible = len(coding.visible_tests(ex))
        reported = body.browser_results
        attempt.total_count = visible
        attempt.passed_count = min(reported.passed, visible) if reported and reported.total == visible else 0

    full = attempt.total_count > 0 and attempt.passed_count == attempt.total_count
    attempt.points_awarded = coding.points_for(db, ex, user.id, full, attempt.verified)
    attempt.grading_status = GradingStatus.pending
    db.add(attempt)
    db.commit()
    background.add_task(coding.feedback_job, attempt.id)
    return attempt_out(attempt)


@router.get("/coding/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(attempt_id: int, db: DB, user: CurrentUser):
    a = db.get(CodeAttempt, attempt_id)
    if a is None or (a.user_id != user.id and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    return attempt_out(a)


# --- admin -----------------------------------------------------------------------------

def admin_out(ex: CodingExercise) -> AdminExerciseOut:
    return AdminExerciseOut(
        id=ex.id, title=ex.title, description_md=ex.description_md, language=ex.language, starter_code=ex.starter_code,
        entrypoint=ex.entrypoint, tests=ex.tests, difficulty=ex.difficulty, points=ex.points, module=ex.module,
        week_key=ex.week_key, material_id=ex.material_id, time_limit_seconds=ex.time_limit_seconds,
        status=ex.status.value, reference_solution=ex.reference_solution, tests_verified=ex.tests_verified,
        created_at=as_utc(ex.created_at),
    )


def any_exercise(db: DB, exercise_id: int) -> CodingExercise:
    ex = db.get(CodingExercise, exercise_id)
    if ex is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found")
    return ex


def verify_remotely(ex: CodingExercise) -> None:
    """With a remote runner, check the reference solution passes every test. Never runs here."""
    runner = get_runner()
    if not (runner.verifies and ex.reference_solution):
        return
    try:
        result = runner.run(ex.language, ex.reference_solution, ex.entrypoint, ex.tests, ex.time_limit_seconds)
        ex.tests_verified = result.passed == len(ex.tests) and not result.error
    except RunnerError as e:
        log.warning("Couldn't verify exercise %s remotely: %s", ex.id, e)
        ex.tests_verified = False


@router.get("/admin/exercises", response_model=list[AdminExerciseOut])
def admin_list(db: DB, _: AdminUser):
    return [admin_out(ex) for ex in db.scalars(select(CodingExercise).order_by(CodingExercise.created_at.desc())).all()]


@router.get("/admin/exercises/{exercise_id}", response_model=AdminExerciseOut)
def admin_get(exercise_id: int, db: DB, _: AdminUser):
    return admin_out(any_exercise(db, exercise_id))


@router.post("/admin/exercises", response_model=AdminExerciseOut, status_code=status.HTTP_201_CREATED)
def admin_create(body: ExerciseIn, db: DB, admin: AdminUser):
    data = body.model_dump()
    data["tests"] = [t.model_dump() for t in body.tests]
    ex = CodingExercise(**data, created_by=admin.id, status=ExerciseStatus.draft)
    verify_remotely(ex)
    db.add(ex)
    db.commit()
    return admin_out(ex)


@router.patch("/admin/exercises/{exercise_id}", response_model=AdminExerciseOut)
def admin_update(exercise_id: int, body: ExerciseUpdate, db: DB, _: AdminUser):
    ex = any_exercise(db, exercise_id)
    fields = body.model_dump(exclude_unset=True)
    new_status = fields.pop("status", None)
    if "tests" in fields:
        fields["tests"] = [t.model_dump() for t in body.tests]
    for name, value in fields.items():
        setattr(ex, name, value)
    if {"tests", "reference_solution", "entrypoint"} & fields.keys():
        ex.tests_verified = False  # needs re-checking
        verify_remotely(ex)
    if new_status:
        ex.status = ExerciseStatus(new_status)
    db.commit()
    return admin_out(ex)


@router.delete("/admin/exercises/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete(exercise_id: int, db: DB, _: AdminUser):
    db.delete(any_exercise(db, exercise_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/exercises/{exercise_id}/publish", response_model=AdminExerciseOut)
def admin_publish(exercise_id: int, db: DB, _: AdminUser):
    ex = any_exercise(db, exercise_id)
    if not coding.visible_tests(ex):
        raise HTTPException(status.HTTP_409_CONFLICT, "Add at least one visible test before publishing")
    ex.status = ExerciseStatus.published
    db.commit()
    return admin_out(ex)


@router.post("/admin/exercises/{exercise_id}/verify", response_model=AdminExerciseOut)
def admin_verify(exercise_id: int, body: VerifyIn, db: DB, _: AdminUser):
    """Record the reference solution's run against all tests. Uses the remote runner when
    configured; otherwise trusts the admin's browser run."""
    ex = any_exercise(db, exercise_id)
    if get_runner().verifies:
        verify_remotely(ex)
    else:
        ex.tests_verified = body.total == len(ex.tests) and body.passed == body.total
    db.commit()
    return admin_out(ex)


@router.post("/admin/exercises/generate", response_model=dict)
def admin_generate(body: GenerateExercisesIn, db: DB, admin: AdminUser):
    """Draft exercises from chosen materials. Drafts always need review and publishing."""
    text, ids = materials.context_from_ids(db, body.material_ids)
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "None of those materials are active")
    try:
        generated, dropped = coding.generate_exercises(text, body.language, body.count)
    except grading.GradingError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    first = db.get(LearningMaterial, ids[0])
    created = []
    for data in generated:
        ex = CodingExercise(
            **data, points=10 * data["difficulty"], module=first.module if first else "", week_key=first.week_key if first else None,
            material_id=ids[0], created_by=admin.id, status=ExerciseStatus.draft, tests_verified=False,
        )
        verify_remotely(ex)
        db.add(ex)
        created.append(ex)
    db.commit()
    log.info("Generated %d exercise drafts from materials %s (%d dropped)", len(created), ids, len(dropped))
    return {"created": [admin_out(ex).model_dump(mode="json") for ex in created], "dropped": dropped}
