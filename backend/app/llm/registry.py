"""Models the app may use, by friendly name.

Prices are USD per million tokens, copied from https://openrouter.ai/api/v1/models on
2026-10-12; they're for display and estimates only (the real cost comes back in each
response's `usage.cost`). `zdr` means OpenRouter lists at least one Zero Data Retention
endpoint for the model (https://openrouter.ai/api/v1/endpoints/zdr). Models without one
must never see student data: they're for the test button and the comparison script.

Settings may also name any raw OpenRouter id ("vendor/model"); those are treated as
non-ZDR unless listed here.
"""

import re
from dataclasses import dataclass

TASKS = ("grading", "feedback", "summary", "generation")
# grading:    article rubric scores, short quiz answers
# feedback:   comments on daily code and coding-exercise attempts
# summary:    weekly class-notes summary, learning-material digests
# generation: quizzes and coding exercises (long, strictly validated JSON)


@dataclass(frozen=True)
class ModelInfo:
    key: str
    id: str
    label: str
    tier: str  # free | cheap | strong
    prompt_price: float  # USD per 1M input tokens
    completion_price: float  # USD per 1M output tokens
    context: int
    zdr: bool
    notes: str

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.prompt_price + tokens_out * self.completion_price) / 1_000_000


MODELS: dict[str, ModelInfo] = {
    m.key: m
    for m in [
        ModelInfo("gemma-free", "google/gemma-4-31b-it:free", "Gemma 4 31B (free)", "free", 0, 0, 262_144, False,
                  "Testing only: no zero-retention provider, may log or train on prompts. 20/min, 50 or 1000/day."),
        ModelInfo("nemotron-free", "nvidia/nemotron-3-super-120b-a12b:free", "Nemotron 3 Super (free)", "free", 0, 0,
                  262_144, False, "Testing only: no zero-retention provider. Same free-tier limits."),
        ModelInfo("luna", "openai/gpt-6-luna", "GPT-6 Luna", "cheap", 0.10, 0.50, 1_050_000, True,
                  "Default for grading, feedback and summaries. Zero retention via Azure."),
        ModelInfo("mistral-small", "mistralai/mistral-small-2603", "Mistral Small", "cheap", 0.15, 0.60, 262_144, True,
                  "First fallback, from a different vendor. Zero retention via Mistral."),
        ModelInfo("gemini-flash", "google/gemini-3.8-flash", "Gemini 3.8 Flash", "strong", 0.75, 3.75, 1_048_576, True,
                  "Quiz and exercise generation, last fallback. Zero retention via Google."),
    ]
}

_BY_ID = {m.id: m for m in MODELS.values()}


class UnknownModel(ValueError):
    pass


def resolve(name: str) -> str:
    """Friendly name or raw OpenRouter id -> OpenRouter id."""
    name = name.strip()
    if name in MODELS:
        return MODELS[name].id
    if "/" in name:
        return name
    raise UnknownModel(f"Unknown model {name!r}: use one of {', '.join(MODELS)} or an OpenRouter id like vendor/model")


def canonical(model_id: str) -> str:
    """Responses may name a dated variant ("openai/gpt-6-luna-20260901"); map it to the
    registry id so usage groups correctly. "gpt-6-luna-pro" is a different model and isn't."""
    if model_id in _BY_ID:
        return model_id
    for known in _BY_ID:
        if re.fullmatch(re.escape(known.split(":")[0]) + r"-\d{4,8}(?::\w+)?", model_id):
            return known
    return model_id


def info(model_id: str) -> ModelInfo | None:
    return _BY_ID.get(canonical(model_id))


def is_zdr(model_id: str) -> bool:
    m = info(model_id)
    return bool(m and m.zdr)
