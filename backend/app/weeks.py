"""Which Friday Drop a moment belongs to.

A week is keyed by the date of its drop (WEEKLY_DROP_DAY at WEEKLY_DROP_HOUR, in
TIMEZONE). The *current* drop is the latest one that has already happened; notes
and project proposals collected before the next drop go to the *upcoming* one.
"""

from datetime import date, datetime, timedelta

from app.config import get_settings

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def now_local() -> datetime:
    return datetime.now(get_settings().tz)


def drop_weekday() -> int:
    return DAYS[get_settings().weekly_drop_day.strip().lower()[:3]]


def current_week_key(now: datetime | None = None) -> date:
    """Date of the most recent drop at or before `now`."""
    now = (now or now_local()).astimezone(get_settings().tz)
    d = now.date() - timedelta(days=(now.weekday() - drop_weekday()) % 7)
    if d == now.date() and now.hour < get_settings().weekly_drop_hour:
        d -= timedelta(days=7)  # drop day, but before the drop hour
    return d


def upcoming_week_key(now: datetime | None = None) -> date:
    return current_week_key(now) + timedelta(days=7)


def is_drop_due(now: datetime | None = None) -> bool:
    """True on drop day once the drop hour has passed."""
    now = (now or now_local()).astimezone(get_settings().tz)
    return current_week_key(now) == now.date()


def month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def month_end(month: str) -> date:
    y, m = map(int, month.split("-"))
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def is_monthly_drop(week_key: date) -> bool:
    if get_settings().monthly_quiz_week == "last":
        return (week_key + timedelta(days=7)).month != week_key.month
    return week_key.day <= 7


def current_month_key(now: datetime | None = None) -> str:
    """Month of the latest monthly drop: monthly quizzes stay open until the next one."""
    week = current_week_key(now)
    for _ in range(6):
        if is_monthly_drop(week):
            return month_key(week)
        week -= timedelta(days=7)
    return month_key(week)
