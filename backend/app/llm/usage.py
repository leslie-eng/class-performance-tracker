"""Usage log for AI calls (llm_calls table) and the per-model summary used to compare models.

One row per generate() call: task, models, tokens, latency, cost and error type. Nothing
from the prompt or the reply is stored, and no member id.
"""

import logging
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import registry

log = logging.getLogger(__name__)


@dataclass
class CallRecord:
    task: str
    model_requested: str | None
    model_used: str | None
    fallback_used: bool
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost: float | None
    cost_estimated: bool
    ok: bool
    error_type: str | None = None
    http_status: int | None = None

    @classmethod
    def success(cls, task: str, result) -> "CallRecord":
        cost, estimated = result.cost, False
        if cost is None and (m := registry.info(result.model_used)):
            cost, estimated = m.estimate_cost(result.tokens_in, result.tokens_out), True
        return cls(
            task=task, model_requested=result.model_requested, model_used=registry.canonical(result.model_used),
            fallback_used=result.fallback_used, tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            latency_ms=result.latency_ms, cost=cost, cost_estimated=estimated, ok=True,
        )

    @classmethod
    def failure(cls, task: str, model_requested: str | None, error: Exception, started: float) -> "CallRecord":
        return cls(
            task=task, model_requested=model_requested, model_used=None, fallback_used=False, tokens_in=0,
            tokens_out=0, latency_ms=int((time.monotonic() - started) * 1000), cost=None, cost_estimated=False,
            ok=False, error_type=type(error).__name__[:40], http_status=getattr(error, "status", None),
        )


def record_call(record: CallRecord) -> None:
    from app.db import SessionLocal
    from app.models import LLMCall

    with SessionLocal() as db:
        db.add(LLMCall(**asdict(record)))
        db.commit()


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]


def _group(rows, key) -> list[dict]:
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(key(r) or "unknown", []).append(r)
    out = []
    for name, items in groups.items():
        ok = [r for r in items if r.ok]
        cost = sum(r.cost or 0 for r in ok)
        latencies = [r.latency_ms for r in ok]
        info = registry.info(name)
        out.append({
            "name": name,
            "label": info.label if info else name,
            "calls": len(items),
            "errors": len(items) - len(ok),
            "fallbacks": sum(1 for r in ok if r.fallback_used),
            "tokens_in": sum(r.tokens_in for r in ok),
            "tokens_out": sum(r.tokens_out for r in ok),
            "cost": round(cost, 6),
            "cost_estimated": any(r.cost_estimated for r in ok),
            "cost_per_call": round(cost / len(ok), 6) if ok else 0.0,
            "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
            "p95_latency_ms": _p95(latencies),
            "error_types": sorted({r.error_type for r in items if r.error_type}),
        })
    return sorted(out, key=lambda g: (-g["calls"], g["name"]))


def summarize(db: Session, days: int = 30) -> dict:
    """Usage per model (the model that answered; failed calls count against the model asked for)
    and per task, plus totals, over the last `days` days."""
    from app.models import LLMCall

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.scalars(select(LLMCall).where(LLMCall.created_at >= since)).all()
    by_model = _group(rows, lambda r: r.model_used if r.ok else r.model_requested)
    by_task = _group(rows, lambda r: r.task)
    for g in by_task:
        g["label"] = g["name"]
    return {
        "days": days,
        "since": since,
        "totals": {
            "calls": len(rows),
            "errors": sum(1 for r in rows if not r.ok),
            "cost": round(sum(r.cost or 0 for r in rows if r.ok), 6),
            "tokens_in": sum(r.tokens_in for r in rows),
            "tokens_out": sum(r.tokens_out for r in rows),
        },
        "by_model": by_model,
        "by_task": by_task,
    }


def format_table(summary: dict) -> str:
    """Plain-text table for the CLI script."""
    head = f"{'model':<34}{'calls':>7}{'errors':>8}{'fallbk':>8}{'tok in':>10}{'tok out':>10}{'cost $':>11}{'$/call':>10}{'avg ms':>8}{'p95 ms':>8}"
    lines = [f"AI usage, last {summary['days']} days", "", head, "-" * len(head)]
    for g in summary["by_model"]:
        est = "*" if g["cost_estimated"] else " "
        lines.append(
            f"{g['label'][:33]:<34}{g['calls']:>7}{g['errors']:>8}{g['fallbacks']:>8}{g['tokens_in']:>10}"
            f"{g['tokens_out']:>10}{g['cost']:>10.4f}{est}{g['cost_per_call']:>10.5f}{g['avg_latency_ms']:>8}{g['p95_latency_ms']:>8}"
        )
    t = summary["totals"]
    lines += ["-" * len(head), f"{'total':<34}{t['calls']:>7}{t['errors']:>8}{'':>8}{t['tokens_in']:>10}{t['tokens_out']:>10}{t['cost']:>10.4f}"]
    lines += ["", "By task: " + ", ".join(f"{g['name']} {g['calls']} calls ${g['cost']:.4f}" for g in summary["by_task"])]
    if any(g["cost_estimated"] for g in summary["by_model"]):
        lines.append("* includes costs estimated from registry prices (OpenRouter didn't report them)")
    errors = {e for g in summary["by_model"] for e in g["error_types"]}
    if errors:
        lines.append("Error types: " + ", ".join(sorted(errors)))
    return "\n".join(lines)
