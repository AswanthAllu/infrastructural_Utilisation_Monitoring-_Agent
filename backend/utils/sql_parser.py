from typing import Optional

import sqlglot
from sqlglot import exp


def parse_sql(sql: str) -> Optional[exp.Expression]:
    """
    Parse BigQuery SQL using sqlglot.

    Returns:
        Parsed SQL expression or None if parsing fails.
    """

    if not sql or not sql.strip():
        return None

    try:
        return sqlglot.parse_one(
            sql,
            dialect="bigquery",
        )
    except sqlglot.errors.ParseError:
        return None


def _is_partition_column(
    column: exp.Column,
    partition_column: str,
) -> bool:
    return (
        column.name.lower()
        == partition_column.lower()
    )


def _contains_partition_comparison(
    expression: exp.Expression,
    partition_column: str,
) -> bool:

    comparison_types = (
        exp.EQ,
        exp.GT,
        exp.GTE,
        exp.LT,
        exp.LTE,
        exp.Between,
        exp.In,
    )

    for node in expression.walk():

        if not isinstance(
            node,
            comparison_types,
        ):
            continue

        columns = list(
            node.find_all(exp.Column)
        )

        for column in columns:
            if _is_partition_column(
                column,
                partition_column,
            ):
                return True

    return False


def has_partition_filter(
    sql: str,
    partition_column: str,
) -> bool:
    """
    Determine whether SQL contains a usable
    partition-column filter.

    Supported predicates:

    =
    >
    >=
    <
    <=
    BETWEEN
    IN

    IS NOT NULL is intentionally not treated
    as a useful partition filter.
    """

    parsed_sql = parse_sql(sql)

    if parsed_sql is None:
        return False

    where_clause = parsed_sql.find(
        exp.Where
    )

    if where_clause is None:
        return False

    return _contains_partition_comparison(
        where_clause,
        partition_column,
    )