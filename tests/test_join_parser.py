import pytest

from utils.join_parser import extract_joins


def only_join(sql, **kwargs):
    result = extract_joins(sql, **kwargs)

    assert result["success"], result

    return result["joins"][0]


def test_inner_equi_join_resolves_both_sides():
    join = only_join(
        "SELECT 1 FROM `p.d.orders` o JOIN `p.d.customers` c ON o.cust_id = c.id"
    )

    assert join["predicate_kind"] == "EQUI"
    assert join["join_type"] == "INNER"
    assert join["resolved"] is True
    assert join["tables"] == ["p.d.customers", "p.d.orders"]

    pair = join["key_pairs"][0]

    assert {pair["left_column"], pair["right_column"]} == {"cust_id", "id"}


def test_composite_key_yields_one_pair_per_column():
    join = only_join(
        "SELECT 1 FROM `p.d.a` a JOIN `p.d.b` b "
        "ON a.k1 = b.k1 AND a.k2 = b.k2"
    )

    assert len(join["key_pairs"]) == 2
    assert join["predicate_kind"] == "EQUI"


def test_left_join_records_side():
    join = only_join(
        "SELECT 1 FROM `p.d.a` a LEFT JOIN `p.d.b` b ON a.k = b.k"
    )

    assert join["join_type"] == "LEFT"


def test_using_clause_expands_to_key_pairs():
    join = only_join("SELECT 1 FROM `p.d.a` a JOIN `p.d.b` b USING (k)")

    assert join["predicate_kind"] == "EQUI"
    assert join["key_pairs"][0]["left_column"] == "k"
    assert join["key_pairs"][0]["right_column"] == "k"


def test_literal_equality_is_not_a_join_key():
    join = only_join(
        "SELECT 1 FROM `p.d.a` a JOIN `p.d.b` b ON a.k = b.k AND b.status = 'X'"
    )

    assert len(join["key_pairs"]) == 1


def test_same_source_equality_is_not_a_join_key():
    join = only_join(
        "SELECT 1 FROM `p.d.a` a JOIN `p.d.b` b ON a.k = b.k AND b.x = b.y"
    )

    assert len(join["key_pairs"]) == 1


def test_unqualified_columns_resolve_with_schema():
    schema = {
        "p": {
            "d": {
                "orders": {"cust_id": "STRING"},
                "customers": {"id": "STRING"},
            }
        }
    }

    join = only_join(
        "SELECT 1 FROM `p.d.orders` JOIN `p.d.customers` ON cust_id = id",
        schema=schema,
    )

    assert join["predicate_kind"] == "EQUI"
    assert join["resolved"] is True
    assert join["tables"] == ["p.d.customers", "p.d.orders"]


# Section 12 — patterns that must never be reported as this incident.


def test_cross_join_unnest_is_suppressed():
    join = only_join("SELECT 1 FROM `p.d.events` e CROSS JOIN UNNEST(e.items) AS i")

    assert join["suppressed"] is True
    assert join["suppression_reason"] == "unnest_array_flattening"
    assert join["predicate_kind"] == "UNNEST"


def test_comma_unnest_is_suppressed():
    result = extract_joins("SELECT 1 FROM `p.d.events` e, UNNEST(e.items) AS i")

    assert result["analyzable_joins"] == []


def test_semi_join_produces_no_join_node():
    result = extract_joins(
        "SELECT 1 FROM `p.d.a` a "
        "WHERE EXISTS (SELECT 1 FROM `p.d.b` b WHERE b.k = a.k)"
    )

    assert result["success"]
    assert result["join_count"] == 0


def test_in_subquery_produces_no_join_node():
    result = extract_joins(
        "SELECT 1 FROM `p.d.a` a WHERE a.k IN (SELECT k FROM `p.d.b`)"
    )

    assert result["join_count"] == 0


def test_comma_join_with_where_predicate_is_equi_not_cartesian():
    join = only_join(
        "SELECT 1 FROM `p.d.a` a, `p.d.b` b WHERE a.k = b.k AND a.d = '2026-01-01'"
    )

    assert join["predicate_kind"] == "EQUI"
    assert len(join["key_pairs"]) == 1


def test_genuine_cross_join_is_absent_predicate():
    join = only_join("SELECT 1 FROM `p.d.a` a CROSS JOIN `p.d.b` b")

    assert join["predicate_kind"] == "ABSENT"
    assert join["suppressed"] is False


def test_comma_join_without_predicate_is_absent():
    join = only_join("SELECT 1 FROM `p.d.a` a, `p.d.b` b WHERE a.x > 5")

    assert join["predicate_kind"] == "ABSENT"


def test_range_join_is_classified_as_range():
    join = only_join(
        "SELECT 1 FROM `p.d.a` a JOIN `p.d.b` b ON a.ts BETWEEN b.s AND b.e"
    )

    assert join["predicate_kind"] == "RANGE"
    assert join["residual_predicates"]


def test_equi_join_with_extra_range_keeps_both():
    join = only_join(
        "SELECT 1 FROM `p.d.a` a JOIN `p.d.b` b "
        "ON a.k = b.k AND a.ts BETWEEN b.s AND b.e"
    )

    assert join["predicate_kind"] == "EQUI"
    assert join["residual_predicates"]


def test_cte_side_is_unresolved():
    join = only_join(
        "WITH c AS (SELECT k FROM `p.d.b`) "
        "SELECT 1 FROM `p.d.a` a JOIN c ON a.k = c.k"
    )

    assert join["predicate_kind"] == "EQUI"
    assert join["resolved"] is False


def test_subquery_side_is_unresolved():
    join = only_join(
        "SELECT 1 FROM `p.d.a` a "
        "JOIN (SELECT k FROM `p.d.b`) s ON a.k = s.k"
    )

    assert join["resolved"] is False


# Structure.


def test_three_table_join_pairs_tables_by_qualifier_not_position():
    result = extract_joins(
        "SELECT 1 FROM `p.d.a` a "
        "JOIN `p.d.b` b ON a.k = b.k "
        "JOIN `p.d.c` c ON b.j = c.j"
    )

    assert result["join_count"] == 2
    assert result["joins"][0]["tables"] == ["p.d.a", "p.d.b"]
    assert result["joins"][1]["tables"] == ["p.d.b", "p.d.c"]


def test_alias_reused_across_scopes_resolves_per_select():
    result = extract_joins(
        "SELECT 1 FROM `p.d.outer_left` x "
        "JOIN `p.d.outer_right` y ON x.k = y.k "
        "WHERE x.k IN ("
        "  SELECT x.k FROM `p.d.inner_left` x JOIN `p.d.inner_right` y ON x.k = y.k"
        ")"
    )

    assert result["join_count"] == 2

    tables = {tuple(j["tables"]) for j in result["joins"]}

    assert ("p.d.outer_left", "p.d.outer_right") in tables
    assert ("p.d.inner_left", "p.d.inner_right") in tables


def test_no_join_returns_empty():
    result = extract_joins("SELECT 1 FROM `p.d.a` WHERE x = 1")

    assert result["success"]
    assert result["joins"] == []


@pytest.mark.parametrize("sql", ["", "   ", None])
def test_empty_sql_fails_cleanly(sql):
    result = extract_joins(sql)

    assert result["success"] is False
    assert result["error"] == "EMPTY_SQL"


def test_unparseable_sql_fails_cleanly():
    result = extract_joins("SELECT FROM WHERE JOIN ON )(")

    assert result["success"] is False
    assert result["joins"] == []


def test_base_tables_follow_the_query_not_the_alphabet():
    """`tables` is sorted, so its head named a table the SQL did not start
    FROM on most multi-table statements. An agent handed that
    contradiction rewrote the query's FROM clause to agree with it."""

    parsed = extract_joins(
        "SELECT 1 FROM `p.d.transactions` AS t "
        "JOIN `p.d.loan_applications` AS l ON t.k = l.k"
    )

    assert parsed["base_tables"] == ["p.d.transactions", "p.d.loan_applications"]
    assert parsed["base_tables"][0] != sorted(parsed["base_tables"])[0]


def test_base_tables_reach_through_a_cte_to_the_real_table():
    """A CTE join used to report the CTE's own name as the table."""

    parsed = extract_joins(
        "WITH probe AS (SELECT k FROM `p.d.transactions`) "
        "SELECT 1 FROM probe AS a JOIN probe AS b ON a.k = b.k"
    )

    assert parsed["base_tables"] == ["p.d.transactions"]
    assert "probe" not in parsed["base_tables"]
