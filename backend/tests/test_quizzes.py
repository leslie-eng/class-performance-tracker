from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Notification, NotificationType, Quiz, QuizAttempt, QuizStatus, User, WeeklyBrief, utcnow
from app.services import grading
from app.services.quizzes import DURATION_QUESTIONS, GenQuiz, difficulty_band
from app.weeks import current_week_key
from tests.conftest import register
from tests.fakes import FakeClaude, valid_questions


@pytest.fixture
def claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(grading, "_parse", fake)
    return fake


@pytest.fixture
def notes(db):
    db.add(WeeklyBrief(week_key=current_week_key(), source_notes="Decorators, generators and context managers."))
    db.commit()


def start(client, headers, duration=10, kind="weekly"):
    return client.post(f"/quizzes/{kind}/start?duration={duration}", headers=headers)


@pytest.mark.parametrize("duration", [10, 20, 30])
def test_question_counts_and_difficulty_ramp(client, claude, notes, duration):
    h, _ = register(client, "q@example.com")
    r = start(client, h, duration)
    assert r.status_code == 200, r.text
    qs = r.json()["questions"]
    assert len(qs) == DURATION_QUESTIONS[duration]
    diffs = [q["difficulty"] for q in qs]
    assert diffs == sorted(diffs)
    assert all(difficulty_band(i, len(qs))[0] <= d <= difficulty_band(i, len(qs))[1] for i, d in enumerate(diffs))
    assert [q["points"] for q in qs] == diffs  # harder is worth more


def test_start_hides_answers_and_results_until_submitted(client, claude, notes):
    h, _ = register(client, "q@example.com")
    attempt = start(client, h).json()
    assert all("answer_key" not in q and "explanation" not in q for q in attempt["questions"])
    assert attempt["results"] is None and attempt["score"] is None
    again = client.get(f"/quizzes/attempts/{attempt['id']}", headers=h).json()
    assert again["results"] is None and all("answer_key" not in q for q in again["questions"])

    mcq = next(q for q in attempt["questions"] if q["type"] == "mcq")
    short = next(q for q in attempt["questions"] if q["type"] == "short")
    r = client.post(f"/quizzes/attempts/{attempt['id']}/submit", headers=h,
                    json={"answers": {mcq["id"]: 1, short["id"]: "idea"}})
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["submitted"] and done["results"] and done["late"] is False
    by_id = {x["id"]: x for x in done["results"]}
    assert by_id[mcq["id"]]["earned"] == mcq["points"] and by_id[mcq["id"]]["explanation"]
    assert by_id[short["id"]]["earned"] == short["points"]
    assert done["score"] == mcq["points"] + short["points"] and done["grading_status"] == "done"
    assert "<answer>" in claude.calls[-1][1]  # member answers are wrapped as untrusted input

    # other members can't see it
    other, _ = register(client, "other@example.com")
    assert client.get(f"/quizzes/attempts/{attempt['id']}", headers=other).status_code == 404


def test_one_attempt_and_generation_is_cached(client, claude, notes):
    a, _ = register(client, "a@example.com")
    b, _ = register(client, "b@example.com")
    first = start(client, a).json()
    assert start(client, a).json()["id"] == first["id"]  # resume, not a new attempt
    start(client, b)
    assert claude.count("GenQuiz") == 1
    client.post(f"/quizzes/attempts/{first['id']}/submit", headers=a, json={"answers": {}})
    r = start(client, a)
    assert r.status_code == 409 and "already taken" in r.json()["detail"]


def test_late_submit_grades_autosaved_answers(client, claude, notes, db):
    h, _ = register(client, "late@example.com")
    attempt = start(client, h).json()
    mcq = [q for q in attempt["questions"] if q["type"] == "mcq"]
    r = client.patch(f"/quizzes/attempts/{attempt['id']}/answers", headers=h, json={"answers": {mcq[0]["id"]: 1}})
    assert r.status_code == 200 and r.json()["answers"] == {mcq[0]["id"]: 1}

    db.get(QuizAttempt, attempt["id"]).deadline_at = utcnow() - timedelta(seconds=1)
    db.commit()
    r = client.post(f"/quizzes/attempts/{attempt['id']}/submit", headers=h,
                    json={"answers": {mcq[0]["id"]: 0, mcq[1]["id"]: 1}})
    body = r.json()
    assert r.status_code == 200 and body["late"] is True
    assert body["answers"] == {mcq[0]["id"]: 1}  # the late answers were ignored
    assert body["score"] == mcq[0]["points"]
    assert client.patch(f"/quizzes/attempts/{attempt['id']}/answers", headers=h,
                        json={"answers": {}}).status_code == 409


def test_expired_attempt_is_finalized_on_read(client, claude, notes, db):
    h, _ = register(client, "idle@example.com")
    attempt = start(client, h).json()
    db.get(QuizAttempt, attempt["id"]).deadline_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.get(f"/quizzes/attempts/{attempt['id']}", headers=h).json()["submitted"] is True


def test_invalid_generation_is_retried_then_reported(client, claude, notes, db, admin, monkeypatch):
    h, _ = register(client, "g@example.com")
    bad = GenQuiz(questions=list(reversed(valid_questions(6))))  # hardest first
    claude.quiz_responses = [bad, GenQuiz(questions=valid_questions(6))]
    assert start(client, h).status_code == 200
    assert claude.count("GenQuiz") == 2
    assert "rejected" in claude.calls[1][1]

    alerts = []
    monkeypatch.setattr("app.services.admin_alerts.get_sender",
                        lambda: type("S", (), {"send": lambda self, p, m, template=None: alerts.append(m)})())
    db.execute(User.__table__.update().where(User.is_admin).values(phone_number="+254711111111"))
    db.commit()
    claude.quiz_responses = [bad, bad]
    r = start(client, h, duration=20)
    assert r.status_code == 503
    quiz = db.scalar(select(Quiz).where(Quiz.duration_minutes == 20))
    assert quiz.status == QuizStatus.failed and "easier" in quiz.error
    assert alerts and db.scalar(select(Notification).where(Notification.type == NotificationType.admin_alert))


def test_no_notes_means_no_weekly_quiz(client, claude):
    h, _ = register(client, "n@example.com")
    r = start(client, h)
    assert r.status_code == 404 and claude.count("GenQuiz") == 0
    slots = client.get("/weekly/current", headers=h).json()["quizzes"]
    weekly = [s for s in slots if s["kind"] == "weekly"]
    assert not any(s["available"] for s in weekly) and weekly[0]["reason"] == "No class notes for this week yet"


def test_without_api_key_everything_loads(client, notes, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    h, _ = register(client, "k@example.com")
    current = client.get("/weekly/current", headers=h)
    assert current.status_code == 200 and current.json()["ai_configured"] is False
    assert start(client, h).status_code == 503


def test_short_answer_grading_failure_keeps_mcq_points(client, claude, notes, monkeypatch):
    h, _ = register(client, "f@example.com")
    attempt = start(client, h).json()
    mcq = next(q for q in attempt["questions"] if q["type"] == "mcq")
    short = next(q for q in attempt["questions"] if q["type"] == "short")

    def broken(system, content, output_format, model=None):
        raise grading.GradingError("grader down")

    monkeypatch.setattr(grading, "_parse", broken)
    body = client.post(f"/quizzes/attempts/{attempt['id']}/submit", headers=h,
                       json={"answers": {mcq["id"]: 1, short["id"]: "something"}}).json()
    assert body["grading_status"] == "failed" and body["score"] == mcq["points"]


def test_quiz_leaderboard_is_separate(client, claude, notes, challenge):
    h, _ = register(client, "lb@example.com", "Leader")
    attempt = start(client, h).json()
    mcq = next(q for q in attempt["questions"] if q["type"] == "mcq")
    client.post(f"/quizzes/attempts/{attempt['id']}/submit", headers=h, json={"answers": {mcq["id"]: 1}})
    rows = client.get("/quizzes/leaderboard", headers=h).json()
    assert rows[0]["name"] == "Leader" and rows[0]["points"] == mcq["points"]
    assert client.get(f"/leaderboard/{challenge['id']}", headers=h).json() == []  # main board untouched
