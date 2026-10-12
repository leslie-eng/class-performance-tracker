"""Admin: which AI model each task uses, switched live, and a test button."""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app import llm
from app.config import get_settings
from app.deps import DB, AdminUser
from app.llm import overrides, registry, usage
from app.llm.ratelimit import Quota

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/llm", tags=["admin"])

SAMPLE_PROMPT = "In two sentences, explain what a Python list comprehension is, then give a one-line example."


class ModelOut(BaseModel):
    key: str
    id: str
    label: str
    tier: str
    prompt_price: float
    completion_price: float
    context: int
    zdr: bool
    allowed_for_member_data: bool
    notes: str


class TaskOut(BaseModel):
    task: str
    model_id: str
    label: str
    source: Literal["admin", "env", "default"]


class LLMConfigOut(BaseModel):
    configured: bool
    require_zdr: bool
    tasks: list[TaskOut]
    fallbacks: list[str]
    models: list[ModelOut]


class TaskModelIn(BaseModel):
    model: str | None = Field(default=None, description="Registry key or OpenRouter id; null = back to env settings")


class TestIn(BaseModel):
    model: str
    prompt: str | None = Field(default=None, max_length=2000)


class TestOut(BaseModel):
    text: str
    model_used: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost: float | None
    cost_estimated: bool


def label(model_id: str) -> str:
    m = registry.info(model_id)
    return m.label if m else model_id


def allowed_for_member_data(model_id: str) -> bool:
    return registry.is_zdr(model_id) or not get_settings().llm_require_zdr


def config_out() -> LLMConfigOut:
    service, s = llm.get_llm(), get_settings()
    tasks = []
    for task in registry.TASKS:
        model_id, source = service.model_source(task)
        tasks.append(TaskOut(task=task, model_id=model_id, label=label(model_id), source=source))
    return LLMConfigOut(
        configured=llm.ai_configured(),
        require_zdr=s.llm_require_zdr,
        tasks=tasks,
        fallbacks=[registry.resolve(n) for n in s.llm_fallback_list],
        models=[
            ModelOut(**{k: getattr(m, k) for k in ModelOut.model_fields if hasattr(m, k)},
                     allowed_for_member_data=allowed_for_member_data(m.id))
            for m in registry.MODELS.values()
        ],
    )


@router.get("", response_model=LLMConfigOut)
def get_config(_: AdminUser):
    return config_out()


@router.get("/usage")
def get_usage(db: DB, _: AdminUser, days: int = Query(30, ge=1, le=365)) -> dict:
    """Calls, errors, fallbacks, tokens, cost and latency per model and per task."""
    return usage.summarize(db, days)


@router.put("/tasks/{task}", response_model=LLMConfigOut)
def set_task_model(task: str, body: TaskModelIn, db: DB, admin: AdminUser):
    if task not in registry.TASKS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown task; use one of {', '.join(registry.TASKS)}")
    model_id = None
    if body.model:
        try:
            model_id = registry.resolve(body.model)
        except registry.UnknownModel as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        if not allowed_for_member_data(model_id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{label(model_id)} has no zero-retention provider, so it can't handle member data. "
                "Use it only with the test button.",
            )
    overrides.set_override(db, task, model_id, admin.id)
    log.info("Admin %s set the %s model to %s", admin.id, task, model_id or "the env default")
    return config_out()


@router.post("/test", response_model=TestOut)
def test_model(body: TestIn, _: AdminUser, quota: Quota):
    """Sends a sample (or your own) prompt to one model, without fallbacks."""
    try:
        model_id = registry.resolve(body.model)
    except registry.UnknownModel as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    private = registry.is_zdr(model_id)
    if body.prompt and not private:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Custom prompts are only allowed for zero-retention models; this one may log prompts. Use the sample prompt.",
        )
    quota.take()
    try:
        result = llm.get_llm().generate(
            "feedback",
            [{"role": "user", "content": body.prompt or SAMPLE_PROMPT}],
            models=[model_id],
            sensitive=private,
            max_tokens=400,
        )
    except llm.LLMNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except llm.LLMError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    cost, estimated = result.cost, False
    if cost is None and (m := registry.info(result.model_used) or registry.info(model_id)):
        cost, estimated = m.estimate_cost(result.tokens_in, result.tokens_out), True
    return TestOut(
        text=result.text, model_used=result.model_used, latency_ms=result.latency_ms,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out, cost=cost, cost_estimated=estimated,
    )
