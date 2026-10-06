from typing import Any, Dict, List, Optional

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify


COMPARISON_TYPES = (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)


# Functions that map many input values onto few. A join key built from
# one of these has far fewer distinct values than the column it came
# from — EXTRACT(DAY FROM ts) has at most 31 — which is a fan-out risk
# readable from the SQL alone, with no execution plan and no profiling.
#
# Anything not listed is assumed to preserve cardinality, so an unknown
# function produces no finding rather than a false one.
CARDINALITY_COLLAPSING = {
    "Extract",
    "Date",
    "DateTrunc",
    "DatetimeTrunc",
    "TimestampTrunc",
    "TimeTrunc",
    "TimeToStr",
    "TsOrDsToDate",
    "Substring",
    "Left",
    "Right",
    "Round",
    "Floor",
    "Ceil",
    "Mod",
    "IntDiv",
}


def _parse(sql: str, schema: Optional[Dict[str, Any]]):
    """Parse and qualify BigQuery SQL.

    Qualification resolves unqualified join columns to their source table.
    It is attempted with the supplied schema, then without, then skipped;
    an unqualified tree yields unresolved joins rather than wrong ones.
    """

    tree = sqlglot.parse_one(sql, dialect="bigquery")

    for attempt in ((schema,) if schema else ()) + (None,):
        try:
            return qualify(tree.copy(), schema=attempt, dialect="bigquery")
        except Exception:
            continue

    return tree


def _table_ref(table: exp.Table) -> str:
    """Join a table's catalog, dataset and name into a dotted reference."""

    parts = [p for p in (table.catalog, table.db, table.name) if p]

    return ".".join(parts)


def _classify_source(node: exp.Expression, cte_names: set) -> Dict[str, Any]:
    """Classify one FROM/JOIN operand as TABLE, CTE, UNNEST or DERIVED.

    Only TABLE sources can be profiled or looked up in table metadata, so
    the distinction decides whether a join is analyzable.
    """

    alias = node.alias if hasattr(node, "alias") else None

    if isinstance(node, exp.Unnest):
        return {"key": alias or None, "kind": "UNNEST", "name": None}

    if isinstance(node, exp.Table):
        name = _table_ref(node)

        if name in cte_names:
            return {"key": alias or name, "kind": "CTE", "name": name}

        return {"key": alias or name, "kind": "TABLE", "name": name}

    return {"key": alias or None, "kind": "DERIVED", "name": None}


def _source_map(select: exp.Select, cte_names: set) -> Dict[str, Dict[str, Any]]:
    """Map alias (or bare name) to source for one SELECT's FROM and JOINs.

    Built per SELECT rather than per query so that an alias reused in a
    different scope does not resolve to the wrong table.
    """

    sources: Dict[str, Dict[str, Any]] = {}

    from_clause = select.find(exp.From)
    nodes = [from_clause.this] if from_clause else []
    nodes += [join.this for join in select.args.get("joins") or []]

    for node in nodes:
        entry = _classify_source(node, cte_names)

        if entry["key"]:
            sources[entry["key"]] = entry

    return sources


def _column_source(
    column: exp.Column,
    sources: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Resolve a column's table qualifier to its source, if it has one."""

    qualifier = column.table

    if not qualifier:
        return None

    return sources.get(qualifier)


def _expression_source(
    expression: exp.Expression,
    sources: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Resolve an expression to the single source it reads from.

    Returns None when it touches no source or more than one, since
    neither can be one side of a join key.
    """

    if isinstance(expression, exp.Column):
        return _column_source(expression, sources)

    resolved = {
        column.table
        for column in expression.find_all(exp.Column)
        if column.table
    }

    if len(resolved) != 1:
        return None

    return sources.get(next(iter(resolved)))


def _single_column(expression: exp.Expression) -> Optional[str]:
    """Name the one column an expression reads, if there is exactly one."""

    columns = {column.name for column in expression.find_all(exp.Column)}

    return next(iter(columns)) if len(columns) == 1 else None


def _collapses_cardinality(expression: exp.Expression) -> bool:
    """Whether an expression maps many input values onto few."""

    return any(
        type(node).__name__ in CARDINALITY_COLLAPSING
        for node in expression.walk()
    )


def _equi_pairs(
    predicate: exp.Expression,
    sources: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract equality pairs spanning two sources.

    Both bare columns (`a.k = b.k`) and computed keys
    (`UPPER(a.k) = UPPER(b.k)`) are join keys: BigQuery evaluates the
    expressions and hash joins on the result. Treating a computed key as
    "no predicate" would call an ordinary equi-join a cartesian product.

    Equalities against a literal, or between two columns of the same
    source, are filters rather than join keys and are skipped.
    """

    pairs = []

    for node in predicate.find_all(exp.EQ):
        left, right = node.this, node.expression

        left_source = _expression_source(left, sources)
        right_source = _expression_source(right, sources)

        if not left_source or not right_source:
            continue

        if left_source["key"] == right_source["key"]:
            continue

        computed = not (
            isinstance(left, exp.Column) and isinstance(right, exp.Column)
        )

        pairs.append(
            {
                "left_source": left_source["key"],
                "left_table": left_source["name"],
                "left_kind": left_source["kind"],
                "left_column": _single_column(left),
                "right_source": right_source["key"],
                "right_table": right_source["name"],
                "right_kind": right_source["kind"],
                "right_column": _single_column(right),
                "computed": computed,
                "cardinality_collapsing": computed
                and (
                    _collapses_cardinality(left)
                    or _collapses_cardinality(right)
                ),
            }
        )

    return pairs


def _residuals(predicate: exp.Expression) -> List[str]:
    """Collect inequality predicates that span two sources.

    These are the range/interval joins that cannot be hash joined.
    """

    out = []

    for node in predicate.find_all(*COMPARISON_TYPES):
        columns = [c for c in node.find_all(exp.Column) if c.table]

        if len({c.table for c in columns}) > 1:
            out.append(node.sql(dialect="bigquery"))

    return out


def _using_pairs(
    join: exp.Join,
    right_key: Optional[str],
    sources: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Expand USING (col, ...) into explicit key pairs."""

    left_key = next((k for k in sources if k != right_key), None)

    if not left_key or not right_key:
        return []

    left_source = sources[left_key]
    right_source = sources[right_key]

    return [
        {
            "left_source": left_key,
            "left_table": left_source["name"],
            "left_kind": left_source["kind"],
            "left_column": identifier.name,
            "right_source": right_key,
            "right_table": right_source["name"],
            "right_kind": right_source["kind"],
            "right_column": identifier.name,
        }
        for identifier in join.args.get("using") or []
    ]


def _where_pairs(
    select: exp.Select,
    right_key: Optional[str],
    sources: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Find join keys for a comma join, which carries them in WHERE.

    sqlglot renders `FROM a, b` identically to `CROSS JOIN`, so without
    this check every comma join looks like a cartesian product.
    """

    where = select.find(exp.Where)

    if where is None or right_key is None:
        return []

    return [
        pair
        for pair in _equi_pairs(where, sources)
        if right_key in (pair["left_source"], pair["right_source"])
    ]


def _join_type(join: exp.Join) -> str:
    """Render the join type, e.g. INNER, LEFT, CROSS, FULL OUTER."""

    side = (join.args.get("side") or "").upper()
    kind = (join.args.get("kind") or "").upper()

    return " ".join(p for p in (side, kind) if p) or "INNER"


def _describe_join(
    join: exp.Join,
    index: int,
    select: exp.Select,
    sources: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Reduce one join node to its keys, predicate kind and analyzability.

    predicate_kind is one of EQUI, RANGE, ABSENT or UNNEST. ABSENT means a
    genuine cartesian product: no ON, no USING, and no linking predicate
    in WHERE.
    """

    right = _classify_source(join.this, set())
    right_key = right["key"]

    result: Dict[str, Any] = {
        "index": index,
        "join_type": _join_type(join),
        "right_source": right_key,
        "right_source_kind": right["kind"],
        "key_pairs": [],
        "residual_predicates": [],
        "tables": [],
        "resolved": False,
        "suppressed": False,
        "suppression_reason": None,
    }

    if right["kind"] == "UNNEST":
        result["predicate_kind"] = "UNNEST"
        result["suppressed"] = True
        result["suppression_reason"] = "unnest_array_flattening"

        return result

    on = join.args.get("on")

    if on is not None:
        result["key_pairs"] = _equi_pairs(on, sources)
        result["residual_predicates"] = _residuals(on)
    elif join.args.get("using"):
        result["key_pairs"] = _using_pairs(join, right_key, sources)
    else:
        result["key_pairs"] = _where_pairs(select, right_key, sources)

    pairs = result["key_pairs"]

    result["computed_key"] = bool(pairs) and all(
        pair["computed"] for pair in pairs
    )

    result["cardinality_collapsing"] = any(
        pair["cardinality_collapsing"] for pair in pairs
    )

    if pairs and not result["computed_key"]:
        result["predicate_kind"] = "EQUI"
    elif pairs:
        result["predicate_kind"] = "EQUI_COMPUTED"
    elif result["residual_predicates"]:
        result["predicate_kind"] = "RANGE"
    else:
        result["predicate_kind"] = "ABSENT"

    kinds = {pair["left_kind"] for pair in pairs}
    kinds |= {pair["right_kind"] for pair in pairs}

    # A computed key cannot be profiled from its base column's distinct
    # count, because the expression changes the cardinality. Mark it
    # unresolved so nothing tries.
    result["resolved"] = (
        bool(pairs) and kinds == {"TABLE"} and not result["computed_key"]
    )

    result["tables"] = sorted(
        {
            table
            for pair in result["key_pairs"]
            for table in (pair["left_table"], pair["right_table"])
            if table
        }
    )

    # A cartesian or range-only join has no key pairs to read tables
    # from, but it still concerns the base tables in its SELECT. Without
    # this the most severe failure mode reports no tables at all.
    if not result["tables"]:
        result["tables"] = sorted(
            {
                source["name"]
                for source in sources.values()
                if source["kind"] == "TABLE" and source["name"]
            }
        )

    return result


def extract_joins(
    sql: str,
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract every join in a BigQuery query.

    Returns the full join list plus `analyzable_joins`, which excludes
    patterns that are not this incident: UNNEST array flattening, and
    semi/anti joins, which produce no join node at all.

    `schema` is a sqlglot schema mapping used to resolve unqualified join
    columns to their source table.
    """

    if not sql or not sql.strip():
        return {"success": False, "error": "EMPTY_SQL", "joins": []}

    try:
        tree = _parse(sql, schema)
    except Exception as exc:
        return {
            "success": False,
            "error": "PARSE_FAILED",
            "message": str(exc),
            "joins": [],
        }

    cte_names = {cte.alias for cte in tree.find_all(exp.CTE)}

    joins: List[Dict[str, Any]] = []
    base_tables: List[str] = []
    index = 0

    for select in tree.find_all(exp.Select):
        sources = _source_map(select, cte_names)

        # Declaration order, not alphabetical. An incident that names a
        # table the query does not start FROM is a contradiction, and an
        # agent handed one has been observed resolving it by rewriting
        # the query's FROM clause to agree.
        for source in sources.values():
            if source["kind"] == "TABLE" and source["name"] not in base_tables:
                base_tables.append(source["name"])

        select_joins = select.args.get("joins") or []

        for join in select_joins:
            joins.append(_describe_join(join, index, select, sources))
            index += 1

    return {
        "success": True,
        "joins": joins,
        "join_count": len(joins),
        "base_tables": base_tables,
        "analyzable_joins": [j for j in joins if not j["suppressed"]],
    }
