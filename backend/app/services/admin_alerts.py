"""One-line WhatsApp alerts to admins (missing class notes, failed quiz generation)."""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import NotificationType, User
from app.services.notifications import _already_sent, _deliver
from app.services.whatsapp import WhatsAppSender, get_sender, one_line

log = logging.getLogger(__name__)


def notify_admins(db: Session, message: str, on: date, sender: WhatsAppSender | None = None) -> int:
    """Alerts every admin with a phone number, at most once per admin per day. Never raises."""
    message = one_line(message)
    log.warning("Admin alert: %s", message)
    try:
        sender = sender or get_sender()
    except RuntimeError as e:
        log.error("Can't alert admins over WhatsApp: %s", e)
        return 0
    sent = 0
    admins = db.scalars(select(User).where(User.is_admin, User.phone_number.is_not(None))).all()
    for admin in admins:
        if _already_sent(db, admin.id, None, NotificationType.admin_alert, on):
            continue
        sent += _deliver(
            db, sender, admin, None, NotificationType.admin_alert, message, on,
            template=get_settings().whatsapp_weekly_template,
        )
    db.commit()
    return sent
