from typing import Any, Dict, Iterable, Optional, Set, Tuple

from google.cloud import bigquery

from .job_labels import agent_job_config


_cache: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}


def _datasets(table_names: Iterable[str]) -> Set[Tuple[str, str]]:
    """Reduce dotted table names to the distinct (project, dataset) pairs."""

    out = set()

    for name in table_names:
        parts = name.split(".")

        if len(parts) == 3:
            out.add((parts[0], parts[1]))

    return out


def _fetch_dataset_primary_keys(
    project: str,
    dataset: str,
    client: bigquery.Client,
) -> Set[Tuple[str, str]]:
    """Read single-column primary keys declared in one dataset.

    Composite keys are excluded: uniqueness of a two-column key says
    nothing about either column alone, so it cannot bound fan-out on a
    join that uses only one of them.
    """

    sql = f"""
        SELECT
          kcu.table_name,
          kcu.column_name,
          COUNT(*) OVER (PARTITION BY kcu.constraint_name) AS key_columns
        FROM `{project}.{dataset}`.INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
        JOIN `{project}.{dataset}`.INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
    """

    rows = client.query(sql, job_config=agent_job_config()).result()

    return {
        (f"{project}.{dataset}.{row['table_name']}", row["column_name"])
        for row in rows
        if row["key_columns"] == 1
    }


def get_primary_key_columns(
    table_names: Iterable[str],
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """Look up declared single-column primary keys for the given tables.

    BigQuery primary keys are unenforced, so a hit lowers confidence in a
    fan-out finding rather than proving one impossible. A dataset whose
    constraint views cannot be read yields no keys and no error: the
    check simply loses its free short-circuit there.
    """

    table_names = list(table_names)

    if not table_names:
        return {"success": True, "primary_keys": set(), "datasets_read": 0}

    client = bigquery.Client(project=project) if project else bigquery.Client()

    primary_keys: Set[Tuple[str, str]] = set()
    failures = []
    datasets_read = 0

    for project_id, dataset_id in _datasets(table_names):
        key = (project_id, dataset_id)

        if key in _cache:
            primary_keys |= _cache[key]
            datasets_read += 1
            continue

        try:
            found = _fetch_dataset_primary_keys(project_id, dataset_id, client)
            _cache[key] = found
            primary_keys |= found
            datasets_read += 1

        except Exception as exc:
            failures.append(f"{project_id}.{dataset_id}: {exc}")

    wanted = set(table_names)

    return {
        "success": True,
        "primary_keys": {
            (table, column)
            for table, column in primary_keys
            if table in wanted
        },
        "datasets_read": datasets_read,
        "failures": failures,
    }


def clear_cache() -> None:
    """Drop cached constraint lookups."""

    _cache.clear()
