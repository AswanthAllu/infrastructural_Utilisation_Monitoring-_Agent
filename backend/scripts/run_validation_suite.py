"""Submit the validation suite as individual jobs with caching disabled.

Running the suite as one console script has two problems the detectors
cannot see past: script child statements kept returning cache_hit despite
the console setting, so no execution plan ever existed to analyse; and
they execute sequentially, so slot contention can never fire.

Each statement here becomes its own top-level job with
use_query_cache=False, which guarantees a plan and lets jobs overlap.

    python scripts/run_validation_suite.py --dry-run
    python scripts/run_validation_suite.py
"""

import argparse
import sys
from pathlib import Path
from typing import List

from google.cloud import bigquery


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQL = Path(__file__).resolve().parent / "validation_suite.sql"

sys.path.insert(0, str(ROOT))


def _is_only_comments(fragment: str) -> bool:
    """Whether a fragment holds nothing but comments and whitespace."""

    for line in fragment.splitlines():
        stripped = line.strip()

        if stripped and not stripped.startswith("--"):
            return False

    return True


def split_statements(text: str) -> List[str]:
    """Split multi-statement SQL on top-level semicolons.

    String literals, backtick-quoted identifiers and line comments are
    tracked so a semicolon inside any of them does not end a statement.
    """

    statements: List[str] = []
    current: List[str] = []
    quote = ""
    index = 0

    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""

        if quote:
            current.append(char)

            if char == "\\" and following:
                current.append(following)
                index += 2
                continue

            if char == quote:
                quote = ""

            index += 1
            continue

        if char in ("'", '"', "`"):
            quote = char
            current.append(char)
            index += 1
            continue

        if char == "-" and following == "-":
            end = text.find("\n", index)
            end = len(text) if end == -1 else end
            current.append(text[index:end])
            index = end
            continue

        if char == ";":
            statements.append("".join(current))
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    statements.append("".join(current))

    return [s.strip() for s in statements if not _is_only_comments(s)]


def label_of(statement: str) -> str:
    """Use the statement's leading comment as its label, if it has one."""

    for line in statement.splitlines():
        stripped = line.strip()

        if stripped.startswith("--"):
            return stripped.lstrip("- ").strip()[:52]

        if stripped:
            break

    return " ".join(statement.split())[:52]


def estimate(client: bigquery.Client, sql: str):
    """Dry-run one statement to price it before executing."""

    config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)

    try:
        job = client.query(sql, job_config=config)
        return job.total_bytes_processed, None
    except Exception as exc:
        return None, str(exc)


def execute(client: bigquery.Client, sql: str):
    """Run one statement as its own job, bypassing the result cache."""

    config = bigquery.QueryJobConfig(use_query_cache=False)

    job = client.query(sql, job_config=config)
    job.result()

    return job


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql", type=Path, default=DEFAULT_SQL)
    parser.add_argument("--project", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="estimate bytes for every statement and stop",
    )
    args = parser.parse_args()

    statements = split_statements(args.sql.read_text(encoding="utf-8"))

    print(f"{len(statements)} statements parsed from {args.sql.name}\n")

    client = (
        bigquery.Client(project=args.project) if args.project else bigquery.Client()
    )

    total_bytes = 0

    print(f"{'#':>3}  {'estimated':>12}  statement")
    print("-" * 74)

    for number, sql in enumerate(statements, start=1):
        size, error = estimate(client, sql)

        if error:
            print(f"{number:>3}  {'DRY RUN FAILED':>12}  {label_of(sql)}")
            print(f"     {error.splitlines()[0][:66]}")
            continue

        total_bytes += size or 0
        print(f"{number:>3}  {(size or 0)/1024/1024:>9.1f} MB  {label_of(sql)}")

    print(f"\ntotal estimated: {total_bytes/1024/1024:.1f} MB")

    if args.dry_run:
        print("\ndry run only, nothing executed")
        return 0

    print(f"\n{'#':>3}  {'cache':>6}  {'slot_ms':>9}  {'stages':>6}  job_id")
    print("-" * 78)

    cached = 0
    planned = 0
    failed = 0

    for number, sql in enumerate(statements, start=1):
        try:
            job = execute(client, sql)
        except Exception as exc:
            failed += 1
            print(f"{number:>3}  {'FAILED':>6}  {exc.__class__.__name__}")
            print(f"     {str(exc).splitlines()[0][:70]}")
            continue

        stages = len(job.query_plan or [])
        cached += 1 if job.cache_hit else 0
        planned += 1 if stages else 0

        print(
            f"{number:>3}  {str(bool(job.cache_hit)):>6}  "
            f"{str(job.slot_millis):>9}  {stages:>6}  {job.job_id}"
        )

    print(
        f"\n{len(statements)} submitted  |  {planned} with an execution plan  |  "
        f"{cached} cache hits  |  {failed} failed"
    )

    if cached:
        print(
            "\nCache hits should be zero here. If not, use_query_cache is being "
            "overridden somewhere."
        )

    print("\nNow call GET /api/review to analyse these jobs.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
