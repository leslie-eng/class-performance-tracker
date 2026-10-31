"""Admin approval queue for member-proposed challenges, with the review audit trail."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DB, AdminUser, today
from app.models import Challenge, ChallengeStatus, Enrollment
from app.schemas_challenges import AdminChallengeOut, AdminChallengePage, ApproveIn, RejectIn
from app.services import challenge_review as review

router = APIRouter(prefix="/admin/challenges", tags=["admin"])


def admin_out(db: DB, c: Challenge) -> AdminChallengeOut:
    enrolled = db.scalar(select(func.count()).where(Enrollment.challenge_id == c.id)) or 0
    return AdminChallengeOut.model_validate(c).model_copy(update={"enrolled": enrolled})


def get_or_404(db: DB, challenge_id: int) -> Challenge:
    c = db.get(Challenge, challenge_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challenge not found")
    return c


@router.get("", response_model=AdminChallengePage)
def list_challenges(
    db: DB,
    _: AdminUser,
    status_filter: Literal["pending", "approved", "rejected", "cancelled", "all"] = Query("pending", alias="status"),
    q: str | None = Query(None, max_length=100, description="Search in the name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """The approval queue (pending by default, oldest first so nothing waits forever)."""
    query = select(Challenge).options(selectinload(Challenge.creator), selectinload(Challenge.reviewer))
    if status_filter != "all":
        query = query.where(Challenge.status == ChallengeStatus(status_filter))
    if q:
        query = query.where(Challenge.name.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    order = Challenge.created_at.asc() if status_filter == "pending" else Challenge.updated_at.desc()
    rows = db.scalars(query.order_by(order, Challenge.id).limit(limit).offset(offset)).all()
    return AdminChallengePage(items=[admin_out(db, c) for c in rows], total=total, limit=limit, offset=offset)


@router.get("/{challenge_id}", response_model=AdminChallengeOut)
def challenge_detail(challenge_id: int, db: DB, _: AdminUser):
    """Any challenge with who proposed it and who reviewed it, when and why."""
    return admin_out(db, get_or_404(db, challenge_id))


@router.post("/{challenge_id}/approve", response_model=AdminChallengeOut)
def approve(challenge_id: int, body: ApproveIn, db: DB, admin: AdminUser):
    c = get_or_404(db, challenge_id)
    try:
        review.approve(db, c, admin, body.note, today())
    except review.ReviewError as e:
        raise HTTPException(e.status_code, str(e))
    return admin_out(db, c)


@router.post("/{challenge_id}/reject", response_model=AdminChallengeOut)
def reject(challenge_id: int, body: RejectIn, db: DB, admin: AdminUser):
    c = get_or_404(db, challenge_id)
    try:
        review.reject(db, c, admin, body.note)
    except review.ReviewError as e:
        raise HTTPException(e.status_code, str(e))
    return admin_out(db, c)
