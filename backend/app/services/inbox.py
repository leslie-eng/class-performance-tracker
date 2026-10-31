"""notify(user, event, payload): the single entry point for user notifications.

Each event has one template that builds a title, body and in-app link from a small
payload; channels deliver it. Today the only channel is the in-app inbox (the bell);
email or WhatsApp can be appended to CHANNELS without touching the workflow code.

Templates only use what the event needs (a challenge name, dates, the reviewer's reason).
They never include grades, scores, emails or phone numbers. A channel failure is logged
and never breaks the action that triggered it.
"""

import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InboxMessage, User

log = logging.getLogger(__name__)

NAME_MAX = 120
REASON_MAX = 500


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    link: str | None
    challenge_id: int | None = None


def _clip(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _challenge_submitted(p: dict) -> Message:
    return Message(
        "New challenge to review",
        f"{_clip(p['proposer'], 60)} proposed “{_clip(p['name'], NAME_MAX)}” ({p['start_date']} to {p['end_date']}).",
        "/admin/challenges", p["challenge_id"],
    )


def _challenge_approved(p: dict) -> Message:
    note = f" Note from the reviewer: {_clip(p['note'], REASON_MAX)}" if p.get("note") else ""
    return Message(
        "Your challenge was approved",
        f"“{_clip(p['name'], NAME_MAX)}” is now open for everyone to join.{note}",
        "/join", p["challenge_id"],
    )


def _challenge_rejected(p: dict) -> Message:
    return Message(
        "Your challenge wasn't approved",
        f"“{_clip(p['name'], NAME_MAX)}”: {_clip(p['reason'], REASON_MAX)}",
        "/challenges/proposals", p["challenge_id"],
    )


TEMPLATES: dict[str, Callable[[dict], Message]] = {
    "challenge_submitted": _challenge_submitted,
    "challenge_approved": _challenge_approved,
    "challenge_rejected": _challenge_rejected,
}


def _in_app(db: Session, user: User, event: str, message: Message) -> None:
    db.add(InboxMessage(user_id=user.id, event=event, title=message.title, body=message.body,
                        link=message.link, challenge_id=message.challenge_id))


# Add e.g. an email or WhatsApp sender here; each gets (db, user, event, message).
CHANNELS: list[Callable[[Session, User, str, Message], None]] = [_in_app]


def notify(db: Session, user: User, event: str, payload: dict) -> None:
    """Queue `event` for `user` on every channel. The caller commits. Never raises."""
    message = TEMPLATES[event](payload)  # an unknown event is a programming error: fail loudly in tests
    for channel in CHANNELS:
        try:
            channel(db, user, event, message)
        except Exception:
            log.warning("Notification channel %s failed for user %s (%s)", channel.__name__, user.id, event, exc_info=True)
    log.info("Notified user %s: %s", user.id, event)


def notify_admins(db: Session, event: str, payload: dict, exclude_user_id: int | None = None) -> int:
    admins = db.scalars(select(User).where(User.is_admin)).all()
    count = 0
    for admin in admins:
        if admin.id != exclude_user_id:
            notify(db, admin, event, payload)
            count += 1
    return count
