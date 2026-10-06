"""Pins the existing MISSING_PARTITION_FILTER behaviour.

The high-cardinality join check is built on top of this path and shares
table metadata and job review with it. These tests exist so that any
change to the shared code which alters partition detection fails here.
"""

import pytest

from tools.bigquery import partition_detection
from tools.bigquery.partition_detection import detect_missing_partition_filter
from utils.sql_parser import has_partition_filter


PARTITIONED = {
    "success": True,
    "table": "p:d.events",
    "table_type": "TABLE",
    "is_partitioned": True,
    "partition_column": "event_date",
    "partition_type": "DAY",
    "partition_expiration_ms": None,
    "require_partition_filter": False,
}


@pytest.fixture
def metadata(monkeypatch):
    """Replace the BigQuery metadata lookup with a fixed response."""

    def _set(response):
        monkeypatch.setattr(
            partition_detection,
            "get_table_partition_info",
            lambda table_name: response,
        )

    return _set


# utils/sql_parser.py — the supported predicate set.


@pytest.mark.parametrize(
    "where",
    [
        "event_date = '2026-01-01'",
        "event_date > '2026-01-01'",
        "event_date >= '2026-01-01'",
        "event_date < '2026-01-01'",
        "event_date <= '2026-01-01'",
        "event_date BETWEEN '2026-01-01' AND '2026-01-02'",
        "event_date IN ('2026-01-01')",
    ],
)
def test_usable_partition_predicates(where):
    sql = f"SELECT 1 FROM `p.d.events` WHERE {where}"

    assert has_partition_filter(sql, "event_date") is True


def test_is_not_null_is_not_a_partition_filter():
    sql = "SELECT 1 FROM `p.d.events` WHERE event_date IS NOT NULL"

    assert has_partition_filter(sql, "event_date") is False


def test_filter_on_another_column_does_not_count():
    sql = "SELECT 1 FROM `p.d.events` WHERE user_id = 7"

    assert has_partition_filter(sql, "event_date") is False


def test_no_where_clause():
    assert has_partition_filter("SELECT 1 FROM `p.d.events`", "event_date") is False


def test_partition_column_match_is_case_insensitive():
    sql = "SELECT 1 FROM `p.d.events` WHERE EVENT_DATE = '2026-01-01'"

    assert has_partition_filter(sql, "event_date") is True


def test_unparseable_sql_returns_false():
    assert has_partition_filter("SELECT FROM WHERE )(", "event_date") is False


# tools/bigquery/partition_detection.py — the four outcomes.


def test_missing_filter_is_detected(metadata):
    metadata(PARTITIONED)

    result = detect_missing_partition_filter(
        table_name="p.d.events",
        sql="SELECT 1 FROM `p.d.events`",
    )

    assert result["detected"] is True
    assert result["status"] == "DETECTED"
    assert result["incident_type"] == "MISSING_PARTITION_FILTER"
    assert result["sql_has_partition_filter"] is False
    assert "event_date" in result["reason"]


def test_present_filter_is_not_detected(metadata):
    metadata(PARTITIONED)

    result = detect_missing_partition_filter(
        table_name="p.d.events",
        sql="SELECT 1 FROM `p.d.events` WHERE event_date = '2026-01-01'",
    )

    assert result["detected"] is False
    assert result["status"] == "NOT_DETECTED"
    assert result["sql_has_partition_filter"] is True


def test_unpartitioned_table_is_not_applicable(metadata):
    metadata({**PARTITIONED, "is_partitioned": False, "partition_column": None})

    result = detect_missing_partition_filter(
        table_name="p.d.events",
        sql="SELECT 1 FROM `p.d.events`",
    )

    assert result["detected"] is False
    assert result["status"] == "NOT_APPLICABLE"


def test_metadata_failure_is_reported_as_failed(metadata):
    metadata({"success": False, "error": "TABLE_NOT_FOUND", "message": "nope"})

    result = detect_missing_partition_filter(
        table_name="p.d.missing",
        sql="SELECT 1 FROM `p.d.missing`",
    )

    assert result["detected"] is False
    assert result["status"] == "FAILED"
    assert result["reason"] == "nope"


def test_partitioned_without_column_is_failed(metadata):
    metadata({**PARTITIONED, "partition_column": None})

    result = detect_missing_partition_filter(
        table_name="p.d.events",
        sql="SELECT 1 FROM `p.d.events`",
    )

    assert result["status"] == "FAILED"


def test_metadata_is_passed_through_unchanged(metadata):
    metadata(PARTITIONED)

    result = detect_missing_partition_filter(
        table_name="p.d.events",
        sql="SELECT 1 FROM `p.d.events`",
    )

    assert result["metadata"] == PARTITIONED
