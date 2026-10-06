"""Every verdict reason must have a plain-English reading.

Most entries in `evaluated` never become incidents, so they never reach
an agent and never get explained in prose. For those the reason slug is
the only account of what happened, which makes the mapping the whole
explanation rather than a convenience.
"""

import re
from pathlib import Path

import pytest

from tools.bigquery.reason_text import REASON_TEXT, explain


DETECTOR = (
    Path(__file__).resolve().parent.parent
    / "tools"
    / "bigquery"
    / "join_detection.py"
)


def reasons_emitted_by_the_detector():
    """Slugs passed as the second positional argument to _outcome()."""

    source = DETECTOR.read_text(encoding="utf-8")

    return set(re.findall(r'_outcome\(\s*"[A-Z_]+",\s*\n\s*"([a-z0-9_]+)"', source))


def test_every_emitted_reason_has_an_explanation():
    missing = reasons_emitted_by_the_detector() - set(REASON_TEXT)

    assert not missing, f"no plain-English reading for: {sorted(missing)}"


def test_the_detector_emits_reasons_this_test_can_find():
    """Guards the regex above: if it matches nothing the test is vacuous."""

    assert len(reasons_emitted_by_the_detector()) >= 8


def test_explanations_are_prose_not_slugs():
    for reason, text in REASON_TEXT.items():
        assert " " in text, f"{reason}: not a sentence"
        assert text[0].isupper(), f"{reason}: does not start capitalised"
        assert text.rstrip().endswith("."), f"{reason}: no full stop"
        assert "_" not in text.replace("EXTRACT(DAY FROM ...)", ""), (
            f"{reason}: still contains a slug"
        )


def test_size_floor_reasons_are_covered():
    """These come from _clears_size_floor, not from an _outcome literal."""

    for reason in (
        "all_sides_below_min_side_rows",
        "table_sizes_unknown",
        "table_sizes_partially_unknown",
        "size_floor_cleared",
    ):
        assert reason in REASON_TEXT


def test_stage_analysis_reason_is_covered():
    """`no_job_stages` is produced by analyze_join_stages, not the detector."""

    assert "no_job_stages" in REASON_TEXT


@pytest.mark.parametrize("reason", sorted(REASON_TEXT))
def test_known_reasons_return_their_mapped_text(reason):
    assert explain(reason) == REASON_TEXT[reason]


def test_unknown_reason_degrades_readably_rather_than_vanishing():
    assert explain("some_new_branch_nobody_mapped") == (
        "Some new branch nobody mapped."
    )


def test_missing_reason_returns_nothing():
    assert explain(None) is None
    assert explain("") is None


def test_review_attaches_the_explanation():
    import inspect

    from tools.bigquery import join_review

    source = inspect.getsource(join_review.review_jobs_for_joins)

    assert '"explanation"' in source
