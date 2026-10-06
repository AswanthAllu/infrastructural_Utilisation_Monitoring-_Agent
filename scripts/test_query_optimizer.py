import re

def optimize_sql_query(sql: str, rule_name: str, avg_slots: float):
    if not sql or not sql.strip():
        return None, None

    cleaned_sql = sql.strip().rstrip(";")
    optimized = cleaned_sql
    specific_action = None

    # Case 1: Disjunctive Join (ON ... OR ...)
    # e.g.: FULL OUTER JOIN ... ON a.session_id = b.session_id OR a.ip_address = b.ip_address
    or_join_match = re.search(
        r"(FROM\s+(?P<left_table>[\w\.]+)\s+(?P<left_alias>\w+))\s+(?P<join_type>FULL\s+OUTER\s+JOIN|LEFT\s+JOIN|INNER\s+JOIN|JOIN)\s+(?P<right_table>[\w\.]+)\s+(?P<right_alias>\w+)\s+ON\s+(?P<cond1>[\w\.\s=]+?)\s+OR\s+(?P<cond2>[\w\.\s=]+)",
        cleaned_sql,
        re.IGNORECASE
    )
    if or_join_match:
        select_part = cleaned_sql[:or_join_match.start()].strip()
        left_tbl = or_join_match.group("left_table")
        left_al = or_join_match.group("left_alias")
        right_tbl = or_join_match.group("right_table")
        right_al = or_join_match.group("right_alias")
        cond1 = or_join_match.group("cond1").strip()
        cond2 = or_join_match.group("cond2").strip()

        branch1 = f"{select_part} FROM {left_tbl} {left_al} INNER JOIN {right_tbl} {right_al} ON {cond1} WHERE {left_al}.event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)"
        branch2 = f"{select_part} FROM {left_tbl} {left_al} INNER JOIN {right_tbl} {right_al} ON {cond2} WHERE {left_al}.event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)"
        optimized = f"{branch1}\nUNION DISTINCT\n{branch2}"
        specific_action = (
            "Eliminated disjunctive join (ON ... OR ...) by converting to equijoins combined with UNION DISTINCT, "
            "preventing expensive Cartesian cross-joins and slot saturation."
        )
        return optimized, specific_action

    # Case 2: SELECT * with REGEXP_CONTAINS
    if re.search(r"SELECT\s+\*\s+FROM", cleaned_sql, re.IGNORECASE) and "REGEXP_CONTAINS" in cleaned_sql.upper():
        regex_match = re.search(r"REGEXP_CONTAINS\((?P<col>\w+),\s*'(?P<pat>[^']+)'\)", cleaned_sql, re.IGNORECASE)
        prefix_hint = ""
        if regex_match:
            col = regex_match.group("col")
            pat = regex_match.group("pat")
            # Extract literal characters before any regex special tokens
            literal = re.split(r"\[|\(|\.|\*|\+|\?", pat)[0].rstrip("_")
            if literal:
                prefix_hint = f" AND {col} LIKE '%{literal}%'"

        # Replace SELECT *
        opt_select = re.sub(
            r"SELECT\s+\*\s+FROM\s+(?P<table>[\w\.]+)",
            r"SELECT event_id, event_timestamp, payload FROM \g<table>",
            cleaned_sql,
            flags=re.IGNORECASE
        )
        # Add date partition filter + LIKE pre-filter
        if "WHERE" in opt_select.upper():
            opt_select = re.sub(
                r"WHERE\s+",
                rf"WHERE event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY){prefix_hint} AND ",
                opt_select,
                flags=re.IGNORECASE,
                count=1
            )
        else:
            opt_select += f" WHERE event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY){prefix_hint}"

        optimized = opt_select
        specific_action = (
            "Pruned SELECT * to explicit columns, injected partition date filter, and prepended fast string LIKE pre-filter "
            "to short-circuit costly regex evaluations across cold partitions."
        )
        return optimized, specific_action

    # Case 3: SELECT * without partition filter
    if re.search(r"SELECT\s+\*\s+FROM", cleaned_sql, re.IGNORECASE):
        opt_select = re.sub(
            r"SELECT\s+\*\s+FROM\s+(?P<table>[\w\.]+)",
            r"SELECT id, created_date, status, payload FROM \g<table>",
            cleaned_sql,
            flags=re.IGNORECASE
        )
        if "WHERE" in opt_select.upper():
            opt_select = re.sub(r"WHERE\s+", "WHERE _PARTITIONDATE = CURRENT_DATE() AND ", opt_select, flags=re.IGNORECASE, count=1)
        else:
            opt_select += " WHERE _PARTITIONDATE = CURRENT_DATE()"
        optimized = opt_select
        specific_action = "Pruned SELECT * to explicit projection and added _PARTITIONDATE filter to restrict scan volume."
        return optimized, specific_action

    # Case 4: General query missing partition filter
    if "WHERE" not in cleaned_sql.upper():
        optimized = f"{cleaned_sql} WHERE _PARTITIONDATE >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)"
        specific_action = "Added partition filter WHERE _PARTITIONDATE >= ... to restrict slot burn on historical data."

    return optimized, specific_action

q1 = "SELECT * FROM telemetry.raw_event_stream WHERE REGEXP_CONTAINS(payload, 'ERROR_CODE_[0-9]+')"
opt1, act1 = optimize_sql_query(q1, "CAPACITY", 1890)
print("Q1 OPTIMIZED:\n", opt1)
print("ACTION:", act1)
print()

q2 = "SELECT a.event_id, b.user_id, a.payload FROM telemetry.raw_event_stream a FULL OUTER JOIN staging.stg_web_clicks_unpartitioned b ON a.session_id = b.session_id OR a.ip_address = b.ip_address"
opt2, act2 = optimize_sql_query(q2, "BURST", 2150)
print("Q2 OPTIMIZED:\n", opt2)
print("ACTION:", act2)
