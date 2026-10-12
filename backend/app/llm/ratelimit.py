"""Per-user limit on AI work, so a loop or abuse can't burn OpenRouter credit.

AI_RATE_LIMIT_PER_HOUR calls per member per sliding hour; admins get
AI_RATE_LIMIT_ADMIN_MULTIPLIER times that. Counts live in this process's memory: they
reset on restart and aren't shared between instances, which is fine for one Render
instance (use a DB- or Redis-backed counter if you scale out).

Endpoints that save a member's work use `allow()` and skip only the AI step when over the
limit (the work is saved and can be retried). Endpoints that only run AI use `take()`,
which raises 429.
"""

import threading
import time
from collections import deque
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.config import get_settings
from app.deps import CurrentUser
from app.models import User

WINDOW_SECONDS = 3600


class RateLimiter:
    def __init__(self, window: float = WINDOW_SECONDS, clock=time.monotonic):
        self.window, self.clock = window, clock
        self._hits: dict[int, deque[float]] = {}
        self._lock = threading.Lock()

    def try_take(self, key: int, limit: int, n: int = 1) -> float | None:
        """Records n hits and returns None, or returns seconds until there's room (nothing recorded)."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) + n > limit:
                free_at = hits[len(hits) + n - limit - 1] + self.window if n <= limit else now + self.window
                return max(1.0, free_at - now)
            hits.extend([now] * n)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def limit_for(user: User) -> int:
    s = get_settings()
    return s.ai_rate_limit_per_hour * (s.ai_rate_limit_admin_multiplier if user.is_admin else 1)


class AIQuota:
    def __init__(self, user: User):
        self.user = user
        self.wait_seconds: float | None = None

    def allow(self, n: int = 1) -> bool:
        self.wait_seconds = limiter.try_take(self.user.id, limit_for(self.user), n)
        return self.wait_seconds is None

    @property
    def message(self) -> str:
        minutes = max(1, round((self.wait_seconds or 60) / 60))
        return (f"You've reached the AI limit ({limit_for(self.user)} per hour). "
                f"Try again in about {minutes} minute{'s' if minutes != 1 else ''}.")

    def take(self, n: int = 1) -> None:
        if not self.allow(n):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, self.message,
                headers={"Retry-After": str(int(self.wait_seconds or 60))},
            )


def get_ai_quota(user: CurrentUser) -> AIQuota:
    return AIQuota(user)


Quota = Annotated[AIQuota, Depends(get_ai_quota)]
