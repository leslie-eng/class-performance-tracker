"""Fill an empty database with a demo cohort so every screen has something to show.

    python -m scripts.seed_demo

Creates demo@classtrack.dev / password123 (admin) plus eight classmates. Never
run this against a real database: it refuses if any users already exist.
"""

import random
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select

from app.db import SessionLocal
from app.deps import today
from app.models import (
    ApplicationSource,
    ApplicationStatus,
    Challenge,
    Enrollment,
    GradingStatus,
    JobApplication,
    Submission,
    SubmissionType,
    TaskTypes,
    User,
)
from app.scoring import date_for_day, recompute_enrollment
from app.security import hash_password

PEOPLE = [
    ("Demo Student", "demo@classtrack.dev", 0.85),
    ("Sarah Jenkins", "sarah@classtrack.dev", 1.0),
    ("Alex Chen", "alex@classtrack.dev", 0.95),
    ("David Kim", "david@classtrack.dev", 0.9),
    ("Elena Rostova", "elena@classtrack.dev", 0.8),
    ("Marcus Vance", "marcus@classtrack.dev", 0.7),
    ("Chloe Dupont", "chloe@classtrack.dev", 0.6),
    ("Liam O'Connor", "liam@classtrack.dev", 0.45),
    ("Amina Otieno", "amina@classtrack.dev", 0.3),
]

CODE = '''def two_sum(nums: list[int], target: int) -> tuple[int, int]:
    """Return indices of the two numbers that add up to target."""
    seen: dict[int, int] = {}
    for i, n in enumerate(nums):
        if target - n in seen:
            return seen[target - n], i
        seen[n] = i
    raise ValueError("no solution")
'''

ARTICLES = [
    ("Mastering Database Connection Pools in SQLAlchemy 2.0", 9, {"clarity": 3, "technical_accuracy": 3, "depth": 2, "originality": 1}),
    ("Understanding Python Decorators From Scratch", 7, {"clarity": 3, "technical_accuracy": 2, "depth": 1, "originality": 1}),
    ("Async IO in FastAPI: What Actually Runs in Parallel", 8, {"clarity": 2, "technical_accuracy": 3, "depth": 2, "originality": 1}),
]


def main() -> None:
    random.seed(7)
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            raise SystemExit("Database already has users; refusing to seed demo data.")

        t = today()
        challenge = Challenge(
            name="100 Days of Python",
            description="One solved problem or one technical article every day.",
            start_date=t - timedelta(days=24),
            end_date=t + timedelta(days=75),
            task_types_allowed=TaskTypes.both,
            scoring_rules={},
        )
        db.add(challenge)
        db.flush()

        for idx, (name, email, consistency) in enumerate(PEOPLE):
            user = User(
                name=name,
                email=email,
                password_hash=hash_password("password123"),
                is_admin=idx == 0,
                joined_at=datetime.now(timezone.utc) - timedelta(days=30),
            )
            db.add(user)
            db.flush()
            enrollment = Enrollment(user_id=user.id, challenge_id=challenge.id, joined_at=user.joined_at)
            db.add(enrollment)
            db.flush()

            last_day = 25 if idx else 24  # the demo user hasn't submitted today yet
            for day in range(1, last_day + 1):
                # Recent days follow the member's consistency; everyone keeps a streak going except the stragglers.
                if random.random() > consistency and day < last_day - 3:
                    continue
                if idx >= 7 and day > last_day - 4:
                    continue
                when = datetime.combine(date_for_day(challenge, day), time(19, 30), tzinfo=timezone.utc)
                if day % 6 == 0:
                    title, score, breakdown = ARTICLES[(day // 6 + idx) % len(ARTICLES)]
                    slug = title.lower().replace(" ", "-").replace(":", "")
                    db.add(
                        Submission(
                            enrollment_id=enrollment.id,
                            day_number=day,
                            submission_type=SubmissionType.article,
                            content=f"https://dev.to/{email.split('@')[0]}/{slug}",
                            grading_status=GradingStatus.done,
                            ai_score=float(score),
                            ai_breakdown=breakdown,
                            ai_feedback="Clear structure and well-chosen examples. The benchmark section would be stronger with numbers from a realistic workload.",
                            ai_details={
                                "title": title,
                                "strengths": [
                                    "The opening example makes the core problem concrete before any theory.",
                                    "Code snippets are short, runnable and build on each other.",
                                ],
                                "improvements": [
                                    "Show what happens under load, e.g. when the pool is exhausted.",
                                    "Link to the official docs for the parameters you tune.",
                                ],
                            },
                            submitted_at=when,
                        )
                    )
                else:
                    db.add(
                        Submission(
                            enrollment_id=enrollment.id,
                            day_number=day,
                            submission_type=SubmissionType.code,
                            content=CODE,
                            language="python",
                            problem_link="https://leetcode.com/problems/two-sum/",
                            submitted_at=when,
                        )
                    )
            db.flush()
            recompute_enrollment(db, enrollment, t)

        demo = db.scalar(select(User).where(User.email == "demo@classtrack.dev"))
        jobs = [
            ("Safaricom", "Backend Engineer", ApplicationStatus.interview, ApplicationSource.referral, 12, True),
            ("Andela", "Python Developer", ApplicationStatus.oa, ApplicationSource.linkedin, 6, False),
            ("Twiga Foods", "Data Engineer", ApplicationStatus.applied, ApplicationSource.company_site, 3, False),
            ("Cellulant", "Platform Engineer", ApplicationStatus.applied, ApplicationSource.linkedin, 1, False),
            ("M-KOPA", "Software Engineer", ApplicationStatus.offer, ApplicationSource.referral, 20, True),
            ("Acme Corp", "SWE Intern", ApplicationStatus.rejected, ApplicationSource.other, 25, False),
        ]
        for company, role, status, source, ago, public in jobs:
            db.add(
                JobApplication(
                    user_id=demo.id,
                    company=company,
                    role=role,
                    status=status,
                    source=source,
                    date_applied=t - timedelta(days=ago),
                    follow_up_date=t + timedelta(days=2) if status in (ApplicationStatus.applied, ApplicationStatus.oa) else None,
                    notes="Recruiter replied within a week." if status == ApplicationStatus.interview else None,
                    is_public=public,
                )
            )
        db.commit()
        print("Seeded demo cohort. Sign in as demo@classtrack.dev / password123")


if __name__ == "__main__":
    main()
