from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.deps import DB, AdminUser, CurrentUser, today
from app.models import Challenge, Enrollment
from app.schemas import ChallengeIn, ChallengeOut, ChallengeUpdate, EnrollmentOut, UserOut
from app.scoring import recompute_enrollment

router = APIRouter(prefix="/challenges", tags=["challenges"])


def get_challenge_or_404(db: DB, challenge_id: int) -> Challenge:
    challenge = db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challenge not found")
    return challenge


@router.post("", response_model=ChallengeOut, status_code=status.HTTP_201_CREATED)
def create_challenge(body: ChallengeIn, db: DB, _: AdminUser):
    challenge = Challenge(**body.model_dump(exclude={"scoring_rules"}), scoring_rules=body.scoring_rules.overrides())
    db.add(challenge)
    db.commit()
    return challenge


@router.get("", response_model=list[ChallengeOut])
def list_challenges(db: DB, _: CurrentUser, active_only: bool = False):
    q = select(Challenge).order_by(Challenge.start_date.desc())
    if active_only:
        t = today()
        q = q.where(Challenge.start_date <= t, Challenge.end_date >= t)
    return db.scalars(q).all()


@router.get("/mine", response_model=list[ChallengeOut])
def my_challenges(db: DB, user: CurrentUser):
    return db.scalars(
        select(Challenge)
        .join(Enrollment, Enrollment.challenge_id == Challenge.id)
        .where(Enrollment.user_id == user.id)
        .order_by(Challenge.start_date.desc())
    ).all()


@router.get("/{challenge_id}", response_model=ChallengeOut)
def get_challenge(challenge_id: int, db: DB, _: CurrentUser):
    return get_challenge_or_404(db, challenge_id)


@router.patch("/{challenge_id}", response_model=ChallengeOut)
def update_challenge(challenge_id: int, body: ChallengeUpdate, db: DB, _: AdminUser):
    challenge = get_challenge_or_404(db, challenge_id)
    data = body.model_dump(exclude_unset=True, exclude={"scoring_rules"})
    for field, value in data.items():
        setattr(challenge, field, value)
    if body.scoring_rules is not None:
        challenge.scoring_rules = {**challenge.scoring_rules, **body.scoring_rules.overrides()}
    if challenge.end_date < challenge.start_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_date must be on or after start_date")
    # Point values or dates may have changed: rebuild everyone's totals.
    for enrollment in challenge.enrollments:
        recompute_enrollment(db, enrollment, today())
    db.commit()
    return challenge


@router.post("/{challenge_id}/enroll", response_model=EnrollmentOut, status_code=status.HTTP_201_CREATED)
def enroll(challenge_id: int, db: DB, user: CurrentUser):
    challenge = get_challenge_or_404(db, challenge_id)
    if challenge.end_date < today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This challenge has ended")
    enrollment = Enrollment(user_id=user.id, challenge_id=challenge.id)
    db.add(enrollment)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Already enrolled")
    recompute_enrollment(db, enrollment, today())
    db.commit()
    return enrollment


@router.delete("/{challenge_id}/enroll", status_code=status.HTTP_204_NO_CONTENT)
def leave(challenge_id: int, db: DB, user: CurrentUser):
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.challenge_id == challenge_id, Enrollment.user_id == user.id)
    )
    if enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not enrolled")
    db.delete(enrollment)
    db.commit()


@router.get("/{challenge_id}/members", response_model=list[UserOut])
def challenge_members(challenge_id: int, db: DB, _: AdminUser):
    get_challenge_or_404(db, challenge_id)
    enrollments = db.scalars(
        select(Enrollment).where(Enrollment.challenge_id == challenge_id).options(selectinload(Enrollment.user))
    ).all()
    return [e.user for e in enrollments]
