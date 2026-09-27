"""Lag detection and WhatsApp nudges (design doc section 8)."""

import logging
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Challenge,
    Enrollment,
    EnrollmentStats,
    Notification,
    NotificationStatus,
    NotificationType,
    Submission,
    User,
)
from app.scoring import compute_streaks, day_number_for, recompute_enrollment, rules_for
from app.services.whatsapp import WhatsAppError, WhatsAppSender, get_sender

log = logging.getLogger(__name__)

DEFAULT_LAG_MESSAGE = (
    "Hi {name}! You've missed {days_missed} days of {challenge}"
    "{streak_clause}. The group is averaging {group_avg} points and you're on {points}. "
    "Submit today's task to get back on pace!"
)


@dataclass
class LaggingMember:
    user_id: int
    name: str
    challenge_id: int
    challenge: str
    days_missed: int
    streak_lost: int
    points: int
    notified: bool = False
    skipped_reason: str | None = None


def active_challenges(db: Session, today: date) -> list[Challenge]:
    return list(
        db.scalars(select(Challenge).where(Challenge.start_date <= today, Challenge.end_date >= today)).all()
    )


def _group_average(db: Session, challenge_id: int) -> float:
    avg = db.scalar(
        select(func.avg(EnrollmentStats.total_points))
        .join(Enrollment, Enrollment.id == EnrollmentStats.enrollment_id)
        .where(Enrollment.challenge_id == challenge_id)
    )
    return round(float(avg or 0), 1)


def find_lagging(db: Session, today: date) -> list[LaggingMember]:
    lagging: list[LaggingMember] = []
    for challenge in active_challenges(db, today):
        rules = rules_for(challenge)
        enrollments = db.scalars(
            select(Enrollment)
            .where(Enrollment.challenge_id == challenge.id)
            .options(selectinload(Enrollment.user), selectinload(Enrollment.stats))
        ).all()
        for enrollment in enrollments:
            stats = recompute_enrollment(db, enrollment, today)
            # Nobody is behind for days before they joined or before the challenge began.
            joined = max(challenge.start_date, enrollment.joined_at.date())
            last_day = stats.last_submission_date or (joined - timedelta(days=1))
            days_missed = (today - last_day).days - 1  # excluding today
            if days_missed < rules["lag_threshold"]:
                continue
            days = set(
                db.scalars(
                    select(Submission.day_number).where(
                        Submission.enrollment_id == enrollment.id, Submission.counts_for_streak
                    )
                ).all()
            )
            runs = compute_streaks(days, day_number_for(challenge, today), rules).runs
            lagging.append(
                LaggingMember(
                    user_id=enrollment.user.id,
                    name=enrollment.user.name,
                    challenge_id=challenge.id,
                    challenge=challenge.name,
                    days_missed=days_missed,
                    streak_lost=runs[-1][1] if runs else 0,
                    points=stats.total_points,
                )
            )
    db.flush()
    return lagging


def build_lag_message(member: LaggingMember, group_avg: float, template: str | None = None) -> str:
    streak_clause = f" and your {member.streak_lost}-day streak ended" if member.streak_lost > 1 else ""
    return (template or DEFAULT_LAG_MESSAGE).format(
        name=member.name.split()[0],
        challenge=member.challenge,
        days_missed=member.days_missed,
        streak_lost=member.streak_lost,
        streak_clause=streak_clause,
        group_avg=group_avg,
        points=member.points,
    )


def _already_sent(db: Session, user_id: int, challenge_id: int | None, kind: NotificationType, on: date) -> bool:
    return (
        db.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.challenge_id == challenge_id,
                Notification.type == kind,
                Notification.sent_on == on,
                Notification.status == NotificationStatus.sent,
            )
        )
        is not None
    )


def _deliver(
    db: Session,
    sender: WhatsAppSender,
    user: User,
    challenge_id: int | None,
    kind: NotificationType,
    message: str,
    today: date,
) -> bool:
    status, error = NotificationStatus.sent, None
    try:
        sender.send(user.phone_number, message)
    except WhatsAppError as e:
        status, error = NotificationStatus.failed, str(e)
        log.warning("WhatsApp send to user %s failed: %s", user.id, e)
    db.add(
        Notification(
            user_id=user.id,
            challenge_id=challenge_id,
            type=kind,
            message_sent=message,
            sent_on=today,
            status=status,
            error=error,
        )
    )
    return status == NotificationStatus.sent


def run_lag_check(db: Session, today: date, dry_run: bool = False, sender: WhatsAppSender | None = None) -> list[dict]:
    sender = sender or get_sender()
    lagging = find_lagging(db, today)
    averages: dict[int, float] = {}
    for member in lagging:
        user = db.get(User, member.user_id)
        challenge = db.get(Challenge, member.challenge_id)
        if not (user.phone_number and user.whatsapp_opt_in):
            member.skipped_reason = "no WhatsApp opt-in"
            continue
        if _already_sent(db, user.id, challenge.id, NotificationType.lagging_alert, today):
            member.skipped_reason = "already nudged today"
            continue
        if challenge.id not in averages:
            averages[challenge.id] = _group_average(db, challenge.id)
        message = build_lag_message(member, averages[challenge.id], rules_for(challenge).get("lag_message"))
        if dry_run:
            member.skipped_reason = f"dry run: {message}"
            continue
        member.notified = _deliver(db, sender, user, challenge.id, NotificationType.lagging_alert, message, today)
    db.commit()
    return [asdict(m) for m in lagging]


def run_weekly_digest(db: Session, today: date, dry_run: bool = False, sender: WhatsAppSender | None = None) -> str:
    sender = sender or get_sender()
    lagging = find_lagging(db, today)
    if lagging:
        lines = [f"ClassTrack weekly digest ({today:%d %b}): {len(lagging)} lagging"]
        lines += [f"- {m.name} ({m.challenge}): {m.days_missed} days missed" for m in lagging]
    else:
        lines = [f"ClassTrack weekly digest ({today:%d %b}): everyone is on pace!"]
    message = "\n".join(lines)
    if not dry_run:
        admins = db.scalars(select(User).where(User.is_admin, User.phone_number.is_not(None))).all()
        for admin in admins:
            if not _already_sent(db, admin.id, None, NotificationType.weekly_digest, today):
                _deliver(db, sender, admin, None, NotificationType.weekly_digest, message, today)
    db.commit()
    return message
