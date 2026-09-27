from datetime import datetime, timedelta, timezone

import pytest

from app.models import Enrollment, Notification, Submission
from app.scoring import DEFAULT_RULES, compute_streaks
from app.services import grading
from app.services.article_fetch import ArticleFetchError, fetch_html
from tests.conftest import register


def member(client, challenge, email="amina@example.com", name="Amina Otieno", **extra):
    headers, _ = register(client, email, name, **extra)
    r = client.post(f"/challenges/{challenge['id']}/enroll", headers=headers)
    assert r.status_code == 201, r.text
    return headers


def submit_code(client, headers, challenge, **extra):
    body = {"challenge_id": challenge["id"], "submission_type": "code", "content": "print('hi')", "language": "python"}
    return client.post("/submissions", headers=headers, json={**body, **extra})


# --- scoring ---------------------------------------------------------------

def test_compute_streaks():
    s = compute_streaks({1, 2, 3, 5, 6, 7, 8, 9, 10, 11}, ref_day=12, rules=DEFAULT_RULES)
    assert (s.current, s.longest) == (7, 7)  # yesterday's submission keeps the streak alive
    assert s.bonus_points == 5
    assert compute_streaks({1, 2, 3}, ref_day=5, rules=DEFAULT_RULES).current == 0
    assert compute_streaks(set(), ref_day=1, rules=DEFAULT_RULES).longest == 0


# --- auth ------------------------------------------------------------------

def test_admin_bootstrap_and_permissions(client, admin):
    assert client.get("/auth/me", headers=admin).json()["is_admin"] is True
    headers, _ = register(client, "m@example.com")
    assert client.get("/auth/me", headers=headers).json()["is_admin"] is False
    assert client.post("/challenges", headers=headers, json={}).status_code == 403
    assert client.get("/members", headers=headers).status_code == 403
    assert client.get("/auth/me").status_code == 401


# --- submissions -----------------------------------------------------------

def test_code_submission_points_and_one_counted_per_day(client, challenge):
    h = member(client, challenge)
    r = submit_code(client, h, challenge)
    assert r.status_code == 201, r.text
    first = r.json()
    assert [c["id"] for c in client.get("/challenges/mine", headers=h).json()] == [challenge["id"]]
    assert (first["day_number"], first["counts_for_streak"], first["points_awarded"]) == (10, True, 10)

    second = submit_code(client, h, challenge).json()
    assert (second["counts_for_streak"], second["points_awarded"]) == (False, 0)

    yesterday = submit_code(client, h, challenge, day_number=9).json()
    assert yesterday["counts_for_streak"] is True

    board = client.get(f"/leaderboard/{challenge['id']}", headers=h).json()
    assert board[0]["total_points"] == 20
    assert board[0]["current_streak"] == 2


def test_submission_validation(client, challenge):
    h = member(client, challenge)
    assert submit_code(client, h, challenge, day_number=11).status_code == 400  # future
    assert submit_code(client, h, challenge, day_number=5).status_code == 400  # past backfill window
    r = client.post("/submissions", headers=h, json={"challenge_id": challenge["id"], "submission_type": "article", "content": "not a url"})
    assert r.status_code == 422
    outsider, _ = register(client, "x@example.com")
    assert submit_code(client, outsider, challenge).status_code == 403


def test_article_grading(client, challenge, monkeypatch):
    monkeypatch.setattr(
        grading, "grade_article", lambda url: (
            8.0,
            {"clarity": 3, "technical_accuracy": 2, "depth": 2, "originality": 1},
            "Nice work.",
            {"title": "Decorators", "strengths": ["Clear examples"], "improvements": ["Add tests"]},
        )
    )
    h = member(client, challenge)
    r = client.post(
        "/submissions",
        headers=h,
        json={"challenge_id": challenge["id"], "submission_type": "article", "content": "https://dev.to/amina/decorators"},
    )
    assert r.status_code == 201
    assert r.json()["grading_status"] == "pending"
    # TestClient runs background tasks before returning, so grading is done now.
    sub = client.get(f"/submissions/{r.json()['id']}", headers=h).json()
    assert sub["grading_status"] == "done"
    assert sub["ai_score"] == 8.0
    assert sub["points_awarded"] == 15 + 8  # base + scaled AI bonus
    assert sub["ai_feedback"] == "Nice work."
    assert sub["ai_details"]["strengths"] == ["Clear examples"]

    board = client.get(f"/leaderboard/{challenge['id']}", headers=h).json()
    assert board[0]["avg_ai_score"] == 8.0
    assert client.get("/meta").json()["timezone"] == "UTC"


def test_failed_grading_can_be_overridden(client, challenge, admin, monkeypatch):
    def boom(url):
        raise ArticleFetchError("Couldn't read enough text")

    monkeypatch.setattr(grading, "grade_article", boom)
    h = member(client, challenge)
    sub = client.post(
        "/submissions",
        headers=h,
        json={"challenge_id": challenge["id"], "submission_type": "article", "content": "https://example.com/a"},
    ).json()
    sub = client.get(f"/submissions/{sub['id']}", headers=h).json()
    assert sub["grading_status"] == "failed"
    assert sub["points_awarded"] == 15

    r = client.patch(f"/admin/submissions/{sub['id']}/grade", headers=admin, json={"ai_score": 5})
    assert r.json()["points_awarded"] == 20
    assert r.json()["grade_overridden"] is True


def test_ssrf_guard():
    with pytest.raises(ArticleFetchError):
        fetch_html("http://127.0.0.1/admin")
    with pytest.raises(ArticleFetchError):
        fetch_html("file:///etc/passwd")


# --- leaderboard / dashboard -----------------------------------------------

def test_leaderboard_ties_and_global(client, challenge, admin):
    a = member(client, challenge, "a@example.com", "Alice")
    b = member(client, challenge, "b@example.com", "Bob")
    c = member(client, challenge, "c@example.com", "Cara")
    submit_code(client, a, challenge, day_number=9)
    submit_code(client, a, challenge)
    submit_code(client, b, challenge)
    submit_code(client, c, challenge)

    board = client.get(f"/leaderboard/{challenge['id']}", headers=a).json()
    assert [(r["name"], r["rank"]) for r in board] == [("Alice", 1), ("Bob", 2), ("Cara", 2)]
    glob = client.get("/leaderboard/global", headers=a).json()
    assert glob[0]["name"] == "Alice" and glob[0]["total_points"] == 20


def test_dashboard(client, challenge, admin):
    h = member(client, challenge)
    submit_code(client, h, challenge)
    me = client.get("/auth/me", headers=h).json()
    d = client.get(f"/members/{me['id']}/dashboard", headers=h).json()
    assert d["total_points"] == 10
    assert d["challenges"][0]["rank"] == 1
    assert sum(d["heatmap"].values()) == 1
    assert d["job_stats"]["total"] == 0

    other, _ = register(client, "nosy@example.com")
    assert client.get(f"/members/{me['id']}/dashboard", headers=other).status_code == 403
    assert client.get(f"/members/{me['id']}/dashboard", headers=admin).json()["job_stats"] is None


# --- notifications ---------------------------------------------------------

class FakeSender:
    def __init__(self):
        self.sent = []

    def send(self, phone, message):
        self.sent.append((phone, message))


def test_lag_check(client, challenge, db):
    from app.deps import today
    from app.services.notifications import run_lag_check

    h = member(client, challenge, phone_number="+254700000001", whatsapp_opt_in=True)
    member(client, challenge, "quiet@example.com", "Quiet")  # no phone -> skipped
    submit_code(client, h, challenge, day_number=9)  # yesterday: on pace

    for e in db.query(Enrollment).all():
        e.joined_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.commit()

    results = run_lag_check(db, today() + timedelta(days=3), sender=(sender := FakeSender()))
    by_name = {r["name"]: r for r in results}
    assert by_name["Amina Otieno"]["days_missed"] == 3
    assert by_name["Amina Otieno"]["notified"] is True
    assert by_name["Quiet"]["skipped_reason"] == "no WhatsApp opt-in"
    assert sender.sent[0][0] == "+254700000001"
    assert "Amina" in sender.sent[0][1] and "100 Days of Python" in sender.sent[0][1]

    # Re-running the same day doesn't nudge twice.
    run_lag_check(db, today() + timedelta(days=3), sender=sender)
    assert len(sender.sent) == 1
    assert db.query(Notification).count() == 1


def test_admin_dry_run_endpoint(client, challenge, admin):
    member(client, challenge)
    r = client.post("/admin/notify/run", headers=admin)
    assert r.status_code == 200 and r.json()["dry_run"] is True


# --- job applications ------------------------------------------------------

def test_job_applications(client, challenge):
    h = member(client, challenge)
    other, _ = register(client, "peer@example.com")
    from app.deps import today

    r = client.post("/job-applications", headers=h, json={"company": "Safaricom", "role": "Backend Engineer", "date_applied": str(today()), "is_public": True})
    app_id = r.json()["id"]
    client.post("/job-applications", headers=h, json={"company": "Acme", "role": "SWE", "date_applied": str(today())})

    assert client.get("/job-applications/feed", headers=other).json() == []
    assert client.patch(f"/job-applications/{app_id}", headers=other, json={"status": "interview"}).status_code == 404
    client.patch(f"/job-applications/{app_id}", headers=h, json={"status": "interview"})

    feed = client.get("/job-applications/feed", headers=other).json()
    assert [(f["company"], f["status"]) for f in feed] == [("Safaricom", "interview")]

    stats = client.get("/job-applications/me", headers=h).json()["stats"]
    assert stats["total"] == 2 and stats["interviews"] == 1 and stats["response_rate"] == 0.5


def test_rules_change_recomputes(client, challenge, admin):
    h = member(client, challenge)
    submit_code(client, h, challenge)
    client.patch(f"/challenges/{challenge['id']}", headers=admin, json={"scoring_rules": {"code_points": 12}})
    board = client.get(f"/leaderboard/{challenge['id']}", headers=h).json()
    assert board[0]["total_points"] == 12


def test_leave_challenge_deletes_submissions(client, challenge, db):
    h = member(client, challenge)
    submit_code(client, h, challenge)
    assert client.delete(f"/challenges/{challenge['id']}/enroll", headers=h).status_code == 204
    assert db.query(Submission).count() == 0


def test_grading_without_api_key_fails_cleanly(client, challenge, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    h = member(client, challenge)
    sub = client.post(
        "/submissions",
        headers=h,
        json={"challenge_id": challenge["id"], "submission_type": "article", "content": "https://example.com/a"},
    ).json()
    sub = client.get(f"/submissions/{sub['id']}", headers=h).json()
    assert sub["grading_status"] == "failed"
    assert "isn't configured" in sub["ai_feedback"]


@pytest.mark.parametrize(
    "url",
    ["postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"],
)
def test_database_url_uses_psycopg3(url):
    from app.config import Settings

    assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@h:5432/db"
