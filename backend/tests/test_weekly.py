from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, insert, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import JobRun, Notification, NotificationType, ProjectProposal, User, WeeklyBrief
from app.services import grading
from app.services.weekly import build_drop_message, maybe_run_weekly_drop, run_weekly_drop
from app.services.whatsapp import MetaCloudSender
from app.weeks import current_week_key, upcoming_week_key
from tests.conftest import register
from tests.fakes import FakeClaude, FakeSender


@pytest.fixture
def claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(grading, "_parse", fake)
    return fake


def propose(client, headers, title="Build a CLI todo app"):
    return client.post("/weekly/projects", headers=headers, json={"title": title, "description": "A small project for the week."})


def add_member(client, n, opt_in=True):
    phone = f"+25470000000{n}"
    headers, _ = register(client, f"m{n}@example.com", f"Member {n}", phone_number=phone, whatsapp_opt_in=opt_in)
    return headers, phone


# --- projects ------------------------------------------------------------------

def test_two_project_cap_and_one_per_member(client, claude):
    a, b, c = (register(client, f"p{i}@example.com")[0] for i in range(3))
    first = propose(client, a)
    assert first.status_code == 201, first.text
    assert first.json()["slot"] == 1 and first.json()["week_key"] == str(upcoming_week_key())
    assert propose(client, a, "Another idea").status_code == 409  # one per member
    assert propose(client, b, "Second idea").json()["slot"] == 2
    third = propose(client, c, "Third idea")
    assert third.status_code == 409 and "Both project slots" in third.json()["detail"]

    upcoming = client.get("/weekly/current", headers=c).json()["upcoming"]
    assert upcoming["slots_left"] == 0 and len(upcoming["projects"]) == 2

    # withdrawing frees the slot
    assert client.delete(f"/weekly/projects/{first.json()['id']}", headers=a).status_code == 204
    assert propose(client, c, "Third idea").json()["slot"] == 1


def test_unique_constraints_block_two_proposals_in_one_slot(db, client):
    a, b = (register(client, f"u{i}@example.com")[1] for i in range(2))
    users = db.scalars(select(User).order_by(User.id)).all()
    week = upcoming_week_key()
    db.add(ProjectProposal(week_key=week, slot=1, proposer_id=users[0].id, title="A", description="aaaaaaaaaa"))
    db.commit()
    db.add(ProjectProposal(week_key=week, slot=1, proposer_id=users[1].id, title="B", description="bbbbbbbbbb"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_concurrent_proposal_loses_slot_one_and_gets_slot_two(client):
    a, _ = register(client, "racer@example.com")
    register(client, "rival@example.com")
    with SessionLocal() as s:
        rival_id = s.scalar(select(User.id).where(User.email == "rival@example.com"))
    week = upcoming_week_key()
    fired = []

    # Just before the API's insert is flushed, a "concurrent request" takes slot 1.
    @event.listens_for(SessionLocal, "before_flush")
    def rival(session, *_):
        if not fired and any(isinstance(o, ProjectProposal) for o in session.new):
            fired.append(True)
            with engine.begin() as conn:
                conn.execute(insert(ProjectProposal).values(
                    week_key=week, slot=1, proposer_id=rival_id, title="Rival", description="rival idea here",
                    created_at=datetime.now()))

    try:
        r = propose(client, a)
    finally:
        event.remove(SessionLocal, "before_flush", rival)
    assert fired and r.status_code == 201, r.text
    assert r.json()["slot"] == 2


def test_pick_can_change_and_must_be_this_weeks(client, db):
    h, _ = register(client, "picker@example.com")
    register(client, "x@example.com")
    ids = db.scalars(select(User.id).order_by(User.id)).all()
    week = current_week_key()
    p1 = ProjectProposal(week_key=week, slot=1, proposer_id=ids[0], title="One", description="first project")
    p2 = ProjectProposal(week_key=week, slot=2, proposer_id=ids[1], title="Two", description="second project")
    db.add_all([p1, p2])
    db.commit()

    assert client.put("/weekly/projects/pick", headers=h, json={"proposal_id": p1.id}).status_code == 200
    assert client.put("/weekly/projects/pick", headers=h, json={"proposal_id": p2.id}).status_code == 200
    current = client.get("/weekly/current", headers=h).json()
    assert current["my_pick"] == p2.id
    assert [(p["title"], p["picks"]) for p in current["projects"]] == [("One", 0), ("Two", 1)]

    upcoming = propose(client, h, "Next week's idea").json()
    r = client.put("/weekly/projects/pick", headers=h, json={"proposal_id": upcoming["id"]})
    assert r.status_code == 400


# --- notes and summary -------------------------------------------------------------

def test_any_member_can_add_notes_and_summary_is_generated(client, claude):
    h, _ = register(client, "notes@example.com")
    r = client.put("/weekly/brief", headers=h, json={"source_notes": "This week: decorators, generators and context managers."})
    assert r.status_code == 200, r.text
    assert r.json()["week_key"] == str(upcoming_week_key())
    brief = client.get("/weekly/brief", headers=h).json()
    assert brief["status"] == "ready" and brief["summary"].startswith("Decorators")  # background task ran
    assert "decorators" in brief["source_notes"]
    assert "<class_notes" in claude.calls[0][1]  # notes are wrapped as untrusted input


# --- the drop ---------------------------------------------------------------------

def test_drop_is_idempotent_skips_non_opted_in_and_survives_failures(client, db, claude):
    _, phone1 = add_member(client, 1)
    _, phone2 = add_member(client, 2)
    _, phone3 = add_member(client, 3)
    _, phone4 = add_member(client, 4, opt_in=False)
    week = current_week_key()
    db.add(WeeklyBrief(week_key=week, source_notes="Decorators, generators and context managers this week."))
    db.commit()

    sender = FakeSender(fail_for={phone2}, crash_for={phone3})
    result = run_weekly_drop(db, week, sender=sender)
    assert [p for p, _, _ in sender.sent] == [phone1]  # 2 failed, 3 crashed, the loop kept going
    statuses = {r["user_id"]: r["status"] for r in result["recipients"]}
    assert list(statuses.values()).count("failed") == 2
    assert any("no WhatsApp opt-in" in s for s in statuses.values())
    assert result["summary_ready"] and not result["notes_missing"]
    failed = db.scalars(select(Notification).where(Notification.status == "failed")).all()
    assert len(failed) == 2 and all(n.error for n in failed)

    # Second run: member 1 isn't messaged again; the earlier failures are retried.
    sender2 = FakeSender()
    run_weekly_drop(db, week, sender=sender2)
    assert sorted(p for p, _, _ in sender2.sent) == sorted([phone2, phone3])
    run_weekly_drop(db, week, sender=(sender3 := FakeSender()))
    assert sender3.sent == []
    assert phone4 not in [p for s in (sender, sender2) for p, _, _ in s.sent]


def test_drop_without_notes_skips_summary_and_alerts_admins(client, db, claude, admin, monkeypatch):
    add_member(client, 1)
    db.execute(User.__table__.update().where(User.email == "admin@example.com").values(phone_number="+254711111111"))
    db.commit()
    alerts = FakeSender()
    monkeypatch.setattr("app.services.admin_alerts.get_sender", lambda: alerts)

    result = run_weekly_drop(db, current_week_key(), sender=FakeSender())
    assert result["notes_missing"] and not result["summary_ready"]
    assert "isn't ready yet" in result["message"]
    assert claude.count("BriefSummary") == 0 and claude.count("GenQuiz") == 0  # nothing invented
    assert len(alerts.sent) == 1 and "no class notes" in alerts.sent[0][1]
    assert db.scalar(select(Notification).where(Notification.type == NotificationType.admin_alert)) is not None


def test_drop_dry_run_sends_nothing(client, db, claude):
    add_member(client, 1)
    sender = FakeSender()
    result = run_weekly_drop(db, current_week_key(), dry_run=True, sender=sender)
    assert sender.sent == [] and result["recipients"][0]["status"] == "would send"
    assert db.scalar(select(Notification)) is None


def test_scheduled_drop_runs_once_per_friday(client, db, claude):
    add_member(client, 1)
    tz = get_settings().tz
    friday = datetime(2026, 10, 16, 9, 0, tzinfo=tz)
    assert friday.weekday() == 4
    assert maybe_run_weekly_drop(db, friday - timedelta(hours=2), sender=FakeSender()) is None  # before 08:00
    assert maybe_run_weekly_drop(db, friday + timedelta(days=1), sender=FakeSender()) is None  # Saturday
    sender = FakeSender()
    assert maybe_run_weekly_drop(db, friday, sender=sender)["sent"] == 1
    assert maybe_run_weekly_drop(db, friday + timedelta(hours=1), sender=sender) is None  # already done
    assert len(sender.sent) == 1
    run = db.scalar(select(JobRun))
    assert (run.job, run.run_key, run.status) == ("weekly_drop", "2026-10-16", "done")


def test_internal_endpoint_requires_token(client, monkeypatch):
    assert client.post("/internal/jobs/weekly-drop").status_code == 404  # off without JOB_TOKEN
    monkeypatch.setattr(get_settings(), "job_token", "s3cret-token")
    assert client.post("/internal/jobs/weekly-drop").status_code == 401
    assert client.post("/internal/jobs/weekly-drop", headers={"X-Job-Token": "wrong"}).status_code == 401
    monkeypatch.setattr("app.routers.internal.maybe_run_weekly_drop", lambda: None)
    r = client.post("/internal/jobs/weekly-drop", headers={"X-Job-Token": "s3cret-token"})
    assert r.status_code == 202 and "due" in r.json()


def test_admin_drop_routes(client, admin, claude):
    h, _ = register(client, "member@example.com")
    assert client.post("/admin/weekly/drop/run", headers=h).status_code == 403
    r = client.post("/admin/weekly/drop/run?week=upcoming", headers=admin)
    assert r.status_code == 200 and r.json()["dry_run"] is True
    assert client.post("/admin/weekly/drop/run?week=upcoming&dry_run=false", headers=admin).status_code == 400
    assert client.post("/admin/monthly/run", headers=admin).json()["dry_run"] is True


# --- WhatsApp formatting --------------------------------------------------------------

def test_template_message_is_a_single_line(db, monkeypatch):
    brief = WeeklyBrief(week_key=current_week_key(), source_notes="x",
                        summary="Line one.\nLine two.\tTabbed.     Spaced.\n\nThird.")
    proposals = [ProjectProposal(title="CLI\napp", slot=1), ProjectProposal(title="Web    scraper", slot=2)]
    message = build_drop_message(current_week_key(), brief, proposals, has_quiz=True, monthly=True)
    assert "\n" not in message and "\t" not in message and "     " not in message
    assert message.endswith("/weekly") and "CLI app" in message

    payloads = []

    class Resp:
        status_code = 200
        text = ""

    monkeypatch.setattr("app.services.whatsapp.httpx.post", lambda url, json, headers, timeout: payloads.append(json) or Resp())
    MetaCloudSender("token", "123").send("+254700000001", "a\nb\tc", template="weekly_drop")
    param = payloads[0]["template"]["components"][0]["parameters"][0]["text"]
    assert payloads[0]["template"]["name"] == "weekly_drop" and param == "a b c"


def test_specialization_is_validated(client):
    h, _ = register(client, "spec@example.com")
    assert client.patch("/auth/me", headers=h, json={"specialization": "data_science"}).json()["specialization"] == "data_science"
    assert client.patch("/auth/me", headers=h, json={"specialization": "astrology"}).status_code == 422
    assert "general" in client.get("/meta").json()["specializations"]
