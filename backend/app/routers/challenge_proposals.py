"""Members propose challenges; they stay pending (not listed, not joinable) until an admin approves."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import DB, CurrentUser, today
from app.models import Challenge, ChallengeStatus
from app.schemas_challenges import ProposalIn, ProposalOut, ProposalUpdate, check_dates
from app.services import challenge_review as review
from app.services import inbox

router = APIRouter(prefix="/challenges/proposals", tags=["challenges"])


def http_error(e: review.ReviewError) -> HTTPException:
    return HTTPException(e.status_code, str(e))


def own_proposal(db: DB, proposal_id: int, user) -> Challenge:
    challenge = db.get(Challenge, proposal_id)
    if challenge is None or challenge.created_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposal not found")
    return challenge


@router.post("", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def propose(body: ProposalIn, db: DB, user: CurrentUser):
    """Saved as pending: not listed, not joinable, until an admin approves it."""
    if body.start_date < today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "start_date can't be in the past")
    pending = db.scalar(select(func.count()).where(
        Challenge.created_by == user.id, Challenge.status == ChallengeStatus.pending))
    if pending >= review.MAX_PENDING_PER_MEMBER:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You already have {pending} proposals waiting for review; cancel one or wait for a decision",
        )
    challenge = Challenge(**body.model_dump(), scoring_rules={}, status=ChallengeStatus.pending, created_by=user.id)
    db.add(challenge)
    db.flush()
    # Saved in the same transaction as the proposal, so admins can't miss one.
    inbox.notify_admins(db, "challenge_submitted", {
        "challenge_id": challenge.id, "name": challenge.name, "proposer": user.name,
        "start_date": challenge.start_date.isoformat(), "end_date": challenge.end_date.isoformat(),
    }, exclude_user_id=user.id)
    db.commit()
    return challenge


@router.get("/mine", response_model=list[ProposalOut])
def my_proposals(db: DB, user: CurrentUser):
    """Every challenge I proposed, in any status, newest first."""
    return db.scalars(
        select(Challenge).where(Challenge.created_by == user.id).order_by(Challenge.created_at.desc(), Challenge.id.desc())
    ).all()


@router.patch("/{proposal_id}", response_model=ProposalOut)
def edit_proposal(proposal_id: int, body: ProposalUpdate, db: DB, user: CurrentUser):
    challenge = own_proposal(db, proposal_id, user)
    values = body.model_dump(exclude_unset=True)
    if "name" in values and not values["name"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "name can't be empty")
    start, end = values.get("start_date", challenge.start_date), values.get("end_date", challenge.end_date)
    try:
        check_dates(start, end)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
    if "start_date" in values and start < today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "start_date can't be in the past")
    try:
        return review.edit(db, challenge, user, values)
    except review.ReviewError as e:
        raise http_error(e)


@router.post("/{proposal_id}/cancel", response_model=ProposalOut)
def cancel_proposal(proposal_id: int, db: DB, user: CurrentUser):
    challenge = own_proposal(db, proposal_id, user)
    try:
        return review.cancel(db, challenge, user)
    except review.ReviewError as e:
        raise http_error(e)
