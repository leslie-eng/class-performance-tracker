"""Tests for the grading service's own logic.

The rest of the suite mocks `grade_article`/`_parse` away (correctly — those are the network
seams), which left the function bodies themselves uncovered. These exercise the real code with
the two external edges — the URL fetch and the AI call (app.llm) — stubbed.
"""

import pytest

from app import llm
from app.config import get_settings
from app.services import grading
from app.services.grading import (
    ARTICLE_SYSTEM,
    CODE_SYSTEM,
    EXERCISE_SYSTEM,
    ArticleGrade,
    CodeReview,
    GradingError,
    grade_article,
    review_code,
)
from tests.conftest import register


def _patch_edges(monkeypatch, text="A short article body.", title="Decorators", parse_result=None):
    """Replace the network edges of grade_article: the fetch and the AI call."""
    monkeypatch.setattr(grading, "fetch_article", lambda url: (title, text))
    return _patch_parse(monkeypatch, parse_result)


def _patch_parse(monkeypatch, result=None):
    captured: dict = {}

    def fake(system, content, output_format, task="grading"):
        captured.update(system=system, content=content, output_format=output_format, task=task)
        return result

    monkeypatch.setattr(grading, "_parse", fake)
    return captured


# --- grade_article ---------------------------------------------------------


def test_grade_article_scores_and_trims(monkeypatch):
    # Deliberately out of range / messy: the service must clamp, filter and truncate.
    _patch_edges(monkeypatch)
    fake = ArticleGrade(
        clarity=9,  # above the 0-3 max -> clamp to 3
        technical_accuracy=-4,  # below 0 -> clamp to 0
        depth=2,
        originality=2,
        feedback="  Good work.  ",
        strengths=["clear", "  ", "focused", "concise", "extra"],  # blank dropped, capped at 3
        improvements=["add tests", "show output"],
    )
    monkeypatch.setattr(grading, "_parse", lambda *a, **k: fake)

    score, breakdown, feedback, details = grade_article("https://dev.to/x/post")

    assert breakdown == {"clarity": 3, "technical_accuracy": 0, "depth": 2, "originality": 2}
    assert score == 7.0
    assert feedback == "Good work."  # stripped
    assert details["title"] == "Decorators"
    assert details["strengths"] == ["clear", "focused", "concise"]  # blank removed, 3 kept
    assert details["improvements"] == ["add tests", "show output"]


def test_grade_article_passes_title_and_url_into_the_prompt(monkeypatch):
    captured = _patch_edges(monkeypatch, text="Body text here.", title="My Title", parse_result=_ok_grade())

    grade_article("https://dev.to/x/post")

    assert captured["system"] == ARTICLE_SYSTEM
    assert "My Title" in captured["content"]
    assert "Body text here." in captured["content"]
    assert "https://dev.to/x/post" in captured["content"]
    assert captured["output_format"] is ArticleGrade
    assert captured["task"] == "grading"


def test_grade_article_rejects_an_over_long_article(monkeypatch):
    monkeypatch.setattr(grading, "fetch_article", lambda url: ("T", "x" * 100))
    monkeypatch.setattr(grading.get_settings(), "article_max_chars", 50)

    with pytest.raises(GradingError, match="too long"):
        grade_article("https://dev.to/x/post")


# --- _parse ----------------------------------------------------------------


def test_parse_returns_the_parsed_output_and_records_the_model(monkeypatch):
    expected = _ok_grade()
    service = _FakeService(parsed=expected)
    monkeypatch.setattr(llm, "get_llm", lambda: service)

    assert grading._parse(ARTICLE_SYSTEM, "x", ArticleGrade) is expected
    assert grading.take_last_model() == "openai/gpt-6-luna"
    assert grading.take_last_model() is None  # taken once
    [call] = service.calls
    assert call["task"] == "grading" and call["output"] is ArticleGrade
    assert call["messages"] == [{"role": "system", "content": ARTICLE_SYSTEM}, {"role": "user", "content": "x"}]


def test_parse_passes_the_task_through(monkeypatch):
    service = _FakeService(parsed=CodeReview(feedback="ok"))
    monkeypatch.setattr(llm, "get_llm", lambda: service)

    grading._parse(CODE_SYSTEM, "x", CodeReview, task="feedback")

    assert service.calls[0]["task"] == "feedback"


def test_parse_raises_a_readable_error_on_bad_output(monkeypatch):
    """Invalid JSON after app.llm's own retry surfaces as a GradingError members can read."""
    service = _FakeService(error=llm.LLMInvalidOutput("The AI returned an answer in the wrong format; try again"))
    monkeypatch.setattr(llm, "get_llm", lambda: service)

    with pytest.raises(GradingError, match="wrong format"):
        grading._parse(ARTICLE_SYSTEM, "x", ArticleGrade)


def test_parse_anonymises_member_names(client, monkeypatch):
    register(client, "amina@example.com", "Amina Wanjiru")
    service = _FakeService(parsed=_ok_grade())
    monkeypatch.setattr(llm, "get_llm", lambda: service)

    grading._parse(ARTICLE_SYSTEM, "Written by Amina Wanjiru", ArticleGrade)

    anonymizer = service.calls[0]["anonymizer"]
    assert anonymizer is not None and anonymizer.redact("Written by Amina Wanjiru") == "Written by Student A"


# --- review_code -----------------------------------------------------------


def test_review_code_uses_the_daily_task_prompt_without_a_description(monkeypatch):
    captured = _patch_parse(monkeypatch, CodeReview(feedback="  Fine.  "))

    out = review_code("print(1)", "python")

    assert out == "Fine."
    assert captured["task"] == "feedback"
    assert captured["system"] == CODE_SYSTEM
    assert captured["output_format"] is CodeReview
    assert "print(1)" in captured["content"]


def test_review_code_uses_the_exercise_prompt_and_includes_test_results(monkeypatch):
    captured = _patch_parse(monkeypatch, CodeReview(feedback="Good."))

    review_code("def f(): pass", "python", description="Write f().", test_summary="2/2 passed")

    assert captured["system"] == EXERCISE_SYSTEM
    assert "Write f()." in captured["content"]
    assert "2/2 passed" in captured["content"]


# --- grade_submission: failure paths the API tests don't reach -------------


def test_submission_fails_readably_when_no_api_key_is_configured(client, challenge, monkeypatch):
    """Without a key, articles must fail with a message an admin can act on, not a crash."""
    sub_id = _pending_article(client, challenge, monkeypatch)
    monkeypatch.setattr(grading.get_settings(), "openrouter_api_key", None)

    grading.grade_submission(sub_id)

    row = _reload(sub_id)
    assert row.grading_status.value == "failed"
    assert "isn't configured" in row.ai_feedback
    assert row.points_awarded == 15  # base article points still stand; only grading failed


def test_submission_survives_an_api_error(client, challenge, monkeypatch):
    sub_id = _pending_article(client, challenge, monkeypatch)

    def boom(url):
        raise llm.LLMUnavailable("The AI service is busy or unavailable right now (HTTP 503); try again shortly", 503)

    monkeypatch.setattr(grading, "grade_article", boom)

    grading.grade_submission(sub_id)

    row = _reload(sub_id)
    assert row.grading_status.value == "failed"
    assert "busy or unavailable" in row.ai_feedback


def test_grade_submission_is_a_noop_for_an_already_graded_row(client, challenge, monkeypatch):
    """The background task can be retried; it must not re-grade a finished row."""
    sub_id = _pending_article(client, challenge, monkeypatch)
    monkeypatch.setattr(grading, "grade_article", lambda url: (9.0, {"clarity": 3}, "done", {}))
    grading.grade_submission(sub_id)
    assert _reload(sub_id).ai_score == 9.0

    # Second run: swap the grader for one that would explode, proving it never runs.
    monkeypatch.setattr(grading, "grade_article", lambda url: pytest.fail("re-graded a finished row"))
    grading.grade_submission(sub_id)
    assert _reload(sub_id).ai_score == 9.0


# --- helpers ---------------------------------------------------------------


def _ok_grade() -> ArticleGrade:
    return ArticleGrade(
        clarity=3, technical_accuracy=3, depth=2, originality=2,
        feedback="Great.", strengths=["a"], improvements=["b"],
    )


def _pending_article(client, challenge, monkeypatch) -> int:
    """Create an article submission and stop the background grader, so the row stays pending."""
    from app.routers import submissions as submissions_router

    monkeypatch.setattr(submissions_router, "grade_submission", lambda sub_id: None)
    headers = _member(client, challenge)
    resp = client.post(
        "/submissions",
        headers=headers,
        json={"challenge_id": challenge["id"], "submission_type": "article", "content": "https://dev.to/x/post"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["grading_status"] == "pending"
    return resp.json()["id"]


def _member(client, challenge):
    headers, _ = register(client, "graded@example.com", "Graded Member")
    assert client.post(f"/challenges/{challenge['id']}/enroll", headers=headers).status_code == 201
    return headers


def _reload(submission_id: int):
    from app.db import SessionLocal
    from app.models import Submission

    with SessionLocal() as db:
        return db.get(Submission, submission_id)


class _FakeService:
    """Stands in for app.llm.LLMService: records each generate() call."""

    def __init__(self, parsed=None, error=None):
        self.parsed, self.error, self.calls = parsed, error, []

    def generate(self, task, messages, *, output=None, anonymizer=None, **kwargs):
        self.calls.append({"task": task, "messages": messages, "output": output, "anonymizer": anonymizer})
        if self.error:
            raise self.error
        return llm.LLMResult(text="{}", model_used="openai/gpt-6-luna", tokens_in=1, tokens_out=1,
                             latency_ms=1, fallback_used=False, cost=None, parsed=self.parsed)
