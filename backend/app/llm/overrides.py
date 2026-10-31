"""Per-task model choices made by admins (llm_task_models table).

Read on every AI call, so they're cached for CACHE_SECONDS and cleared when an admin
changes one. With more than one API instance, other instances pick a change up within
CACHE_SECONDS.
"""

import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LLMTaskModel

CACHE_SECONDS = 30.0

_lock = threading.Lock()
_cache: dict[str, str] | None = None
_loaded_at = 0.0


def get_overrides() -> dict[str, str]:
    global _cache, _loaded_at
    with _lock:
        if _cache is not None and time.monotonic() - _loaded_at < CACHE_SECONDS:
            return _cache
    from app.db import SessionLocal

    with SessionLocal() as db:
        rows = dict(db.execute(select(LLMTaskModel.task, LLMTaskModel.model)).all())
    with _lock:
        _cache, _loaded_at = rows, time.monotonic()
    return rows


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def set_override(db: Session, task: str, model_id: str | None, user_id: int) -> None:
    """model_id=None removes the choice (back to the env settings)."""
    row = db.get(LLMTaskModel, task)
    if model_id is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(LLMTaskModel(task=task, model=model_id, updated_by=user_id))
    else:
        row.model, row.updated_by = model_id, user_id
    db.commit()
    clear_cache()
