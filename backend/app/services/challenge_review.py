"""Challenge approval workflow: the only code that changes a challenge's status.

    pending -> approved   (admin)
    pending -> rejected   (admin, reason required)
    pending -> cancelled  (the member who proposed it)

Nothing leaves approved, rejected or cancelled. Every move (and a member's edit) is one
conditional UPDATE ... WHERE status = 'pending', so when two admins click at once, or an
admin approves while the member cancels, exactly one wins and the other gets a 409 that
says what happened.
"""

from datetime import date

from sqlalchemy import or_, true, update
from sqlalchemy.orm import Session

from app.models import Challenge, ChallengeStatus, User, utcnow
from app.services import inbox

TRANSITIONS: dict[ChallengeStatus, set[ChallengeStatus]] = {
    ChallengeStatus.pending: {ChallengeStatus.approved, ChallengeStatus.rejected, ChallengeStatus.cancelled},
    ChallengeStatus.approved: set(),
    ChallengeStatus.rejected: set(),
    ChallengeStatus.cancelled: set(),
}

MAX_PENDING_PER_MEMBER = 3


class ReviewError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def visible_filter(user: User):
    """Approved challenges for everyone; members also see their own proposals; admins see all."""
    if user.is_admin:
        return true()
    return or_(Challenge.status == ChallengeStatus.approved, Challenge.created_by == user.id)


def can_see(challenge: Challenge, user: User) -> bool:
    return user.is_admin or challenge.status == ChallengeStatus.approved or challenge.created_by == user.id


def _settled_message(challenge: Challenge, for_admin: bool) -> str:
    state = challenge.status.value
    if challenge.status == ChallengeStatus.cancelled:
        return "This challenge was cancelled by the member who proposed it"
    if for_admin and challenge.reviewer is not None:
        when = challenge.reviewed_at.strftime("%Y-%m-%d %H:%M UTC") if challenge.reviewed_at else ""
        return f"Already {state} by {challenge.reviewer.name} {when}".rstrip()
    return f"This challenge has already been {state}"


def check_transition(challenge: Challenge, target: ChallengeStatus, for_admin: bool) -> None:
    if target not in TRANSITIONS[challenge.status]:
        if challenge.status == ChallengeStatus.pending:
            raise ReviewError(409, f"A pending challenge can't be set to {target.value}")
        raise ReviewError(409, _settled_message(challenge, for_admin))


def _conditional_update(db: Session, challenge: Challenge, values: dict, for_admin: bool) -> Challenge:
    """UPDATE ... WHERE status='pending'. Losing a race raises 409 with the winner's outcome."""
    result = db.execute(
        update(Challenge)
        .where(Challenge.id == challenge.id, Challenge.status == ChallengeStatus.pending)
        .values(**values, updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        db.refresh(challenge)
        raise ReviewError(409, _settled_message(challenge, for_admin))
    db.commit()
    db.refresh(challenge)
    return challenge


def _tell_creator(db: Session, challenge: Challenge, admin: User, event: str, payload: dict) -> None:
    """The member hears about the decision (not when an admin reviews their own proposal)."""
    if challenge.creator is not None and challenge.created_by != admin.id:
        inbox.notify(db, challenge.creator, event, {"challenge_id": challenge.id, "name": challenge.name, **payload})
        db.commit()


def approve(db: Session, challenge: Challenge, admin: User, note: str | None, today: date) -> Challenge:
    check_transition(challenge, ChallengeStatus.approved, for_admin=True)
    if challenge.end_date < today:
        raise ReviewError(409, "This challenge's end date has passed; reject it and ask for new dates")
    _conditional_update(db, challenge, {
        "status": ChallengeStatus.approved, "reviewed_by": admin.id, "reviewed_at": utcnow(),
        "review_note": (note or "").strip() or None,
    }, for_admin=True)
    _tell_creator(db, challenge, admin, "challenge_approved", {"note": challenge.review_note})
    return challenge


def reject(db: Session, challenge: Challenge, admin: User, note: str) -> Challenge:
    note = (note or "").strip()
    if not note:
        raise ReviewError(422, "A reason is required to reject a challenge")
    check_transition(challenge, ChallengeStatus.rejected, for_admin=True)
    _conditional_update(db, challenge, {
        "status": ChallengeStatus.rejected, "reviewed_by": admin.id, "reviewed_at": utcnow(), "review_note": note,
    }, for_admin=True)
    _tell_creator(db, challenge, admin, "challenge_rejected", {"reason": note})
    return challenge


def cancel(db: Session, challenge: Challenge, member: User) -> Challenge:
    if challenge.created_by != member.id:
        raise ReviewError(404, "Proposal not found")
    check_transition(challenge, ChallengeStatus.cancelled, for_admin=False)
    return _conditional_update(db, challenge, {"status": ChallengeStatus.cancelled}, for_admin=False)


def edit(db: Session, challenge: Challenge, member: User, values: dict) -> Challenge:
    """Members edit only while pending. Nothing has been reviewed yet, so there's no review to reset."""
    if challenge.created_by != member.id:
        raise ReviewError(404, "Proposal not found")
    if challenge.status != ChallengeStatus.pending:
        raise ReviewError(409, f"Only pending proposals can be edited; this one is {challenge.status.value}")
    if not values:
        return challenge
    return _conditional_update(db, challenge, values, for_admin=False)
