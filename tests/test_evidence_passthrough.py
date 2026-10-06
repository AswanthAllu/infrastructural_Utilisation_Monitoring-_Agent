"""Evidence must survive every hop from detection to remediation.

partition_min/partition_max were added to the deterministic layer but
dropped by each agent's output template in turn, so remediation kept
anchoring date predicates to CURRENT_DATE() and proposing queries that
return no rows on historical data.
"""

import re
from pathlib import Path

import pytest

from tools.bigquery import query_review
from utils.join_parser import extract_joins


AGENTS = Path(__file__).resolve().parent.parent / "agents"

INCIDENT_OUTPUT = re.compile(
    r"^#+ .*(MISSING_PARTITION_FILTER|SLOT_CONTENTION|HIGH_CARDINALITY_JOIN)"
    r".*Output\s*$"
)


def instructions(agent: str) -> str:
    return (AGENTS / f"{agent}_agent" / "instructions.md").read_text(
        encoding="utf-8"
    )


def output_sections(agent: str) -> dict:
    """Split an agent's instructions into its per-incident output templates.

    Whole-file checks cannot catch a field that one incident type's
    template omits while the others carry it, which is how `job_id` was
    lost for HIGH_CARDINALITY_JOIN alone.
    """

    sections: dict = {}
    current = None

    for line in instructions(agent).splitlines():
        if line.startswith("#"):
            match = INCIDENT_OUTPUT.match(line)
            current = match.group(1) if match else None

            if current:
                sections.setdefault(current, [])

            continue

        if current:
            sections[current].append(line)

    return {name: "\n".join(body) for name, body in sections.items()}


def test_partition_range_survives_every_agent_template():
    for agent in ("detection", "diagnosis", "remediation"):
        text = instructions(agent)

        assert "partition_min" in text, f"{agent} drops partition_min"
        assert "partition_max" in text, f"{agent} drops partition_max"


@pytest.mark.parametrize(
    "agent,fields",
    [
        ("diagnosis", ("job_id", "table_name", "query")),
        # Remediation emits recommended_query rather than echoing the
        # original, so `query` is not expected in its templates.
        ("remediation", ("job_id", "table_name")),
    ],
)
def test_every_incident_output_template_carries_its_identity_fields(
    agent, fields
):
    """Each stage reads the previous stage's output, not the candidate.

    The HIGH_CARDINALITY_JOIN diagnosis template omitted job_id while
    MISSING_PARTITION_FILTER and SLOT_CONTENTION carried it, so
    remediation reported `job_id: null` — correctly, having been given
    none to copy. A whole-file assertion passes in that state.
    """

    sections = output_sections(agent)

    assert sections, f"{agent}: no incident output sections found"

    for incident, body in sections.items():
        for field in fields:
            assert f'"{field}"' in body, (
                f"{agent} / {incident} output template drops {field}"
            )


def test_downstream_agents_carry_the_minimum_not_allow_list_rule():
    """The rule existed only in detection, which is why it protected
    detection and nothing after it."""

    for agent in ("detection", "diagnosis", "remediation"):
        assert "minimum, not an allow-list" in instructions(agent), (
            f"{agent} has no passthrough rule"
        )


def test_detection_treats_templates_as_a_minimum_not_an_allow_list():
    """Three fields were lost this way in turn: partition range, severity,
    savings currency. The rule is general so the fourth is not."""

    text = instructions("detection")

    assert "minimum, not an allow-list" in text
    assert "severity" in text


def test_diagnosis_carries_detection_severity_through():
    text = instructions("diagnosis")

    assert "carry it through unchanged" in text


def test_unconstrained_join_sets_severity_and_currency_deterministically():
    from tools.bigquery.job_stages import analyze_join_stages
    from tools.bigquery.join_detection import detect_high_cardinality_join

    sql = (
        "SELECT 1 FROM `p.d.transactions` AS t CROSS JOIN `p.d.loans` AS l"
    )

    result = detect_high_cardinality_join(
        job={"job_id": "j"},
        joins=extract_joins(sql)["joins"],
        stages=analyze_join_stages(None),
    )

    assert result["failure_mode"] == "UNCONSTRAINED_JOIN"
    assert result["severity"] == "HIGH"
    assert result["savings_currency"] == "slot_ms"
    assert result["tables"] == ["p.d.loans", "p.d.transactions"]


def test_remediation_forbids_current_date_anchoring():
    text = instructions("remediation")

    assert "CURRENT_DATE()" in text
    assert "zero rows" in text


def test_review_surfaces_the_profiling_block():
    import inspect

    source = inspect.getsource(query_review.review_jobs)

    assert '"profiling"' in source


# A cartesian or range-only join still concerns real tables.


def test_cross_join_reports_its_tables():
    joins = extract_joins(
        "SELECT 1 FROM `p.d.transactions` AS a CROSS JOIN `p.d.loans` AS b"
    )["joins"]

    assert joins[0]["predicate_kind"] == "ABSENT"
    assert joins[0]["tables"] == ["p.d.loans", "p.d.transactions"]


def test_function_wrapped_key_join_reports_its_tables():
    """The real _6 case: keys wrapped in CAST/UPPER/TRIM.

    These are still a hashable equality, so the tables come from the key
    pair rather than from the cartesian fallback.
    """

    joins = extract_joins(
        "SELECT 1 FROM `p.d.transactions` AS t "
        "JOIN `p.d.loans` AS l "
        "ON CAST(UPPER(TRIM(t.customer_id)) AS STRING) "
        "= CAST(UPPER(TRIM(l.customer_id)) AS STRING)"
    )["joins"]

    assert joins[0]["predicate_kind"] == "EQUI_COMPUTED"
    assert joins[0]["tables"] == ["p.d.loans", "p.d.transactions"]


def test_range_join_reports_its_tables():
    joins = extract_joins(
        "SELECT 1 FROM `p.d.transactions` AS t JOIN `p.d.loans` AS l "
        "ON t.ts BETWEEN l.s AND l.e"
    )["joins"]

    assert joins[0]["predicate_kind"] == "RANGE"
    assert joins[0]["tables"] == ["p.d.loans", "p.d.transactions"]


def test_equi_join_tables_still_come_from_the_keys():
    joins = extract_joins(
        "SELECT 1 FROM `p.d.transactions` AS t JOIN `p.d.loans` AS l "
        "ON t.customer_id = l.customer_id"
    )["joins"]

    assert joins[0]["tables"] == ["p.d.loans", "p.d.transactions"]


def test_cte_join_does_not_invent_base_tables():
    """A CTE-only join has no base tables to name, and must not fabricate."""

    joins = extract_joins(
        "WITH c AS (SELECT k FROM `p.d.loans`) "
        "SELECT 1 FROM c AS a CROSS JOIN c AS b"
    )["joins"]

    assert joins[0]["tables"] == []


@pytest.mark.parametrize("agent", ["detection", "diagnosis"])
def test_unmeasured_fields_are_shown_as_null_not_zero(agent):
    """A 0 placeholder taught the agents to report 0 for "unknown".

    On a cache hit there is no execution plan, so join_dominance and the
    stage ratios have no value at all. Reporting 0 asserts the join used
    none of the query's compute, which is a measurement rather than the
    absence of one.
    """

    unmeasured = {
        "join_dominance",
        "max_skew_ratio",
        "max_fanout_ratio",
        "total_shuffle_bytes",
        "max_spilled_bytes",
        "total_slot_ms",
        "total_bytes_processed",
    }

    # Template lines only. The rule itself quotes `"join_dominance": 0` as
    # the thing not to do, and prose must not fail its own assertion.
    for line in instructions(agent).splitlines():
        match = re.match(r'^\s+"([a-z_]+)"\s*:\s*0\s*,?\s*$', line)

        if match and match.group(1) in unmeasured:
            raise AssertionError(
                f"{agent}: {match.group(1)} placeholder is 0, which reads "
                f"as measured rather than unknown"
            )

    assert "Never report `0` for an unknown value" in instructions(agent)


@pytest.mark.parametrize("agent", ["detection", "diagnosis", "remediation"])
def test_numeric_fields_are_not_typed_as_strings(agent):
    """The templates once wrote every number as "...", so the agents
    faithfully emitted strings: expected_future_runs came back "2.0"."""

    text = instructions(agent)

    for field in (
        "expected_future_runs",
        "total_slot_ms",
        "total_bytes_processed",
        "join_dominance",
    ):
        assert f'"{field}": "..."' not in text, (
            f"{agent}: {field} placeholder is a string"
        )


def test_join_detection_carries_the_job_cost():
    """MISSING_PARTITION_FILTER and SLOT_CONTENTION already report
    total_slot_ms. Without it on the join path the results table has no
    numeric column at all, so incidents cannot be ranked by cost."""

    import inspect

    from tools.bigquery import join_review

    source = inspect.getsource(join_review.review_jobs_for_joins)

    assert '"total_slot_ms"' in source

    for agent in ("detection", "diagnosis"):
        assert '"total_slot_ms"' in instructions(agent), (
            f"{agent} drops total_slot_ms"
        )


def test_every_unfiltered_table_reaches_the_incident():
    """The detector finds every table missing a partition filter, but the
    incident used to name only detected_tables[0].

    Consequences seen live: remediation filtered one side and left the
    other scanning whole, the named table flipped between runs on
    identical SQL, and the detection agent rewrote the query's FROM clause
    to agree with the single table it had been given.
    """

    import inspect

    from services import agent_service

    source = inspect.getsource(agent_service.run_support_agent)

    assert '"tables_missing_filter"' in source
    assert "detected_tables" in source

    for agent in ("detection", "diagnosis", "remediation"):
        assert "tables_missing_filter" in instructions(agent), (
            f"{agent} drops tables_missing_filter"
        )


def test_remediation_must_filter_every_listed_table():
    text = instructions("remediation")

    assert "every** table in it" in text or "every table in it" in text
    assert "partition_column" in text
