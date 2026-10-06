"""The flattened row must distinguish findings the columns alone cannot.

No new columns: the failure mode qualifies incident_type, and the
detector's own verdict rides inside incident_evidence.
"""

import json

from tools.bigquery.results_writer import _flatten_agent_response


def payload(**detection):
    base = {
        "incident_type": "HIGH_CARDINALITY_JOIN",
        "job_id": "j1",
        "status": "DETECTED",
        "evidence": {"evidence_tier": 0, "total_slot_ms": 12345},
    }
    base.update(detection)

    return {"detection": base, "diagnosis": {}, "remediation": {}}


def evidence_of(row):
    return json.loads(row["incident_evidence"])


def test_failure_mode_qualifies_the_incident_type():
    row = _flatten_agent_response("j1", payload(failure_mode="KEY_SKEW"))

    assert row["incident_type"] == "HIGH_CARDINALITY_JOIN.KEY_SKEW"


def test_detectors_without_a_failure_mode_are_unchanged():
    row = _flatten_agent_response(
        "j1",
        {"detection": {"incident_type": "MISSING_PARTITION_FILTER"}},
    )

    assert row["incident_type"] == "MISSING_PARTITION_FILTER"


def test_evidence_strength_records_measured_versus_inferred():
    """diagnosis_status says CONFIRMED for a PROBABLE finding, so without
    this a tier-0 inference reads as a measurement."""

    row = _flatten_agent_response(
        "j1", payload(failure_mode="FAN_OUT", confidence_state="PROBABLE")
    )

    assert evidence_of(row)["evidence_strength"] == "PROBABLE"


def test_evidence_strength_does_not_displace_the_rest_of_the_evidence():
    row = _flatten_agent_response(
        "j1", payload(confidence_state="CONFIRMED")
    )

    assert evidence_of(row)["total_slot_ms"] == 12345
    assert evidence_of(row)["evidence_tier"] == 0


def test_total_slot_ms_reaches_the_row_for_every_incident_type():
    """The only numeric in the record, so the only way to rank findings."""

    row = _flatten_agent_response("j1", payload(failure_mode="FAN_OUT"))

    assert evidence_of(row)["total_slot_ms"] == 12345


def test_a_verdict_with_no_evidence_block_still_records_its_strength():
    row = _flatten_agent_response(
        "j1",
        {"detection": {"incident_type": "X", "confidence_state": "PROBABLE",
                       "evidence": None}},
    )

    assert evidence_of(row) == {"evidence_strength": "PROBABLE"}


def test_nothing_to_record_stays_null():
    row = _flatten_agent_response("j1", {"detection": {"incident_type": "X"}})

    assert row["incident_evidence"] is None
