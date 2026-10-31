"""generate(task, messages): one call to OpenRouter with a fallback chain, retries and
optional Pydantic-validated JSON output.

- The model chain for a task is [task model or default model] + fallbacks, sent as
  OpenRouter's `models` list, so OpenRouter moves down the chain when a model is
  down, rate-limited or rejects the request. We retry the whole call only on 408/429/5xx,
  timeouts and connection errors, with exponential backoff.
- `sensitive=True` (the default, for anything built from members' work) asks OpenRouter
  for Zero Data Retention endpoints that don't collect data, and drops non-ZDR models
  from the chain. Free models therefore only run when `sensitive=False`.
- Every LLMError message is safe to show to members and admins. Prompts, outputs and the
  API key are never logged.
"""

import json
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm import overrides, registry, usage
from app.llm.anonymize import Anonymizer
from app.llm.client import make_client

log = logging.getLogger(__name__)

MAX_CHAIN = 3  # OpenRouter doesn't document a limit for `models`; keep chains short
RETRYABLE = {408, 429, 500, 502, 503, 504}
MAX_RETRY_AFTER = 30.0


class LLMError(Exception):
    """Base class; the message is safe to show to users."""


class LLMNotConfigured(LLMError):
    pass


class LLMRequestError(LLMError):
    """A 4xx the caller can't fix by retrying: bad key, no credit, blocked, bad request."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class LLMUnavailable(LLMError):
    """Every retry failed with a temporary error (rate limits, outages, timeouts)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class LLMInvalidOutput(LLMError):
    """The model's reply wasn't valid JSON for the requested schema, even after one retry."""


@dataclass
class LLMResult:
    text: str
    model_used: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    fallback_used: bool
    cost: float | None  # USD, from OpenRouter's usage.cost
    parsed: Any = None  # the validated Pydantic object when `output` was given
    model_requested: str = ""  # first model in the chain


_STATUS_MESSAGES = {
    401: "OpenRouter rejected the API key; check OPENROUTER_API_KEY",
    402: "The OpenRouter account is out of credit",
    403: "OpenRouter blocked this request (moderation or a spending limit)",
    404: "No model is available for this request; check the model names and privacy settings",
}

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def ai_configured() -> bool:
    return bool(get_settings().openrouter_api_key)


def _same_model(used: str, wanted: str) -> bool:
    return registry.canonical(used) == registry.canonical(wanted)


def _error_message(body: Any) -> str:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return str(body["error"].get("message", ""))[:200]
    return ""


def _json_instruction(output: type[BaseModel]) -> str:
    schema = json.dumps(output.model_json_schema(), separators=(",", ":"))
    return f"\n\nReply with only a JSON object (no prose, no code fences) that matches this JSON Schema:\n{schema}"


class LLMService:
    def __init__(
        self,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        recorder: Callable[[usage.CallRecord], None] | None = None,
    ):
        self._client = client
        self._sleep = sleep
        self._record = recorder or usage.record_call

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = make_client()
        return self._client

    # --- model selection --------------------------------------------------------

    def model_for(self, task: str) -> str:
        return self.model_source(task)[0]

    def model_source(self, task: str) -> tuple[str, str]:
        """(model id, where it came from): "admin" (chosen in the app), "env" (LLM_TASK_MODELS)
        or "default" (LLM_DEFAULT_MODEL)."""
        if task not in registry.TASKS:
            raise ValueError(f"unknown LLM task {task!r}")
        chosen = overrides.get_overrides().get(task)
        if chosen:
            return chosen, "admin"
        s = get_settings()
        if task in s.llm_task_model_map:
            return registry.resolve(s.llm_task_model_map[task]), "env"
        return registry.resolve(s.llm_default_model), "default"

    def chain(self, task: str, sensitive: bool = True) -> list[str]:
        s = get_settings()
        names = [self.model_for(task)] + [registry.resolve(n) for n in s.llm_fallback_list]
        out: list[str] = []
        for model_id in names:
            if model_id in out:
                continue
            if sensitive and s.llm_require_zdr and not registry.is_zdr(model_id):
                log.warning("Skipping %s for task %s: no zero-retention endpoint for sensitive data", model_id, task)
                continue
            out.append(model_id)
        if not out:
            raise LLMError("No configured AI model is approved for member data; check LLM_* settings")
        return out[:MAX_CHAIN]

    # --- generation -------------------------------------------------------------

    def generate(
        self,
        task: str,
        messages: list[dict],
        *,
        output: type[BaseModel] | None = None,
        models: list[str] | None = None,
        sensitive: bool = True,
        max_tokens: int | None = None,
        anonymizer: Anonymizer | None = None,
    ) -> LLMResult:
        """`models` overrides the task's chain (friendly names or ids), e.g. for the test button.
        With an `anonymizer`, non-system messages are redacted before sending and names are
        restored in the text and parsed output."""
        s = get_settings()
        if not s.openrouter_api_key:
            raise LLMNotConfigured("AI isn't configured on this server yet (OPENROUTER_API_KEY)")
        if anonymizer is not None:
            messages = [m if m["role"] == "system" else {**m, "content": anonymizer.redact(m["content"])}
                        for m in messages]
        started, requested = time.monotonic(), None
        try:
            chain = [registry.resolve(m) for m in models] if models else self.chain(task, sensitive)
            requested = chain[0]
            if sensitive and s.llm_require_zdr and not all(registry.is_zdr(m) for m in chain):
                raise LLMError("That model isn't approved for member data (no zero-retention endpoint)")
            result = self._generate(task, messages, chain, output, sensitive, max_tokens)
        except LLMError as e:
            self._save(usage.CallRecord.failure(task, requested, e, started))
            raise
        result.model_requested = requested
        result.latency_ms = int((time.monotonic() - started) * 1000)  # whole call, retries included
        self._save(usage.CallRecord.success(task, result))
        if anonymizer is not None:
            result.text = anonymizer.restore(result.text)
            if result.parsed is not None:
                result.parsed = anonymizer.restore_model(result.parsed)
        return result

    def _save(self, record: "usage.CallRecord") -> None:
        try:
            self._record(record)
        except Exception:  # usage logging must never break an AI call
            log.warning("Couldn't record LLM usage for task %s", record.task, exc_info=True)

    def _generate(self, task: str, messages: list[dict], chain: list[str], output: type[BaseModel] | None,
                  sensitive: bool, max_tokens: int | None) -> LLMResult:
        s = get_settings()
        body: dict[str, Any] = {
            "models": chain[:MAX_CHAIN],
            "messages": messages,
            "max_tokens": max_tokens or s.llm_max_tokens,
            "provider": {"require_parameters": True},
        }
        if sensitive and s.llm_require_zdr:
            body["provider"].update({"zdr": True, "data_collection": "deny"})
        if output is not None:
            body["messages"] = self._with_json_instruction(messages, output)
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": output.__name__, "strict": False, "schema": output.model_json_schema()},
            }

        result = self._call(task, body)
        if output is None:
            return result
        try:
            result.parsed = self._parse_output(result.text, output)
            return result
        except (ValueError, ValidationError) as e:
            problem = str(e).splitlines()[0][:300]
            log.warning("llm task=%s model=%s returned invalid JSON; retrying once", task, result.model_used)
        retry_body = {
            **body,
            "messages": body["messages"] + [
                {"role": "assistant", "content": result.text[:4000]},
                {"role": "user", "content": f"That reply was not valid for the schema ({problem}). "
                                            "Reply again with only the corrected JSON object."},
            ],
        }
        second = self._call(task, retry_body)
        try:
            second.parsed = self._parse_output(second.text, output)
        except (ValueError, ValidationError) as e:
            raise LLMInvalidOutput("The AI returned an answer in the wrong format; try again") from e
        second.tokens_in += result.tokens_in
        second.tokens_out += result.tokens_out
        second.cost = None if result.cost is None or second.cost is None else result.cost + second.cost
        return second

    @staticmethod
    def _with_json_instruction(messages: list[dict], output: type[BaseModel]) -> list[dict]:
        out = [dict(m) for m in messages]
        instruction = _json_instruction(output)
        for m in out:
            if m["role"] == "system":
                m["content"] = m["content"] + instruction
                return out
        return [{"role": "system", "content": instruction.strip()}] + out

    @staticmethod
    def _parse_output(text: str, output: type[BaseModel]) -> BaseModel:
        cleaned = _FENCE.sub("", text.strip())
        return output.model_validate_json(cleaned)

    def _call(self, task: str, body: dict) -> LLMResult:
        s = get_settings()
        headers = {"Authorization": f"Bearer {s.openrouter_api_key}"}
        attempts = s.llm_max_retries + 1
        last, last_status = "no response", None
        for attempt in range(attempts):
            started = time.monotonic()
            retry_after = None
            try:
                resp = self.client.post("/chat/completions", json=body, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = type(e).__name__
            else:
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                status = resp.status_code
                # Errors during generation arrive as 200 with an `error` object and no choices.
                if status == 200 and isinstance(data, dict) and "error" in data and not data.get("choices"):
                    status = int(data["error"].get("code") or 502)
                if status == 200 and isinstance(data, dict) and data.get("choices"):
                    return self._result(task, body, data, started)
                last, last_status = f"HTTP {status}", status
                if status not in RETRYABLE:
                    message = _STATUS_MESSAGES.get(status) or f"The AI request was rejected ({_error_message(data) or last})"
                    log.warning("llm task=%s failed: %s", task, last)
                    raise LLMRequestError(message, status)
                retry_after = resp.headers.get("retry-after")
            if attempt + 1 < attempts:
                delay = 2 ** attempt + random.uniform(0, 0.5)
                if retry_after:
                    try:
                        delay = min(max(delay, float(retry_after)), MAX_RETRY_AFTER)
                    except ValueError:
                        pass
                log.info("llm task=%s temporary failure (%s); retry %d in %.1fs", task, last, attempt + 1, delay)
                self._sleep(delay)
        log.warning("llm task=%s gave up after %d attempts: %s", task, attempts, last)
        raise LLMUnavailable(f"The AI service is busy or unavailable right now ({last}); try again shortly", last_status)

    @staticmethod
    def _result(task: str, body: dict, data: dict, started: float) -> LLMResult:
        choice = data["choices"][0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        model_used = data.get("model") or body["models"][0]
        result = LLMResult(
            text=text,
            model_used=model_used,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            latency_ms=int((time.monotonic() - started) * 1000),
            fallback_used=not _same_model(model_used, body["models"][0]),
            cost=float(usage["cost"]) if usage.get("cost") is not None else None,
        )
        log.info(
            "llm task=%s model=%s fallback=%s tokens_in=%d tokens_out=%d latency_ms=%d cost=%s finish=%s",
            task, result.model_used, result.fallback_used, result.tokens_in, result.tokens_out,
            result.latency_ms, f"{result.cost:.6f}" if result.cost is not None else "?", choice.get("finish_reason"),
        )
        return result


_service: LLMService | None = None


def get_llm() -> LLMService:
    """FastAPI dependency (and plain accessor for background jobs)."""
    global _service
    if _service is None:
        _service = LLMService()
    return _service
