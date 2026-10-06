from typing import Any, Dict, List, Optional, Set, Tuple

from config import join_thresholds as T


FAILURE_MODES = (
    "KEY_SKEW",
    "FAN_OUT",
    "SHUFFLE_VOLUME",
    "UNCONSTRAINED_JOIN",
)


def _outcome(
    confidence: str,
    reason: str,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a detection outcome with a stable shape."""

    result = {
        "incident_type": "HIGH_CARDINALITY_JOIN",
        "detected": confidence in ("CONFIRMED", "PROBABLE"),
        "confidence_state": confidence,
        "failure_mode": None,
        "severity": "MEDIUM",
        "reason": reason,
        "routed": False,
        "evidence_tier": 0,
    }

    result.update(extra)

    return result


def _side_rows(
    join: Dict[str, Any],
    table_rows: Dict[str, Optional[int]],
) -> List[Optional[int]]:
    """Row counts for the tables a join touches, None where unknown."""

    return [table_rows.get(table) for table in join.get("tables") or []]


def _clears_size_floor(
    joins: List[Dict[str, Any]],
    table_rows: Dict[str, Optional[int]],
) -> Tuple[bool, str]:
    """Whether any join touches a table large enough to matter.

    Unknown row counts do not suppress: an unmeasured table is not a
    small one, so the join proceeds and the uncertainty is recorded.
    """

    if not table_rows:
        return True, "table_sizes_unknown"

    for join in joins:
        rows = _side_rows(join, table_rows)

        if any(r is None for r in rows):
            return True, "table_sizes_partially_unknown"

        if any(r >= T.MIN_SIDE_ROWS for r in rows):
            return True, "size_floor_cleared"

    return False, "all_sides_below_min_side_rows"


def _has_declared_pk_side(
    join: Dict[str, Any],
    pk_columns: Set[Tuple[str, str]],
) -> bool:
    """Whether a join key is a declared single-column primary key.

    BigQuery constraints are unenforced, so this lowers confidence in a
    fan-out finding rather than proving one impossible.
    """

    for pair in join.get("key_pairs") or []:
        # Uniqueness of a column says nothing about an expression over
        # it: EXTRACT(DAY FROM pk) has 31 values however unique pk is.
        if pair.get("computed"):
            continue

        left = (pair.get("left_table"), pair.get("left_column"))
        right = (pair.get("right_table"), pair.get("right_column"))

        if left in pk_columns or right in pk_columns:
            return True

    return False


def _duplication_factor(stats: Optional[Dict[str, Any]]) -> Optional[float]:
    """Average rows per distinct key on one side of a join."""

    if not stats:
        return None

    rows = stats.get("row_count")
    ndv = stats.get("ndv")

    if not rows or not ndv:
        return None

    return float(rows) / float(ndv)


def estimate_matches_per_row(
    joins: List[Dict[str, Any]],
    key_stats: Dict[Tuple[str, str], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Estimate fan-out from key cardinality instead of the plan.

    Row multiplication needs duplicate keys on *both* sides: if either
    side is unique the output cannot exceed the other side's row count.
    So the estimate is the smaller of the two duplication factors, which
    reads as "every row finds at least this many partners".

    A dimension lookup scores 1 however skewed the fact side is; a join
    on a two-valued column over 20k rows scores 10,000.
    """

    best = None

    for join in joins:
        for pair in join.get("key_pairs") or []:
            left = _duplication_factor(
                key_stats.get((pair.get("left_table"), pair.get("left_column")))
            )
            right = _duplication_factor(
                key_stats.get(
                    (pair.get("right_table"), pair.get("right_column"))
                )
            )

            if left is None or right is None:
                continue

            matches = min(left, right)

            if best is None or matches > best["matches_per_row"]:
                best = {
                    "matches_per_row": matches,
                    "left_duplication": left,
                    "right_duplication": right,
                    "key_pair": pair,
                }

    return best


def profile_targets(joins: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Base-table columns whose cardinality would resolve a fan-out.

    Only TABLE sources are returned. A CTE or subquery alias reads like a
    table name in the key pair but cannot be selected from, so passing one
    to the profiler spends a dry run to learn that `inflated` does not
    exist.
    """

    targets = []

    for join in joins:
        for pair in join.get("key_pairs") or []:
            for kind, table, column in (
                (pair.get("left_kind"), pair.get("left_table"), pair.get("left_column")),
                (
                    pair.get("right_kind"),
                    pair.get("right_table"),
                    pair.get("right_column"),
                ),
            ):
                if kind != "TABLE":
                    continue

                if table and column and (table, column) not in targets:
                    targets.append((table, column))

    return targets


def _nothing_classified(
    joins: List[Dict[str, Any]],
    stages: Dict[str, Any],
    dominance: Optional[float],
    pk_protected: bool,
    key_stats: Optional[Dict[Tuple[str, str], Dict[str, Any]]],
    expected_future_runs: float,
    slot_ms_reference: Optional[float],
) -> Dict[str, Any]:
    """Verdict when the stage metrics showed no pathology.

    PATTERN_ONLY asserts that nothing is wrong. That is only honest when
    every signal was actually measurable; BigQuery fuses aggregation into
    the join stage often enough that fan-out usually was not.
    """

    common = {
        "evidence_tier": 1,
        "join_dominance": dominance,
        "fanout_measurable": stages.get("fanout_measurable"),
        "aggregate_fused_stages": stages.get("aggregate_fused_stages"),
        "declared_pk_on_a_side": pk_protected,
    }

    if stages.get("fanout_measurable"):
        return _outcome("PATTERN_ONLY", "no_join_pathology_in_stage_metrics", **common)

    # Fan-out was not measurable. A declared primary key bounds it at 1
    # by declaration, which settles the question without profiling.
    if pk_protected:
        return _outcome(
            "NOT_CONFIRMED",
            "declared_primary_key_bounds_fanout",
            **common,
        )

    collapsing = _collapsing_key_join(joins)

    if collapsing is not None:
        return _outcome(
            "PROBABLE",
            "join_key_expression_collapses_cardinality",
            failure_mode="FAN_OUT",
            savings_currency="slot_ms",
            join=collapsing,
            routed=True,
            routing_reason="static_sql_evidence",
            **common,
        )

    estimate = estimate_matches_per_row(joins, key_stats or {})

    if estimate is not None:
        matches = estimate["matches_per_row"]

        if matches < T.MATCHES_PER_ROW_WARN:
            # Tier 2 like the PROBABLE branch below: an estimate exists
            # only when both sides were profiled, so ruling the join out
            # here cost the same NDV queries as confirming it would have.
            return _outcome(
                "NOT_CONFIRMED",
                "estimated_fanout_below_threshold",
                estimated_matches_per_row=matches,
                **{**common, "evidence_tier": 2},
            )

        recoverable = {
            "attributable_join_slot_ms": stages.get("join_slot_ms") or 0,
            "savings_fraction": None,
            "expected_future_runs": expected_future_runs,
            "recoverable_slot_ms_upper_bound": (
                (stages.get("join_slot_ms") or 0) * expected_future_runs
            ),
        }

        gate = _passes_gate(recoverable, expected_future_runs, slot_ms_reference)

        # PROBABLE, never CONFIRMED: this comes from a uniformity
        # assumption over approximate distinct counts, not a measurement.
        return _outcome(
            "PROBABLE",
            "fanout_estimated_from_key_cardinality",
            **{
                **common,
                "evidence_tier": 2,
                "failure_mode": "FAN_OUT",
                "severity": "MEDIUM",
                "routed": gate["passes"],
                "routing_reason": gate["reason"],
                "savings_currency": "slot_ms",
                "estimated_matches_per_row": matches,
                "estimate": estimate,
                "recoverable": recoverable,
            },
        )

    return _outcome(
        "INCONCLUSIVE",
        "fanout_unmeasurable_aggregate_fused",
        missing_evidence=["join_key_cardinality"],
        **common,
    )


def _unconstrained(joins: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """First join that is a cartesian product or a non-hashable range.

    An equality between two expressions is NOT unconstrained: BigQuery
    evaluates both sides and hash joins on the result. Only a missing
    predicate or an inequality-only one leaves it with nothing to hash.
    """

    for join in joins:
        if join.get("predicate_kind") in ("ABSENT", "RANGE"):
            return join

    return None


def _collapsing_key_join(
    joins: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """First join keyed on an expression that collapses cardinality.

    `EXTRACT(DAY FROM a.ts) = EXTRACT(DAY FROM b.ts)` is a valid equi
    join on a key with at most 31 distinct values. That is a fan-out
    risk readable from the SQL alone, which makes it the only route to a
    fan-out finding that survives a cache hit.
    """

    for join in joins:
        if join.get("cardinality_collapsing"):
            return join

    return None


def _spill_is_material(stages: Dict[str, Any]) -> bool:
    """Whether spilled shuffle is large relative to the shuffle itself.

    An absolute spill threshold is not portable across dataset sizes, and
    using one as a trigger let a single spilled byte outrank a measured
    fan-out. The shuffle floor only suppresses ratios taken over a
    shuffle too small to mean anything.
    """

    spilled = stages.get("max_spilled_bytes") or 0
    shuffle = stages.get("total_shuffle_bytes") or 0

    if shuffle < T.SPILL_MIN_SHUFFLE_BYTES:
        return False

    return (spilled / shuffle) >= T.SPILL_RATIO_WARN


def _classify_from_stages(stages: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pick the failure mode from measured stage metrics.

    Skew is tested before fan-out: a hot key produces both signals, and
    skew is the more specific diagnosis with the more targeted fix. That
    ordering is only safe while the skew evidence is genuinely skew
    evidence, hence the ratio test on spill.
    """

    spilled = stages.get("max_spilled_bytes") or 0
    skew = stages.get("max_skew_ratio")
    fanout = stages.get("max_fanout_ratio")

    skewed = skew is not None and skew >= T.SKEW_COMPUTE_RATIO

    if skewed or _spill_is_material(stages):
        return {
            "failure_mode": "KEY_SKEW",
            "savings_currency": "elapsed_time_and_reliability",
            "savings_fraction": None,
            "trigger": {"spilled_bytes": spilled, "skew_ratio": skew},
        }

    if fanout is not None and fanout >= T.FANOUT_RATIO_WARN:
        return {
            "failure_mode": "FAN_OUT",
            "savings_currency": "slot_ms",
            "savings_fraction": 1.0 - (1.0 / fanout),
            "trigger": {"fanout_ratio": fanout},
        }

    return None


def _classify_shuffle_volume(
    stages: Dict[str, Any],
    bytes_processed: Optional[int],
) -> Optional[Dict[str, Any]]:
    """Detect a large, well-distributed shuffle.

    Requires both the amplification ratio and the absolute floor, so a
    high ratio over a small shuffle does not qualify.
    """

    shuffle = stages.get("total_shuffle_bytes") or 0

    if shuffle < T.SHUFFLE_FLOOR_BYTES:
        return None

    if not bytes_processed:
        return None

    if shuffle < T.SHUFFLE_AMPLIFICATION * bytes_processed:
        return None

    return {
        "failure_mode": "SHUFFLE_VOLUME",
        "savings_currency": "slot_ms",
        "savings_fraction": None,
        "trigger": {
            "shuffle_bytes": shuffle,
            "bytes_processed": bytes_processed,
        },
    }


def _severity(
    failure_mode: str,
    stages: Dict[str, Any],
    resources_exceeded: bool,
) -> str:
    """Map a failure mode plus its evidence onto an incident severity."""

    if resources_exceeded or failure_mode == "UNCONSTRAINED_JOIN":
        return "HIGH"

    if failure_mode == "KEY_SKEW" and (stages.get("max_spilled_bytes") or 0) > 0:
        return "HIGH"

    fanout = stages.get("max_fanout_ratio") or 0

    if failure_mode == "FAN_OUT" and fanout >= 4 * T.FANOUT_RATIO_WARN:
        return "HIGH"

    return "MEDIUM"


def _recoverable(
    stages: Dict[str, Any],
    classification: Dict[str, Any],
    expected_future_runs: float,
) -> Dict[str, Any]:
    """Upper bound on the slot time future runs could stop spending.

    An upper bound, not a prediction: where the saving fraction is not
    measurable the whole join stage is assumed recoverable, which is
    optimistic by design so the gate errs toward reporting.
    """

    attributable = stages.get("join_slot_ms") or 0
    fraction = classification.get("savings_fraction")

    bound = attributable * (1.0 if fraction is None else fraction)

    return {
        "attributable_join_slot_ms": attributable,
        "savings_fraction": fraction,
        "expected_future_runs": expected_future_runs,
        "recoverable_slot_ms_upper_bound": bound * expected_future_runs,
    }


def detect_high_cardinality_join(
    job: Dict[str, Any],
    joins: List[Dict[str, Any]],
    stages: Dict[str, Any],
    table_rows: Optional[Dict[str, Optional[int]]] = None,
    pk_columns: Optional[Set[Tuple[str, str]]] = None,
    expected_future_runs: float = T.UNKNOWN_HASH_EXPECTED_RUNS,
    slot_ms_reference: Optional[float] = None,
    key_stats: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Classify a completed job against the HIGH_CARDINALITY_JOIN incident.

    Implements the ordered procedure in section 11 of the design note.
    Every input is already fetched, so this function performs no I/O and
    the whole decision is reproducible from its arguments.
    """

    table_rows = table_rows or {}
    pk_columns = pk_columns or set()
    stages = stages or {}

    analyzable = [j for j in joins if not j.get("suppressed")]

    if not analyzable:
        return _outcome(
            "NOT_APPLICABLE",
            "no_analyzable_joins",
            join_count=len(joins),
        )

    resources_exceeded = _is_resources_exceeded(job)

    unconstrained = _unconstrained(analyzable)

    if unconstrained is not None:
        return _outcome(
            "CONFIRMED",
            "unconstrained_join_predicate",
            failure_mode="UNCONSTRAINED_JOIN",
            severity="HIGH",
            routed=True,
            savings_currency="slot_ms",
            predicate_kind=unconstrained.get("predicate_kind"),
            join=unconstrained,
            tables=unconstrained.get("tables") or [],
            resources_exceeded=resources_exceeded,
        )

    clears, size_reason = _clears_size_floor(analyzable, table_rows)

    if not clears:
        return _outcome(
            "PATTERN_ONLY",
            size_reason,
            join_count=len(analyzable),
        )

    pk_protected = all(
        _has_declared_pk_side(join, pk_columns) for join in analyzable
    )

    if not stages.get("available") or not stages.get("join_stage_count"):
        return _tier0_outcome(
            analyzable,
            pk_protected,
            stages,
            resources_exceeded,
            cache_hit=bool(job.get("cache_hit")),
        )

    dominance = stages.get("join_dominance")

    if dominance is not None and dominance < T.JOIN_DOMINANCE:
        # The dominance gate asks whether the join is the cost. A key
        # expression that collapses cardinality answers a different
        # question: whether the join multiplies rows, which inflates
        # downstream aggregates whatever share of the cost it took. That
        # is a correctness risk, not only a cost one, so a cost gate must
        # not discard it — the more so because it is read from the SQL
        # text and does not vary between runs, while dominance does.
        collapsing = _collapsing_key_join(analyzable)

        if collapsing is not None:
            return _outcome(
                "PROBABLE",
                "join_key_expression_collapses_cardinality",
                failure_mode="FAN_OUT",
                severity="MEDIUM",
                savings_currency="slot_ms",
                join=collapsing,
                tables=collapsing.get("tables") or [],
                routed=True,
                routing_reason="static_sql_evidence",
                evidence_tier=1,
                join_dominance=dominance,
                join_cost_share_below_gate=True,
                resources_exceeded=resources_exceeded,
            )

        return _outcome(
            "NOT_CONFIRMED",
            "join_stage_does_not_dominate_cost",
            join_dominance=dominance,
            evidence_tier=1,
            routing_hint="MISSING_PARTITION_FILTER",
        )

    classification = _classify_from_stages(stages) or _classify_shuffle_volume(
        stages,
        job.get("total_bytes_processed"),
    )

    if classification is None:
        return _nothing_classified(
            analyzable,
            stages,
            dominance,
            pk_protected,
            key_stats,
            expected_future_runs,
            slot_ms_reference,
        )

    recoverable = _recoverable(stages, classification, expected_future_runs)

    gate = _passes_gate(recoverable, expected_future_runs, slot_ms_reference)

    return _outcome(
        "CONFIRMED",
        "classified_from_stage_metrics",
        failure_mode=classification["failure_mode"],
        severity=_severity(
            classification["failure_mode"],
            stages,
            resources_exceeded,
        ),
        evidence_tier=1,
        routed=gate["passes"],
        routing_reason=gate["reason"],
        join_dominance=dominance,
        savings_currency=classification["savings_currency"],
        trigger=classification["trigger"],
        recoverable=recoverable,
        declared_pk_on_a_side=pk_protected,
        constraint_contradicted=(
            pk_protected and classification["failure_mode"] == "FAN_OUT"
        ),
        resources_exceeded=resources_exceeded,
        joins=analyzable,
    )


def _is_resources_exceeded(job: Dict[str, Any]) -> bool:
    """Whether the job failed for want of resources.

    A failed join is the strongest single signal available, and the
    reason ground truth for threshold calibration.
    """

    error = job.get("error_result") or {}

    if not isinstance(error, dict):
        return False

    reason = (error.get("reason") or "").lower()
    message = (error.get("message") or "").lower()

    return "resourcesexceeded" in reason or "resources exceeded" in message


def _tier0_outcome(
    joins: List[Dict[str, Any]],
    pk_protected: bool,
    stages: Dict[str, Any],
    resources_exceeded: bool,
    cache_hit: bool = False,
) -> Dict[str, Any]:
    """Verdict when no stage evidence is available.

    A declared primary key on every join key is the free short-circuit.
    A key that resolves only to a CTE or subquery cannot be judged at
    all without stages, so it is inconclusive rather than benign.
    """

    if pk_protected:
        return _outcome(
            "NOT_CONFIRMED",
            "declared_primary_key_on_every_join_key",
            declared_pk_on_a_side=True,
        )

    # Checked before the cache branch: a key expression that collapses
    # cardinality is a property of the SQL text, so it holds whether or
    # not the query ever executed. This is the only fan-out route that
    # works on a cached job, where no plan exists at all.
    collapsing = _collapsing_key_join(joins)

    if collapsing is not None:
        return _outcome(
            "PROBABLE",
            "join_key_expression_collapses_cardinality",
            failure_mode="FAN_OUT",
            # MEDIUM, not HIGH: the key shape is certain but the impact
            # is inferred from the SQL rather than measured.
            severity="MEDIUM",
            savings_currency="slot_ms",
            join=collapsing,
            tables=collapsing.get("tables") or [],
            routed=True,
            routing_reason="static_sql_evidence",
            cache_hit=cache_hit,
            resources_exceeded=resources_exceeded,
        )

    # A cached result was never executed, so no plan exists to fetch.
    # Reporting that as missing evidence implies a lookup failure, when
    # in fact there is nothing to look up and nothing was spent.
    if cache_hit:
        return _outcome(
            "INCONCLUSIVE",
            "cache_hit_no_execution_plan",
            cache_hit=True,
            missing_evidence=["job_stages"],
            joins=joins,
        )

    if any(not join.get("resolved") for join in joins):
        return _outcome(
            "INCONCLUSIVE",
            "join_key_resolves_to_derived_table_and_no_stage_evidence",
            missing_evidence=["job_stages"],
        )

    return _outcome(
        "PROBABLE",
        stages.get("reason") or "no_stage_evidence_available",
        missing_evidence=["job_stages"],
        resources_exceeded=resources_exceeded,
        joins=joins,
    )


def _passes_gate(
    recoverable: Dict[str, Any],
    expected_future_runs: float,
    slot_ms_reference: Optional[float],
) -> Dict[str, Any]:
    """Decide whether a confirmed incident is worth a person's time.

    Confidence and worth are separate: a correct finding on a query that
    will not run again is recorded and aggregated, never routed.
    """

    if expected_future_runs < T.MIN_EXPECTED_RUNS:
        return {"passes": False, "reason": "below_min_expected_runs"}

    if slot_ms_reference is None:
        return {"passes": True, "reason": "percentile_gate_disabled"}

    if recoverable["recoverable_slot_ms_upper_bound"] < slot_ms_reference:
        return {"passes": False, "reason": "below_slot_ms_reference"}

    return {"passes": True, "reason": "recoverable_above_reference"}
