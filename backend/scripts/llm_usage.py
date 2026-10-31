"""Print AI usage and cost per model, to compare models.

    python -m scripts.llm_usage            # last 30 days
    python -m scripts.llm_usage --days 7

Reads the llm_calls table in DATABASE_URL (read-only). The same numbers are at
GET /admin/llm/usage and in the Admin page's AI models panel.
"""

import argparse

from app.db import SessionLocal
from app.llm.usage import format_table, summarize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    with SessionLocal() as db:
        print(format_table(summarize(db, args.days)))


if __name__ == "__main__":
    main()
