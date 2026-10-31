"""Step 3: in-app notifications for the challenge workflow, and the inbox API."""

from datetime import timedelta

import pytest

from app.deps import today
from app.models import InboxMessage, User
from app.services import inbox
from tests.conftest import register


def proposal(name="30 Days of SQL") -> dict:
    t = today()
    return {"name": name, "start_date": str(t + timedelta(days=2)), "end_date": str(t + timedelta(days=31))}


@pytest.fixture
def member(client):
    return register(client, "amina@example.com", "Amina", phone_number="+254712345678")[0]


@pytest.fixture
def second_admin(client, db):
    h, _ = register(client, "ta@example.com", "Second Admin")
    db.query(User).filter(User.email == "ta@example.com").update({"is_admin": True})
    db.commit()
    return h


def messages(client, headers) -> list[dict]:
    return client.get("/inbox", headers=headers).json()["items"]


def test_admins_are_notified_of_a_new_proposal(client, admin, second_admin, member):
    cid = client.post("/challenges/proposals", headers=member, json=proposal()).json()["id"]
    for h in (admin, second_admin):
        [m] = messages(client, h)
        assert m["event"] == "challenge_submitted" and m["challenge_id"] == cid and m["link"] == "/admin/challenges"
        assert m["title"] == "New challenge to review" and "Amina proposed “30 Days of SQL”" in m["body"]
        assert m["read_at"] is None
    assert messages(client, member) == []
    assert client.get("/inbox/unread-count", headers=admin).json() == {"unread": 1}


def test_member_hears_about_approval_and_rejection_with_reason(client, admin, member):
    a = client.post("/challenges/proposals", headers=member, json=proposal("SQL sprint")).json()["id"]
    b = client.post("/challenges/proposals", headers=member, json=proposal("Go basics")).json()["id"]
    client.post(f"/admin/challenges/{a}/approve", headers=admin, json={"note": "Starts Monday"})
    client.post(f"/admin/challenges/{b}/reject", headers=admin, json={"note": "Overlaps with 100 Days of Python"})
    rejected, approved = messages(client, member)  # newest first
    assert approved["title"] == "Your challenge was approved" and approved["link"] == "/join"
    assert "“SQL sprint” is now open" in approved["body"] and "Starts Monday" in approved["body"]
    assert rejected["title"] == "Your challenge wasn't approved" and rejected["link"] == "/challenges/proposals"
    assert rejected["body"] == "“Go basics”: Overlaps with 100 Days of Python"


def test_failed_review_sends_nothing_extra(client, admin, member):
    cid = client.post("/challenges/proposals", headers=member, json=proposal()).json()["id"]
    client.post(f"/admin/challenges/{cid}/approve", headers=admin, json={})
    client.post(f"/admin/challenges/{cid}/approve", headers=admin, json={})  # 409
    client.post(f"/challenges/proposals/{cid}/cancel", headers=member)  # 409
    assert len(messages(client, member)) == 1


def test_no_sensitive_data_in_notification_text(client, admin, member, db):
    cid = client.post("/challenges/proposals", headers=member, json=proposal()).json()["id"]
    client.post(f"/admin/challenges/{cid}/reject", headers=admin, json={"note": "Not this month"})
    for m in db.query(InboxMessage).all():
        text = f"{m.title} {m.body}"
        assert "amina@example.com" not in text and "712345678" not in text and "points" not in text.lower()


def test_inbox_is_private_and_can_be_marked_read(client, admin, second_admin, member):
    client.post("/challenges/proposals", headers=member, json=proposal("Alpha"))
    client.post("/challenges/proposals", headers=member, json=proposal("Bravo"))
    mine = messages(client, admin)
    theirs = messages(client, second_admin)[0]["id"]
    assert client.post(f"/inbox/{theirs}/read", headers=admin).status_code == 404
    assert client.post(f"/inbox/{theirs}/read", headers=member).status_code == 404

    read = client.post(f"/inbox/{mine[0]['id']}/read", headers=admin).json()
    assert read["read_at"] is not None
    assert client.get("/inbox/unread-count", headers=admin).json() == {"unread": 1}
    assert [m["id"] for m in client.get("/inbox?unread_only=true", headers=admin).json()["items"]] == [mine[1]["id"]]
    assert client.post("/inbox/read-all", headers=admin).json() == {"unread": 0}
    assert client.get("/inbox/unread-count", headers=second_admin).json() == {"unread": 2}  # untouched
    assert [m["id"] for m in client.get(f"/inbox?before_id={mine[0]['id']}", headers=admin).json()["items"]] == [mine[1]["id"]]
    assert client.get("/inbox").status_code == 401


def test_a_broken_channel_never_breaks_the_workflow(client, admin, member, monkeypatch):
    def broken(db, user, event, message):
        raise RuntimeError("SMTP down")

    monkeypatch.setattr(inbox, "CHANNELS", [broken, *inbox.CHANNELS])
    r = client.post("/challenges/proposals", headers=member, json=proposal())
    assert r.status_code == 201
    assert len(messages(client, admin)) == 1  # the in-app channel still delivered


def test_admin_reviewing_their_own_proposal_gets_no_self_notification(client, admin):
    cid = client.post("/challenges/proposals", headers=admin, json=proposal()).json()["id"]
    client.post(f"/admin/challenges/{cid}/approve", headers=admin, json={})
    assert messages(client, admin) == []
