"""The review must not analyse its own queries.

Column profiling reads real tables with no partition filter, by design.
Those jobs land in INFORMATION_SCHEMA.JOBS and were being reported as
MISSING_PARTITION_FILTER incidents on the following run, so each review
manufactured the findings for the next one.
"""

import inspect

from tools.bigquery import (
    column_profile,
    job_labels,
    job_stages,
    jobs_metadata,
    query_recurrence,
    table_constraints,
    table_metadata,
)


LABELLED_MODULES = [
    column_profile,
    job_stages,
    jobs_metadata,
    query_recurrence,
    table_constraints,
    table_metadata,
]


def test_label_is_valid_for_bigquery():
    """Keys and values must be lowercase alphanumeric, dash or underscore."""

    for key, value in job_labels.AGENT_LABELS.items():
        assert key == key.lower()
        assert value == value.lower()
        assert key.replace("_", "").replace("-", "").isalnum()
        assert value.replace("_", "").replace("-", "").isalnum()


def test_every_module_that_queries_applies_the_label():
    for module in LABELLED_MODULES:
        source = inspect.getsource(module)

        assert (
            "agent_job_config" in source or "label_config" in source
        ), f"{module.__name__} submits queries without the agent label"


def test_no_unlabelled_client_query_calls_remain():
    """A bare client.query(sql) has no label and would be self-detected."""

    for module in LABELLED_MODULES:
        for line in inspect.getsource(module).splitlines():
            stripped = line.strip()

            if ".query(sql)" in stripped or ".query(sql).result()" in stripped:
                raise AssertionError(
                    f"{module.__name__}: unlabelled query -> {stripped}"
                )


def test_sweep_excludes_labelled_jobs():
    source = inspect.getsource(jobs_metadata.get_recent_query_jobs)

    assert "EXCLUDE_AGENT_JOBS_SQL" in source


def test_exclusion_sql_matches_the_label_it_sets():
    assert job_labels.AGENT_LABEL_KEY in job_labels.EXCLUDE_AGENT_JOBS_SQL
    assert job_labels.AGENT_LABEL_VALUE in job_labels.EXCLUDE_AGENT_JOBS_SQL
    assert "NOT EXISTS" in job_labels.EXCLUDE_AGENT_JOBS_SQL


def test_label_config_preserves_existing_settings():
    from google.cloud import bigquery

    config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    labelled = job_labels.label_config(config)

    assert labelled.dry_run is True
    assert labelled.use_query_cache is False
    assert labelled.labels == job_labels.AGENT_LABELS


def test_agent_job_config_accepts_keyword_settings():
    config = job_labels.agent_job_config(dry_run=True, use_query_cache=False)

    assert config.dry_run is True
    assert config.labels == job_labels.AGENT_LABELS
