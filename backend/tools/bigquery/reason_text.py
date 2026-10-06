"""Plain-English readings of the detector's verdict reasons.

`reason` stays a stable slug: it is greppable, countable and asserted on
by tests. This adds a sentence alongside it, because most entries in
`evaluated` never become incidents and so never reach an agent — for
those, the reason is the only explanation there is.
"""

from typing import Optional


REASON_TEXT = {
    # No join to judge.
    "no_analyzable_joins": (
        "No join here that this check applies to. Array flattening and "
        "semi-joins are not joins in the sense that matters."
    ),
    # Ruled out before any evidence was needed.
    "all_sides_below_min_side_rows": (
        "Both tables are too small for a join problem to cost anything."
    ),
    "table_sizes_unknown": (
        "Table row counts could not be read, so the size check was skipped "
        "rather than used to rule the join out."
    ),
    "table_sizes_partially_unknown": (
        "Some table row counts could not be read, so the join was checked "
        "anyway rather than assumed small."
    ),
    "size_floor_cleared": (
        "At least one side is large enough to be worth checking."
    ),
    # Confirmed problems.
    "unconstrained_join_predicate": (
        "The join has no matching rule, or only a 'greater than' style one, "
        "so BigQuery has nothing to match rows on and pairs everything with "
        "everything."
    ),
    "classified_from_stage_metrics": (
        "BigQuery's record of how it ran the query shows a specific join "
        "problem."
    ),
    "join_key_expression_collapses_cardinality": (
        "The join key is built by a function that leaves very few possible "
        "values — EXTRACT(DAY FROM ...) can only ever be 1 to 31 — so each "
        "row probably matches a great many others."
    ),
    "fanout_estimated_from_key_cardinality": (
        "The column being joined on holds very few distinct values, so each "
        "row matches many others and the join multiplies the rows."
    ),
    # Ruled out on evidence.
    "declared_primary_key_on_every_join_key": (
        "Every join key is a declared primary key, so no value can appear "
        "twice and rows cannot multiply."
    ),
    "declared_primary_key_bounds_fanout": (
        "A declared primary key on the join key means values cannot repeat, "
        "so rows cannot multiply — even though the plan could not show it."
    ),
    "estimated_fanout_below_threshold": (
        "The join key's distinct values were counted: each row matches only "
        "a handful of others, so the join is fine."
    ),
    "join_stage_does_not_dominate_cost": (
        "The join used only a small share of the query's compute. The cost "
        "is in reading the tables, not in joining them, so this belongs to "
        "the partition-filter check instead."
    ),
    "no_join_pathology_in_stage_metrics": (
        "BigQuery's record of the run was read and showed nothing wrong "
        "with the join."
    ),
    # Could not tell — distinct from "nothing wrong".
    "cache_hit_no_execution_plan": (
        "BigQuery reused a saved result instead of running the query, so no "
        "work was done and there is no record of how it would have run."
    ),
    "fanout_unmeasurable_aggregate_fused": (
        "BigQuery folded the join and the grouping into one step, so its "
        "row counts show the grouped total rather than what the join "
        "produced. Whether the join multiplied rows cannot be read from it."
    ),
    "join_key_resolves_to_derived_table_and_no_stage_evidence": (
        "The join key comes from a subquery or WITH block rather than a "
        "table column, and no execution plan was available, so there is "
        "nothing to judge it on."
    ),
    "no_stage_evidence_available": (
        "No execution plan came back for this job, so the join could not be "
        "examined."
    ),
    "no_job_stages": (
        "No execution plan came back for this job, so the join could not be "
        "examined."
    ),
}


def explain(reason: Optional[str]) -> Optional[str]:
    """Return the plain-English reading of a verdict reason.

    An unmapped reason degrades to a readable form of the slug rather
    than disappearing, so a new branch is never silently unexplained.
    """

    if not reason:
        return None

    text = REASON_TEXT.get(reason)

    if text:
        return text

    return reason.replace("_", " ").capitalize() + "."
