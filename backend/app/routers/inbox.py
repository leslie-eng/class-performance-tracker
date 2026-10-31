"""The signed-in user's in-app notifications (the bell). Only ever your own messages."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update

from app.deps import DB, CurrentUser
from app.models import InboxMessage, as_utc, utcnow

router = APIRouter(prefix="/inbox", tags=["inbox"])


class InboxItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event: str
    title: str
    body: str
    link: str | None
    challenge_id: int | None
    created_at: datetime
    read_at: datetime | None


class InboxPage(BaseModel):
    items: list[InboxItem]
    unread: int


class UnreadCount(BaseModel):
    unread: int


def unread_count(db: DB, user_id: int) -> int:
    return db.scalar(select(func.count()).where(InboxMessage.user_id == user_id, InboxMessage.read_at.is_(None))) or 0


def item(m: InboxMessage) -> InboxItem:
    out = InboxItem.model_validate(m)
    return out.model_copy(update={"created_at": as_utc(m.created_at), "read_at": as_utc(m.read_at) if m.read_at else None})


@router.get("", response_model=InboxPage)
def list_inbox(db: DB, user: CurrentUser, unread_only: bool = False, limit: int = Query(20, ge=1, le=100),
               before_id: int | None = Query(None, description="Paging: return messages older than this id")):
    q = select(InboxMessage).where(InboxMessage.user_id == user.id)
    if unread_only:
        q = q.where(InboxMessage.read_at.is_(None))
    if before_id is not None:
        q = q.where(InboxMessage.id < before_id)
    rows = db.scalars(q.order_by(InboxMessage.id.desc()).limit(limit)).all()
    return InboxPage(items=[item(m) for m in rows], unread=unread_count(db, user.id))


@router.get("/unread-count", response_model=UnreadCount)
def get_unread_count(db: DB, user: CurrentUser):
    """Cheap enough to poll for the bell badge."""
    return UnreadCount(unread=unread_count(db, user.id))


@router.post("/{message_id}/read", response_model=InboxItem)
def mark_read(message_id: int, db: DB, user: CurrentUser):
    m = db.get(InboxMessage, message_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if m.read_at is None:
        m.read_at = utcnow()
        db.commit()
    return item(m)


@router.post("/read-all", response_model=UnreadCount)
def mark_all_read(db: DB, user: CurrentUser):
    db.execute(
        update(InboxMessage)
        .where(InboxMessage.user_id == user.id, InboxMessage.read_at.is_(None))
        .values(read_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return UnreadCount(unread=0)
