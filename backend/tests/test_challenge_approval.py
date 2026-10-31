"""Challenge approval workflow: proposals, the admin queue, visibility, transitions and races."""

from datetime import timedelta

import pytest

from app.db import SessionLocal
from app.deps import today
from app.models import Challenge, ChallengeStatus, User
from app.services import challenge_review as review
from app.services.notifications import active_challenges
from tests.conftest import register


def proposal(**over) -> dict:
    t = today()
    return {"name": "30 Days of SQL", "description": "One query a day.", "start_date": str(t + timedelta(days=3)),
            "end_date": str(t + timedelta(days=32)), "task_types_allowed": "code", **over}


@pytest.fixture
def member(client):
    return register(client, "amina@example.com", "Amina")[0]


@pytest.fixture
def other(client):
    return register(client, "brian@example.com", "Brian")[0]


@pytest.fixture
def pending(client, member):
    r = client.post("/challenges/proposals", headers=member, json=proposal())
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def second_admin(client, db):
    h, _ = register(client, "ta@example.com", "Second Admin")
    db.query(User).filter(User.email == "ta@example.com").update({"is_admin": True})
    db.commit()
    return h


# --- proposing ------------------------------------------------------------------------

def test_member_proposal_is_pending_and_never_active(client, member, pending, other, admin):
    assert pending["status"] == "pending" and pending["review_note"] is None
    assert all(c["id"] != pending["id"] for c in client.get("/challenges", headers=member).json())
    assert all(c["id"] != pending["id"] for c in client.get("/challenges", headers=admin).json())
    assert [p["id"] for p in client.get("/challenges/proposals/mine", headers=member).json()] == [pending["id"]]
    assert client.get("/challenges/proposals/mine", headers=other).json() == []


def test_pending_is_hidden_from_other_members(client, member, pending, other, admin):
    cid = pending["id"]
    assert client.get(f"/challenges/{cid}", headers=other).status_code == 404
    assert client.get(f"/leaderboard/{cid}", headers=other).status_code == 404
    assert client.post(f"/challenges/{cid}/enroll", headers=other).status_code == 404
    assert client.get(f"/challenges/{cid}", headers=member).status_code == 200  # the creator
    assert client.get(f"/challenges/{cid}", headers=admin).status_code == 200
    r = client.post(f"/challenges/{cid}/enroll", headers=member)
    assert r.status_code == 409 and "only approved" in r.json()["detail"]


def test_proposal_validation(client, member):
    t = today()
    assert client.post("/challenges/proposals", headers=member, json=proposal(scoring_rules={"code_points": 99})).status_code == 422
    assert client.post("/challenges/proposals", headers=member, json=proposal(start_date=str(t - timedelta(days=1)))).status_code == 422
    assert client.post("/challenges/proposals", headers=member, json=proposal(end_date=str(t))).status_code == 422
    assert client.post("/challenges/proposals", headers=member, json=proposal(end_date=str(t + timedelta(days=400)))).status_code == 422
    for _ in range(review.MAX_PENDING_PER_MEMBER):
        assert client.post("/challenges/proposals", headers=member, json=proposal()).status_code == 201
    r = client.post("/challenges/proposals", headers=member, json=proposal())
    assert r.status_code == 409 and "waiting for review" in r.json()["detail"]


def test_edit_and_cancel_only_own_pending(client, member, other, pending, admin):
    cid = pending["id"]
    assert client.patch(f"/challenges/proposals/{cid}", headers=other, json={"name": "Mine now"}).status_code == 404
    assert client.post(f"/challenges/proposals/{cid}/cancel", headers=other).status_code == 404
    r = client.patch(f"/challenges/proposals/{cid}", headers=member, json={"name": "  30 Days of Postgres  "})
    assert r.status_code == 200 and r.json()["name"] == "30 Days of Postgres" and r.json()["status"] == "pending"
    bad = client.patch(f"/challenges/proposals/{cid}", headers=member, json={"end_date": pending["start_date"][:8] + "01"})
    assert bad.status_code == 422

    assert client.post(f"/challenges/proposals/{cid}/cancel", headers=member).json()["status"] == "cancelled"
    assert client.patch(f"/challenges/proposals/{cid}", headers=member, json={"name": "Again"}).status_code == 409
    r = client.post(f"/admin/challenges/{cid}/approve", headers=admin, json={})
    assert r.status_code == 409 and "cancelled by the member" in r.json()["detail"]


# --- permissions ----------------------------------------------------------------------

def test_members_cannot_review(client, member, pending):
    cid = pending["id"]
    assert client.post(f"/admin/challenges/{cid}/approve", headers=member, json={}).status_code == 403
    assert client.post(f"/admin/challenges/{cid}/reject", headers=member, json={"note": "no"}).status_code == 403
    assert client.get("/admin/challenges", headers=member).status_code == 403
    assert client.get(f"/admin/challenges/{cid}", headers=member).status_code == 403
    assert client.post(f"/admin/challenges/{cid}/approve", json={}).status_code == 401


# --- reviewing ------------------------------------------------------------------------

def test_admin_approves(client, admin, member, other, pending):
    cid = pending["id"]
    r = client.post(f"/admin/challenges/{cid}/approve", headers=admin, json={"note": "Great idea"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved" and body["reviewer"]["name"] == "Admin" and body["creator"]["name"] == "Amina"
    assert body["review_note"] == "Great idea" and body["reviewed_at"]
    assert any(c["id"] == cid for c in client.get("/challenges", headers=other).json())
    assert client.post(f"/challenges/{cid}/enroll", headers=other).status_code == 201
    assert client.post(f"/challenges/proposals/{cid}/cancel", headers=member).status_code == 409


def test_rejection_requires_a_reason_and_is_shown_to_the_member(client, admin, member, other, pending):
    cid = pending["id"]
    assert client.post(f"/admin/challenges/{cid}/reject", headers=admin, json={}).status_code == 422
    assert client.post(f"/admin/challenges/{cid}/reject", headers=admin, json={"note": ""}).status_code == 422
    r = client.post(f"/admin/challenges/{cid}/reject", headers=admin, json={"note": "   "})
    assert r.status_code == 422 and "reason is required" in r.json()["detail"]
    r = client.post(f"/admin/challenges/{cid}/reject", headers=admin, json={"note": "Overlaps with 100 Days of Python"})
    assert r.json()["status"] == "rejected"
    mine = client.get("/challenges/proposals/mine", headers=member).json()[0]
    assert mine["status"] == "rejected" and mine["review_note"] == "Overlaps with 100 Days of Python"
    assert client.get(f"/challenges/{cid}", headers=other).status_code == 404


def test_invalid_transitions(client, admin, pending):
    cid = pending["id"]
    client.post(f"/admin/challenges/{cid}/reject", headers=admin, json={"note": "Not now"})
    r = client.post(f"/admin/challenges/{cid}/approve", headers=admin, json={})
    assert r.status_code == 409 and "Already rejected by Admin" in r.json()["detail"]
    assert client.post(f"/admin/challenges/{cid}/reject", headers=admin, json={"note": "again"}).status_code == 409


def test_cannot_approve_after_the_end_date(client, admin, pending, db):
    db.get(Challenge, pending["id"]).end_date = today() - timedelta(days=1)
    db.commit()
    r = client.post(f"/admin/challenges/{pending['id']}/approve", headers=admin, json={})
    assert r.status_code == 409 and "end date has passed" in r.json()["detail"]


def test_double_approval_second_admin_gets_409(client, admin, second_admin, pending):
    cid = pending["id"]
    assert client.post(f"/admin/challenges/{cid}/approve", headers=admin, json={}).status_code == 200
    r = client.post(f"/admin/challenges/{cid}/approve", headers=second_admin, json={})
    assert r.status_code == 409 and "Already approved by Admin" in r.json()["detail"]


def test_race_two_admins_with_stale_reads(client, admin, second_admin, pending):
    """Both admins load the pending challenge before either acts; only one conditional update wins."""
    with SessionLocal() as s1, SessionLocal() as s2:
        c1, c2 = s1.get(Challenge, pending["id"]), s2.get(Challenge, pending["id"])
        a1 = s1.scalar(s1.query(User).filter(User.email == "admin@example.com").statement)
        a2 = s2.scalar(s2.query(User).filter(User.email == "ta@example.com").statement)
        assert c1.status == c2.status == ChallengeStatus.pending
        review.approve(s1, c1, a1, None, today())
        with pytest.raises(review.ReviewError) as e:
            review.reject(s2, c2, a2, "Too similar")  # passes the in-memory check, loses at the UPDATE
        assert e.value.status_code == 409 and "Already approved by Admin" in str(e.value)
    with SessionLocal() as s3:
        final = s3.get(Challenge, pending["id"])
        assert final.status == ChallengeStatus.approved and final.review_note is None


# --- admin queue and other effects ---------------------------------------------------

def test_queue_filters_and_pages(client, admin, member, other):
    for name in ("SQL sprint", "Go basics", "Rust weekends"):
        client.post("/challenges/proposals", headers=member, json=proposal(name=name))
    client.post("/challenges/proposals", headers=other, json=proposal(name="SQL deep dive"))
    page = client.get("/admin/challenges?limit=2", headers=admin).json()
    assert page["total"] == 4 and len(page["items"]) == 2 and page["items"][0]["name"] == "SQL sprint"  # oldest first
    assert client.get("/admin/challenges?limit=2&offset=2", headers=admin).json()["items"][1]["name"] == "SQL deep dive"
    assert client.get("/admin/challenges?q=sql", headers=admin).json()["total"] == 2
    first = page["items"][0]["id"]
    client.post(f"/admin/challenges/{first}/approve", headers=admin, json={})
    assert client.get("/admin/challenges", headers=admin).json()["total"] == 3
    assert [c["id"] for c in client.get("/admin/challenges?status=approved", headers=admin).json()["items"]] == [first]
    assert client.get("/admin/challenges?status=bogus", headers=admin).status_code == 422


def test_admin_created_challenges_are_approved_with_audit(client, admin, challenge):
    detail = client.get(f"/admin/challenges/{challenge['id']}", headers=admin).json()
    assert detail["status"] == "approved" and detail["creator"]["name"] == "Admin" and detail["reviewer"]["name"] == "Admin"
    assert challenge["status"] == "approved"


def test_lag_check_ignores_proposals(client, pending, db):
    db.get(Challenge, pending["id"]).start_date = today() - timedelta(days=5)
    db.commit()
    assert all(c.id != pending["id"] for c in active_challenges(db, today()))


def test_audit_detail_for_a_challenge_from_before_approvals(client, admin, db):
    """Rows the migration backfilled: approved, with no creator or reviewer recorded."""
    old = Challenge(name="Legacy challenge", start_date=today(), end_date=today() + timedelta(days=9),
                    scoring_rules={}, status=ChallengeStatus.approved)
    db.add(old)
    db.commit()
    detail = client.get(f"/admin/challenges/{old.id}", headers=admin).json()
    assert detail["status"] == "approved" and detail["creator"] is None and detail["reviewer"] is None
    assert detail["reviewed_at"] is None and detail["enrolled"] == 0
    assert client.get("/admin/challenges/999999", headers=admin).status_code == 404


def test_audit_trail_records_who_when_and_why(client, admin, member, pending):
    cid = pending["id"]
    client.post(f"/admin/challenges/{cid}/reject", headers=admin, json={"note": "Too close to exams"})
    detail = client.get(f"/admin/challenges/{cid}", headers=admin).json()
    assert detail["creator"]["name"] == "Amina" and detail["reviewer"]["name"] == "Admin"
    assert detail["review_note"] == "Too close to exams" and detail["reviewed_at"] >= detail["created_at"]
