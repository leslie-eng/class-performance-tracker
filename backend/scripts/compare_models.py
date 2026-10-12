"""Run one prompt across the models in app/llm/registry.py and print a comparison table.

    python -m scripts.compare_models                       # sample prompt, every model
    python -m scripts.compare_models --structured          # grade a sample article as JSON (tests schema-following)
    python -m scripts.compare_models --models luna,gemini-flash --prompt "Explain recursion in 2 sentences"
    python -m scripts.compare_models --full                # print each full reply under the table

Needs OPENROUTER_API_KEY (from backend/.env or the environment). Each run costs a few cents at most.
Nothing is written to the database. Never put member data in --prompt: free models may log prompts, so
custom prompts only go to zero-data-retention models and free models are skipped for them.
"""

import argparse
import json
import sys
import time

from app import llm
from app.config import get_settings
from app.llm import registry
from app.services.grading import ARTICLE_SYSTEM, ArticleGrade

SAMPLE_PROMPT = (
    "Explain to a beginner, in at most four sentences, what a Python decorator is and when you'd use one. "
    "End with a one-line code example."
)

# Synthetic article for --structured: no real author or member data.
SAMPLE_ARTICLE = """<article url='https://example.com/decorators' title='Decorators without the magic'>
Decorators look like magic, but they're just functions that take a function and return a new one.
When you write @timer above def load(), Python runs load = timer(load). Inside timer I define wrapper(*args, **kwargs),
record time.perf_counter() before and after calling the original, print the difference and return the result.
One gotcha: without functools.wraps the wrapped function loses its __name__ and docstring, which confuses logging
and debuggers. I used this pattern to find the slow step in my CSV importer: parsing took 80% of the time.
</article>"""


def run_one(service: llm.LLMService, model_id: str, prompt: str | None, structured: bool) -> dict:
    private = registry.is_zdr(model_id)
    if structured:
        messages = [{"role": "system", "content": ARTICLE_SYSTEM}, {"role": "user", "content": SAMPLE_ARTICLE}]
    else:
        messages = [{"role": "user", "content": prompt or SAMPLE_PROMPT}]
    started = time.monotonic()
    try:
        result = service.generate(
            "grading" if structured else "feedback", messages, models=[model_id], sensitive=private,
            output=ArticleGrade if structured else None, max_tokens=1200,
        )
    except llm.LLMError as e:
        return {"model": model_id, "ok": False, "error": f"{type(e).__name__}: {e}",
                "latency_ms": int((time.monotonic() - started) * 1000)}
    cost, estimated = result.cost, False
    if cost is None and (m := registry.info(result.model_used)):
        cost, estimated = m.estimate_cost(result.tokens_in, result.tokens_out), True
    output = json.dumps(result.parsed.model_dump(), ensure_ascii=False) if structured else result.text
    return {
        "model": model_id, "ok": True, "model_used": result.model_used, "latency_ms": result.latency_ms,
        "tokens_in": result.tokens_in, "tokens_out": result.tokens_out, "cost": cost, "cost_estimated": estimated,
        "output": output.strip(),
    }


def table(rows: list[dict], width: int) -> str:
    head = f"{'model':<26}{'ok':<5}{'latency':>9}{'tok in':>8}{'tok out':>8}{'cost $':>11}  output"
    lines = [head, "-" * (len(head) + width)]
    for r in rows:
        label = (registry.info(r["model"]).label if registry.info(r["model"]) else r["model"])[:25]
        if not r["ok"]:
            lines.append(f"{label:<26}{'no':<5}{r['latency_ms'] / 1000:>8.1f}s{'':>8}{'':>8}{'':>11}  {r['error'][:width]}")
            continue
        cost = "?" if r["cost"] is None else f"{r['cost']:.5f}{'*' if r['cost_estimated'] else ''}"
        snippet = " ".join(r["output"].split())[:width]
        lines.append(f"{label:<26}{'yes':<5}{r['latency_ms'] / 1000:>8.1f}s{r['tokens_in']:>8}{r['tokens_out']:>8}{cost:>11}  {snippet}")
    if any(r.get("cost_estimated") for r in rows):
        lines.append("* estimated from registry prices (OpenRouter didn't report the cost)")
    return "\n".join(lines)


def main(argv: list[str] | None = None, service: llm.LLMService | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", help="comma-separated friendly names or OpenRouter ids (default: the whole registry)")
    parser.add_argument("--prompt", help="your own prompt (never member data); only sent to zero-retention models")
    parser.add_argument("--structured", action="store_true", help="grade a sample article as JSON with the real rubric")
    parser.add_argument("--full", action="store_true", help="print each full reply after the table")
    parser.add_argument("--width", type=int, default=70, help="output characters shown per row")
    args = parser.parse_args(argv)

    if not get_settings().openrouter_api_key:
        print("OPENROUTER_API_KEY isn't set (backend/.env or the environment).", file=sys.stderr)
        return 2
    try:
        names = [n for n in (args.models or ",".join(registry.MODELS)).split(",") if n.strip()]
        model_ids = [registry.resolve(n) for n in names]
    except registry.UnknownModel as e:
        print(e, file=sys.stderr)
        return 2
    if args.prompt and args.structured:
        print("--prompt and --structured can't be combined.", file=sys.stderr)
        return 2

    # No usage rows: this is a comparison run, and DATABASE_URL may point at production.
    service = service or llm.LLMService(recorder=lambda record: None)
    rows, skipped = [], []
    for model_id in model_ids:
        if args.prompt and not registry.is_zdr(model_id):
            skipped.append(model_id)
            continue
        print(f"… {model_id}", file=sys.stderr)
        rows.append(run_one(service, model_id, args.prompt, args.structured))

    mode = "sample article graded as JSON" if args.structured else ("your prompt" if args.prompt else "sample prompt")
    print(f"\nComparison: {mode}\n")
    print(table(rows, args.width))
    if skipped:
        print(f"\nSkipped (no zero-retention provider, so no custom prompts): {', '.join(skipped)}")
    if args.full:
        for r in rows:
            print(f"\n=== {r['model']} ===\n{r['output'] if r['ok'] else r['error']}")
    return 0 if any(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
