"""Step 5: every AI call leaves one usage row (no content), and usage summarises per model."""

import httpx
import pytest
import respx
from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.llm import LLMRequestError, LLMService, LLMUnavailable, registry
from app.llm.anonymize import Anonymizer, Person
from app.llm.client import OPENROUTER_BASE_URL, make_client
from app.llm.usage import format_table, summarize
from app.models import LLMCall
from tests.conftest import register

LUNA, MISTRAL = "openai/gpt-6-luna", "mistralai/mistral-small-2603"
MESSAGES = [{"role": "system", "content": "Review."}, {"role": "user", "content": "Code by Amina Wanjiru"}]


class Out(BaseModel):
    feedback: str


def reply(content: str, model: str = LUNA, cost: float | None = 0.0003, tokens=(100, 20)) -> dict:
    usage = {"prompt_tokens": tokens[0], "completion_tokens": tokens[1], **({"cost": cost} if cost is not None else {})}
    return {"model": model, "usage": usage, "choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


@pytest.fixture
def service():
    return LLMService(client=make_client(), sleep=lambda s: None)


@pytest.fixture
def api():
    with respx.mock(base_url=OPENROUTER_BASE_URL, assert_all_called=False) as mock:
        yield mock.post("/chat/completions")


def calls(db) -> list[LLMCall]:
    db.expire_all()
    return db.scalars(select(LLMCall).order_by(LLMCall.id)).all()


def test_success_records_one_row_without_content(service, api, db):
    api.mock(return_value=httpx.Response(200, json=reply("Nice.", model=LUNA + "-20260901")))
    service.generate("feedback", MESSAGES, anonymizer=Anonymizer([Person("Amina Wanjiru")]))
    [row] = calls(db)
    assert (row.task, row.model_requested, row.model_used, row.fallback_used) == ("feedback", LUNA, LUNA, False)
    assert (row.tokens_in, row.tokens_out, row.cost, row.cost_estimated, row.ok) == (100, 20, 0.0003, False, True)
    stored = " ".join(str(getattr(row, c.name)) for c in LLMCall.__table__.columns)
    assert "Amina" not in stored and "Nice" not in stored and "Review" not in stored


def test_fallback_and_estimated_cost(service, api, db):
    api.mock(return_value=httpx.Response(200, json=reply("ok", model=MISTRAL, cost=None, tokens=(1_000_000, 0))))
    service.generate("feedback", MESSAGES)
    [row] = calls(db)
    assert row.model_used == MISTRAL and row.fallback_used is True
    assert row.cost == pytest.approx(0.15) and row.cost_estimated is True


def test_json_retry_is_one_row_with_summed_tokens(service, api, db):
    api.side_effect = [httpx.Response(200, json=reply("not json")), httpx.Response(200, json=reply('{"feedback": "ok"}'))]
    service.generate("grading", MESSAGES, output=Out)
    [row] = calls(db)
    assert row.tokens_in == 200 and row.cost == pytest.approx(0.0006)


def test_failures_are_recorded_with_type_and_status(service, api, db):
    api.mock(return_value=httpx.Response(402, json={"error": {"code": 402, "message": "no credit"}}))
    with pytest.raises(LLMRequestError):
        service.generate("summary", MESSAGES)
    api.mock(return_value=httpx.Response(503, json={"error": {"code": 503, "message": "busy"}}))
    with pytest.raises(LLMUnavailable):
        service.generate("summary", MESSAGES)
    a, b = calls(db)
    assert (a.ok, a.error_type, a.http_status, a.model_requested, a.model_used) == (False, "LLMRequestError", 402, LUNA, None)
    assert (b.error_type, b.http_status) == ("LLMUnavailable", 503)


def test_not_configured_is_not_logged(service, api, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "openrouter_api_key", None)
    with pytest.raises(Exception):
        service.generate("summary", MESSAGES)
    assert calls(db) == []


def test_a_broken_usage_log_never_breaks_the_ai_call(api):
    def broken(_):
        raise RuntimeError("db down")

    api.mock(return_value=httpx.Response(200, json=reply("still fine")))
    service = LLMService(client=make_client(), recorder=broken)
    assert service.generate("feedback", MESSAGES).text == "still fine"


def test_canonical_ids():
    assert registry.canonical(LUNA + "-20260901") == LUNA
    assert registry.canonical("openai/gpt-6-luna-pro") == "openai/gpt-6-luna-pro"  # a different model
    assert registry.canonical("vendor/unknown") == "vendor/unknown"


def test_summary_per_model_and_task(db):
    rows = [
        LLMCall(task="grading", model_requested=LUNA, model_used=LUNA, tokens_in=100, tokens_out=10, latency_ms=lat, cost=0.001, ok=True)
        for lat in (100, 200, 300, 400)
    ] + [
        LLMCall(task="summary", model_requested=LUNA, model_used=MISTRAL, fallback_used=True, tokens_in=50, tokens_out=5,
                latency_ms=900, cost=0.002, ok=True),
        LLMCall(task="summary", model_requested=LUNA, model_used=None, latency_ms=5000, ok=False,
                error_type="LLMUnavailable", http_status=503),
    ]
    db.add_all(rows)
    db.commit()
    s = summarize(db, 30)
    luna = next(g for g in s["by_model"] if g["name"] == LUNA)
    mistral = next(g for g in s["by_model"] if g["name"] == MISTRAL)
    assert (luna["label"], luna["calls"], luna["errors"], luna["cost"]) == ("GPT-6 Luna", 5, 1, 0.004)
    assert luna["avg_latency_ms"] == 250 and luna["p95_latency_ms"] == 400 and luna["cost_per_call"] == 0.001
    assert luna["error_types"] == ["LLMUnavailable"]
    assert (mistral["fallbacks"], mistral["cost"]) == (1, 0.002)
    assert s["totals"] == {"calls": 6, "errors": 1, "cost": 0.006, "tokens_in": 450, "tokens_out": 45}
    assert {g["name"]: g["calls"] for g in s["by_task"]} == {"grading": 4, "summary": 2}
    table = format_table(s)
    assert "GPT-6 Luna" in table and "Error types: LLMUnavailable" in table


def test_usage_endpoint_is_admin_only(client, admin):
    h, _ = register(client, "m@example.com")
    assert client.get("/admin/llm/usage", headers=h).status_code == 403
    body = client.get("/admin/llm/usage?days=7", headers=admin).json()
    assert body["days"] == 7 and body["totals"]["calls"] == 0
    assert client.get("/admin/llm/usage?days=0", headers=admin).status_code == 422
