"""Step 3: anonymisation of member data in prompts, and the per-user AI rate limit."""

import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from app.config import get_settings
from app.llm import LLMService
from app.llm.anonymize import Anonymizer, Person
from app.llm.client import OPENROUTER_BASE_URL, make_client
from app.llm.ratelimit import RateLimiter
from app.services import grading
from tests.conftest import register

PEOPLE = [
    Person("Amina Wanjiru", "amina@example.com", "+254 712 345 678"),
    Person("Grace Otieno", "grace@example.com", None),
    Person("John Kamau", None, "0722000111"),
    Person("John Mwangi", None, None),
]


@pytest.fixture
def anon():
    return Anonymizer(PEOPLE)


# --- anonymizer ----------------------------------------------------------------------

def test_names_emails_and_phones_are_replaced(anon):
    text = ("By AMINA WANJIRU (amina@example.com, 0712345678). Thanks to Wanjiru's group, "
            "Amina and Otieno; call 254712345678 or +254 722 000 111. Ping x@y.io")
    out = anon.redact(text)
    for leaked in ("Amina", "AMINA", "Wanjiru", "Otieno", "amina@", "712345678", "722000111", "x@y.io"):
        assert leaked not in out
    assert out.startswith("By Student A ([email], [phone]). Thanks to Student A's group, Student A and Student B")
    assert out.count("[phone]") == 3


def test_common_words_and_unrelated_numbers_are_left_alone(anon):
    text = "By grace of the compiler, Grace said 10000000071 and 712345 are fine. Grace Otieno wrote it."
    out = anon.redact(text)
    assert out == "By grace of the compiler, Grace said 10000000071 and 712345 are fine. Student B wrote it."


def test_shared_first_names_are_not_mapped_to_one_member(anon):
    out = anon.redact("John asked John Kamau and John Mwangi.")
    assert out == "a student asked Student C and Student D."
    assert anon.restore(out) == "a student asked John Kamau and John Mwangi."


def test_restore_round_trip_in_text_and_models(anon):
    class Review(BaseModel):
        feedback: str
        strengths: list[str]

    assert anon.restore("Student A, nice work. Student Z isn't anyone.") == "Amina Wanjiru, nice work. Student Z isn't anyone."
    review = anon.restore_model(Review(feedback="Student B explains well", strengths=["Student B's examples"]))
    assert review == Review(feedback="Grace Otieno explains well", strengths=["Grace Otieno's examples"])


def test_no_members_is_a_no_op():
    assert Anonymizer([]).redact("Plain text, no names.") == "Plain text, no names."


# --- wired into the service ----------------------------------------------------------

class Feedback(BaseModel):
    feedback: str


def test_prompts_are_anonymised_and_output_restored(client):
    register(client, "amina@example.com", "Amina Wanjiru")
    reply = {"model": "openai/gpt-6-luna", "usage": {"prompt_tokens": 10, "completion_tokens": 5},
             "choices": [{"message": {"content": '{"feedback": "Student A, clear article."}'}, "finish_reason": "stop"}]}
    service = LLMService(client=make_client())
    with respx.mock(base_url=OPENROUTER_BASE_URL) as mock:
        route = mock.post("/chat/completions").mock(return_value=httpx.Response(200, json=reply))
        import app.llm.service as svc
        original, svc._service = svc._service, service
        try:
            out = grading._parse("You review articles by Amina-free rules.", "Written by Amina Wanjiru (amina@example.com).", Feedback)
        finally:
            svc._service = original
    sent = json.loads(route.calls[-1].request.content)["messages"]
    assert sent[0]["content"].startswith("You review articles by Amina-free rules.")  # system prompt untouched
    assert sent[1]["content"] == "Written by Student A ([email])."
    assert out == Feedback(feedback="Amina Wanjiru, clear article.")


# --- rate limit ----------------------------------------------------------------------

def test_rate_limiter_window():
    now = [0.0]
    rl = RateLimiter(window=100, clock=lambda: now[0])
    assert rl.try_take(1, 2) is None and rl.try_take(1, 2) is None
    assert rl.try_take(1, 2) == 100  # oldest hit expires at t=100
    assert rl.try_take(2, 2) is None  # per user
    now[0] = 50
    assert rl.try_take(1, 2, n=3) == 100  # more than the whole limit never fits: report a full window
    now[0] = 100
    assert rl.try_take(1, 2) is None


@pytest.fixture
def one_per_hour(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_rate_limit_per_hour", 1)
    monkeypatch.setattr(grading, "grade_article", lambda url: (7.0, {"clarity": 3, "technical_accuracy": 2, "depth": 1,
                                                                     "originality": 1}, "Good.", {}))


def article(client, h, challenge_id):
    return client.post("/submissions", headers=h, json={"challenge_id": challenge_id, "submission_type": "article",
                                                        "content": "https://example.com/post"})


def test_over_the_limit_the_task_is_saved_but_not_graded(client, challenge, one_per_hour):
    h, _ = register(client, "m@example.com")
    client.post(f"/challenges/{challenge['id']}/enroll", headers=h)
    first = article(client, h, challenge["id"])
    assert first.status_code == 201
    assert client.get(f"/submissions/{first.json()['id']}", headers=h).json()["grading_status"] == "done"

    second = article(client, h, challenge["id"])
    assert second.status_code == 201  # the work is saved
    body = second.json()
    assert body["grading_status"] == "failed" and "AI limit (1 per hour)" in body["ai_feedback"]

    retry = client.post(f"/submissions/{body['id']}/regrade", headers=h)
    assert retry.status_code == 429 and int(retry.headers["Retry-After"]) > 0
    assert "Try again in about" in retry.json()["detail"]


def test_admins_get_a_higher_limit(client, admin, one_per_hour, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_rate_limit_admin_multiplier", 3)
    body = {"kind": "weekly", "durations": [10, 20, 30]}
    assert client.post("/admin/quizzes/generate", headers=admin, json=body).status_code == 200  # uses all 3
    assert client.post("/admin/quizzes/generate", headers=admin, json={**body, "durations": [10]}).status_code == 429
