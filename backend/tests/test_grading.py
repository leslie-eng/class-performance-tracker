"""Tests for the grading service's own logic.

The rest of the suite mocks `grade_article`/`_parse` away (correctly — those are the network
seams), which left the function bodies themselves uncovered. These exercise the real code with
the two external edges — the URL fetch and the Claude call — stubbed.
"""

import anthropic
import pytest

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
    """Replace the network edges of grade_article: the fetch and the Claude call."""
    monkeypatch.setattr(grading, "fetch_article", lambda url: (title, text))
    return _patch_parse(monkeypatch, parse_result)


def _patch_parse(monkeypatch, result=None):
    captured: dict = {}

    def fake(system, content, output_format, model=None):
        captured.update(system=system, content=content, output_format=output_format)
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


def test_grade_article_rejects_an_over_long_article(monkeypatch):
    monkeypatch.setattr(grading, "fetch_article", lambda url: ("T", "x" * 100))
    monkeypatch.setattr(grading.get_settings(), "article_max_chars", 50)

    with pytest.raises(GradingError, match="too long"):
        grade_article("https://dev.to/x/post")


# --- _parse ----------------------------------------------------------------


def test_parse_raises_on_a_refusal(monkeypatch):
    monkeypatch.setattr(grading, "_client", lambda: _FakeClient(stop_reason="refusal", parsed=None))

    with pytest.raises(GradingError, match="declined"):
        grading._parse(ARTICLE_SYSTEM, "x", ArticleGrade)


def test_parse_raises_when_no_result_comes_back(monkeypatch):
    monkeypatch.setattr(grading, "_client", lambda: _FakeClient(stop_reason="max_tokens", parsed=None))

    with pytest.raises(GradingError, match="no result"):
        grading._parse(ARTICLE_SYSTEM, "x", ArticleGrade)


def test_parse_returns_the_parsed_output(monkeypatch):
    expected = _ok_grade()
    monkeypatch.setattr(grading, "_client", lambda: _FakeClient(stop_reason="end_turn", parsed=expected))

    assert grading._parse(ARTICLE_SYSTEM, "x", ArticleGrade) is expected


# --- review_code -----------------------------------------------------------


def test_review_code_uses_the_daily_task_prompt_without_a_description(monkeypatch):
    captured = _patch_parse(monkeypatch, CodeReview(feedback="  Fine.  "))

    out = review_code("print(1)", "python")

    assert out == "Fine."
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
    monkeypatch.setattr(grading.get_settings(), "anthropic_api_key", None)

    grading.grade_submission(sub_id)

    row = _reload(sub_id)
    assert row.grading_status.value == "failed"
    assert "isn't configured" in row.ai_feedback
    assert row.points_awarded == 15  # base article points still stand; only grading failed


def test_submission_survives_an_api_error(client, challenge, monkeypatch):
    sub_id = _pending_article(client, challenge, monkeypatch)

    def boom(url):
        raise _FakeAPIError()

    monkeypatch.setattr(grading, "grade_article", boom)

    grading.grade_submission(sub_id)

    row = _reload(sub_id)
    assert row.grading_status.value == "failed"
    assert "Grading service error" in row.ai_feedback


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


class _FakeAPIError(anthropic.APIError):
    """Bypasses the SDK constructor (whose signature varies by version) but keeps isinstance()."""

    def __init__(self):
        Exception.__init__(self, "simulated API failure")


class _FakeResponse:
    def __init__(self, stop_reason, parsed):
        self.stop_reason = stop_reason
        self.parsed_output = parsed


class _FakeClient:
    def __init__(self, stop_reason, parsed):
        response = _FakeResponse(stop_reason, parsed)

        class _Messages:
            @staticmethod
            def parse(**kwargs):
                return response

        self.beta = type("Beta", (), {"messages": _Messages()})()
