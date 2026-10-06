import json
import logging
from typing import Any, Dict, List, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.orchestrator_agent.agent import orchestrator_agent
from tools.bigquery.query_review import review_jobs
from tools.bigquery.results_writer import store_result


APP_NAME = "bigquery_support_agent"
USER_ID = "api_user"


logger = logging.getLogger(__name__)

session_service = InMemorySessionService()


def _safe_parse_agent_response(raw: Any) -> Dict[str, Any]:
    """Convert an agent response into a dictionary."""

    if isinstance(raw, dict):
        return raw

    if raw is None:
        return {}

    text = str(raw).strip()

    if not text:
        return {}

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            return parsed

    except json.JSONDecodeError:
        # Models occasionally emit literal unescaped control characters
        # (e.g. a raw newline) inside a JSON string value, which strict
        # json.loads rejects even though the structure is otherwise valid.
        try:
            parsed = json.loads(text, strict=False)

            if isinstance(parsed, dict):
                return parsed

        except json.JSONDecodeError:
            pass

    return {
        "summary": text,
    }


def _extract_event_text(event: Any) -> Optional[str]:
    """Extract text from an ADK event."""

    if not event.content:
        return None

    if not event.content.parts:
        return None

    texts = []

    for part in event.content.parts:
        if getattr(part, "text", None):
            texts.append(part.text)

    if not texts:
        return None

    return "\n".join(texts).strip()


# Facts the detectors established before any agent saw them. An agent is
# meant to copy these verbatim.
DRIFT_CHECKED_FIELDS = ("job_id", "incident_type", "table_name", "query")


def _comparable(value: Any) -> str:
    """Normalise line endings and trailing spaces before comparing.

    INFORMATION_SCHEMA returns CRLF in query text and the agents emit LF,
    which is not drift. Anything else that differs is a content change.
    """

    text = str(value).replace("\r\n", "\n").replace("\r", "\n")

    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def _agent_drift(
    workflow: Dict[str, Any],
    candidate: Dict[str, Any],
) -> List[str]:
    """Fields an agent returned altered from the values it was given.

    Recorded, never acted on. The finding itself is deterministic and
    stands; what drift puts in doubt is the prose written around it. An
    agent that rewrote the query was describing SQL the job never ran, so
    its root cause and recommended query concern a query that does not
    exist.
    """

    drift: List[str] = []

    for stage in ("detection", "diagnosis", "remediation"):
        block = workflow.get(stage)

        if not isinstance(block, dict):
            continue

        for field in DRIFT_CHECKED_FIELDS:
            supplied = candidate.get(field)
            returned = block.get(field)

            if supplied is None or returned is None:
                continue

            if _comparable(returned) != _comparable(supplied):
                drift.append(f"{stage}.{field}")

    return drift


async def _run_workflow(
    candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """Run the ADK Workflow for one detected candidate."""

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
    )

    prompt = (
        "Process this BigQuery incident candidate through the workflow. "
        "The workflow stages must execute in order: "
        "Detection, Diagnosis, Remediation. "
        "Use only the evidence provided. "
        "Do not invent missing evidence. "
        "\n\nCandidate:\n"
        f"{json.dumps(candidate, default=str)}"
    )

    user_message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(text=prompt)
        ],
    )

    runner = Runner(
        agent=orchestrator_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    stage_outputs: Dict[str, Dict[str, Any]] = {}

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=user_message,
    ):
        event_text = _extract_event_text(event)

        if not event_text:
            continue

        author = getattr(event, "author", None)

        if author == "detection_agent":
            stage_outputs["detection"] = _safe_parse_agent_response(
                event_text
            )

        elif author == "diagnosis_agent":
            stage_outputs["diagnosis"] = _safe_parse_agent_response(
                event_text
            )

        elif author == "remediation_agent":
            stage_outputs["remediation"] = _safe_parse_agent_response(
                event_text
            )

    return stage_outputs


async def run_support_agent(
    region: str = "US",
    lookback_hours: int = 24,
    jobs_limit: int = 5,
) -> Dict[str, Any]:
    """
    Review recent BigQuery jobs and run the ADK Workflow
    for every detected candidate.
    """

    review_result = review_jobs(
        region=region,
        lookback_hours=lookback_hours,
        jobs_limit=jobs_limit,
    )

    if not review_result.get("success"):
        return {
            "success": False,
            "region": region,
            "lookback_hours": lookback_hours,
            "jobs_checked": 0,
            "candidate_count": 0,
            "incidents": [],
            "message": review_result.get("message"),
        }

    missing_partition_candidates = (
        review_result.get(
            "missing_partition_filter_candidates",
            [],
        )
    )

    slot_contention_candidates = (
        review_result.get(
            "slot_contention_candidates",
            [],
        )
    )

    high_cardinality_join_candidates = (
        review_result.get(
            "high_cardinality_join_candidates",
            [],
        )
    )

    candidate_entries = (
        missing_partition_candidates
        + slot_contention_candidates
        + high_cardinality_join_candidates
    )

    incidents: List[Dict[str, Any]] = []

    for candidate_entry in candidate_entries:

        analysis = candidate_entry.get("analysis") or {}
        job = candidate_entry.get("job") or {}

        candidate = dict(analysis)

        candidate["job_id"] = (
            candidate.get("job_id")
            or job.get("job_id")
        )

        candidate["incident_type"] = (
            candidate.get("incident_type")
        )

        candidate["query"] = (
            candidate.get("query")
            or job.get("query")
        )

        # Missing Partition Filter has table information.
        # Slot Contention does not need a table name.
        # High Cardinality Join concerns a pair of tables and carries
        # them on `tables`.
        detected_tables = candidate.get(
            "detected_tables"
        ) or []

        if detected_tables:
            candidate["table_name"] = (
                detected_tables[0].get("table_name")
            )

            # One query can leave several partitioned tables unfiltered.
            # The detector finds all of them; reporting only the first
            # dropped the rest, so remediation filtered one side and left
            # the other scanning whole. It also meant the incident named
            # whichever table BigQuery happened to list first, which
            # changed between runs on identical SQL.
            candidate["tables_missing_filter"] = [
                {
                    "table_name": entry.get("table_name"),
                    "partition_column": (entry.get("evidence") or {}).get(
                        "partition_column"
                    ),
                    "partition_min": (entry.get("evidence") or {}).get(
                        "partition_min"
                    ),
                    "partition_max": (entry.get("evidence") or {}).get(
                        "partition_max"
                    ),
                }
                for entry in detected_tables
            ]

        elif candidate.get("table_results"):
            candidate["table_name"] = (
                candidate["table_results"][0].get(
                    "table_name"
                )
            )

        elif candidate.get("tables"):
            # primary_table is the table the query reads first. `tables`
            # is sorted, so its head routinely named a table the SQL did
            # not start FROM, and an agent given that contradiction has
            # rewritten the query's FROM clause to resolve it.
            candidate["table_name"] = (
                candidate.get("primary_table")
                or candidate["tables"][0]
            )

        else:
            candidate["table_name"] = None

        workflow_result = await _run_workflow(candidate)

        # Carried inside the workflow result so it reaches the raw
        # archive with everything else, needing no schema change.
        drift = _agent_drift(workflow_result, candidate)
        workflow_result["agent_drift"] = drift

        storage_result = store_result(
            issue_reference=candidate.get("job_id"),
            agent_response=workflow_result,
        )

        if not storage_result.get("success"):
            logger.error(
                "Failed to store incident result for job_id=%s: %s",
                candidate.get("job_id"),
                storage_result,
            )

        incidents.append(
            {
                "job_id": candidate.get("job_id"),
                "incident_type": candidate.get(
                    "incident_type"
                ),
                "table_name": candidate.get(
                    "table_name"
                ),
                "agent_drift": drift,
                "detection": workflow_result.get(
                    "detection"
                ),
                "diagnosis": workflow_result.get(
                    "diagnosis"
                ),
                "remediation": workflow_result.get(
                    "remediation"
                ),
                "storage": storage_result,
            }
        )

    return {
        "success": True,
        "region": region,
        "lookback_hours": lookback_hours,
        "jobs_checked": review_result.get(
            "jobs_checked",
            0,
        ),
        "candidate_count": len(incidents),
        "detector_counts": {
            "missing_partition_filter": len(
                missing_partition_candidates
            ),
            "slot_contention": len(
                slot_contention_candidates
            ),
            "high_cardinality_join": len(
                high_cardinality_join_candidates
            ),
        },
        # Why the join detector found nothing is otherwise invisible from
        # the API: the active scale profile and the per-job verdicts are
        # what distinguish "no incidents" from "every candidate gated".
        "join_review": review_result.get("join_review"),
        "incidents": incidents,
    }