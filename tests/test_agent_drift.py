"""An agent that rewrites the query is describing SQL the job never ran.

N5's real SQL reads `FROM transactions CROSS JOIN loan_applications`. One
run reported both sides as `loan_applications`, leaving a predicate on a
column that table does not have. The invalid query reached the results
table looking exactly like a good row.
"""

from services.agent_service import _agent_drift, _comparable


REAL_SQL = (
    "SELECT COUNT(*) AS pair_count\r\n"
    "FROM `p.d.transactions` AS t\r\n"
    "CROSS JOIN `p.d.loan_applications` AS l"
)


def candidate():
    return {
        "job_id": "j1",
        "incident_type": "HIGH_CARDINALITY_JOIN",
        "table_name": "p.d.transactions",
        "query": REAL_SQL,
    }


def test_faithful_agents_report_no_drift():
    workflow = {
        "detection": dict(candidate()),
        "diagnosis": dict(candidate()),
    }

    assert _agent_drift(workflow, candidate()) == []


def test_line_endings_alone_are_not_drift():
    """INFORMATION_SCHEMA returns CRLF; the agents emit LF."""

    echoed = dict(candidate())
    echoed["query"] = REAL_SQL.replace("\r\n", "\n") + "\n"

    assert _agent_drift({"detection": echoed}, candidate()) == []


def test_a_rewritten_from_clause_is_drift():
    rewritten = dict(candidate())
    rewritten["query"] = REAL_SQL.replace("transactions", "loan_applications")

    assert _agent_drift({"detection": rewritten}, candidate()) == [
        "detection.query"
    ]


def test_drift_is_reported_per_stage_and_field():
    workflow = {
        "detection": {**candidate(), "query": "SELECT 1"},
        "diagnosis": {**candidate(), "table_name": "p.d.somewhere_else"},
    }

    assert _agent_drift(workflow, candidate()) == [
        "detection.query",
        "diagnosis.table_name",
    ]


def test_a_field_the_agent_omitted_is_not_drift():
    """Omission is the passthrough rule's problem, not this check's."""

    assert _agent_drift({"detection": {"job_id": "j1"}}, candidate()) == []


def test_comparable_keeps_real_differences():
    assert _comparable("SELECT 1") != _comparable("SELECT 2")
