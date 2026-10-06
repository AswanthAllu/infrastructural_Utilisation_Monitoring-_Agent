"""The suite splitter must produce exactly the statements in the file.

A miscount here silently changes what gets tested, so the boundaries are
pinned rather than trusted.
"""

import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

sys.path.insert(0, str(SCRIPTS))

from run_validation_suite import (  # noqa: E402
    label_of,
    split_statements,
)


SUITE = SCRIPTS / "validation_suite.sql"
FIXTURES = SCRIPTS / "fixtures_setup.sql"


def test_suite_file_splits_into_seventeen_statements():
    statements = split_statements(SUITE.read_text(encoding="utf-8"))

    assert len(statements) == 17


def test_no_statement_is_only_comments():
    for statement in split_statements(SUITE.read_text(encoding="utf-8")):
        body = [
            line
            for line in statement.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]

        assert body, f"comment-only fragment survived: {statement[:40]!r}"


def test_fixture_ddl_and_insert_are_kept_in_order():
    statements = split_statements(FIXTURES.read_text(encoding="utf-8"))

    create = next(i for i, s in enumerate(statements) if "CREATE OR REPLACE" in s)
    insert = next(i for i, s in enumerate(statements) if "INSERT INTO" in s)

    assert create < insert


def test_the_suite_does_not_recreate_its_own_fixtures():
    """A CREATE OR REPLACE inside the suite invalidates the fixture's
    cache on every run, which is why the tier-0 primary-key short-circuit
    was never reachable and why the PK join produced a spurious
    MISSING_PARTITION_FILTER incident each review."""

    # Executable lines only — the header comment explains why the DDL was
    # moved out, and must not trip its own assertion.
    body = "\n".join(
        line
        for line in SUITE.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    )

    assert "CREATE OR REPLACE" not in body
    assert "INSERT INTO" not in body
    assert "customers_pk` AS c" in body, "the PK join itself must stay"


def test_semicolon_inside_a_string_does_not_split():
    statements = split_statements("SELECT 'a;b' AS x; SELECT 2;")

    assert len(statements) == 2
    assert "'a;b'" in statements[0]


def test_semicolon_inside_a_comment_does_not_split():
    statements = split_statements("-- one; two\nSELECT 1;\nSELECT 2;")

    assert len(statements) == 2


def test_semicolon_inside_backticks_does_not_split():
    statements = split_statements("SELECT 1 FROM `p.d.a;b`; SELECT 2;")

    assert len(statements) == 2


def test_trailing_statement_without_semicolon_is_kept():
    statements = split_statements("SELECT 1;\nSELECT 2")

    assert len(statements) == 2


@pytest.mark.parametrize(
    "statement,expected",
    [
        ("-- 8. computed key\nSELECT 1", "8. computed key"),
        ("SELECT 1 FROM t", "SELECT 1 FROM t"),
    ],
)
def test_label_prefers_the_leading_comment(statement, expected):
    assert label_of(statement) == expected
