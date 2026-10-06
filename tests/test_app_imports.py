"""Smoke test that the application actually loads.

The other suites exercise the detection tools directly and never import
the agents package or the FastAPI app, so a broken agent wiring — or a
merge left half-resolved — passes them all. This catches that.
"""


def test_main_app_imports():
    import main

    assert main.app is not None


def test_orchestrator_workflow_builds():
    from agents.orchestrator_agent.agent import orchestrator_agent

    assert orchestrator_agent is not None


def test_every_agent_instruction_file_is_present():
    from agents.detection_agent.agent import detection_agent
    from agents.diagnosis_agent.agent import diagnosis_agent
    from agents.remediation_agent.agent import remediation_agent

    for agent in (detection_agent, diagnosis_agent, remediation_agent):
        assert agent.instruction


def test_review_exposes_all_three_detectors():
    from tools.bigquery import query_review

    source = query_review.review_jobs.__doc__ or ""

    assert "Missing Partition Filter" in source
    assert "Slot Contention" in source
    assert "High Cardinality Join" in source
