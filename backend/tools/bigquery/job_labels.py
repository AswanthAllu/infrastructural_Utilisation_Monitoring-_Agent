"""Labels that mark a job as the review's own, so it can exclude it.

The review runs real queries against real tables: column profiling, PK
lookups, recurrence history. Those land in INFORMATION_SCHEMA.JOBS like
any other job, and the profiler's `SELECT COUNT(*), APPROX_COUNT_DISTINCT(k)
FROM t` legitimately has no partition filter — so the next review flags
it as an incident. Left alone this compounds: every run generates the
findings for the run after it.
"""

from typing import Any, Dict, Optional

from google.cloud import bigquery


AGENT_LABEL_KEY = "dbops_agent"
AGENT_LABEL_VALUE = "review"

AGENT_LABELS: Dict[str, str] = {AGENT_LABEL_KEY: AGENT_LABEL_VALUE}


# Excludes any job carrying the label. Applied to the review's job sweep
# so the detectors never analyse the review's own work.
EXCLUDE_AGENT_JOBS_SQL = f"""
    NOT EXISTS (
      SELECT 1 FROM UNNEST(labels) AS label
      WHERE label.key = '{AGENT_LABEL_KEY}'
        AND label.value = '{AGENT_LABEL_VALUE}'
    )
"""


def agent_job_config(**kwargs: Any) -> bigquery.QueryJobConfig:
    """A QueryJobConfig labelled as the review's own."""

    return bigquery.QueryJobConfig(labels=AGENT_LABELS, **kwargs)


def label_config(
    config: Optional[bigquery.QueryJobConfig] = None,
) -> bigquery.QueryJobConfig:
    """Attach the agent label to an existing config, or make a new one."""

    if config is None:
        return agent_job_config()

    config.labels = AGENT_LABELS

    return config
