from __future__ import annotations

import pytest

from casmi26.recovery_audit import (
    audit_prediction_identities,
    summarize_candidate_tier,
    summarize_neutral_mass_residuals,
)


def test_candidate_tier_separates_catalog_and_ranking_recall() -> None:
    truth = {"q1": "A", "q2": "B", "q3": "C"}
    rankings = {
        "q1": ["A", "X"],
        "q2": ["X", "B"],
        "q3": ["X"],
    }
    result = summarize_candidate_tier(
        truth,
        rankings,
        catalog_identities={"A", "B", "X"},
        formula_by_candidate={"A": "F1", "B": "F1", "X": "F1"},
    )
    assert result["catalog_recall"] == pytest.approx(2 / 3)
    assert result["candidate_recall_at_25"] == pytest.approx(2 / 3)
    assert result["mrr_at_25"] == pytest.approx(0.5)
    assert result["conditional_mrr_at_25"] == pytest.approx(0.75)
    assert result["same_formula_competitors"]["median"] == 2.0


def test_neutral_mass_residuals_are_grouped_by_adduct() -> None:
    result = summarize_neutral_mass_residuals(
        {"q1": [100.0, 100.0001], "q2": [200.0]},
        {"q1": 100.0, "q2": 200.0, "missing": 300.0},
        {"q1": ["[M+H]+", "[M+Na]+"], "q2": ["[M-H]-"]},
    )
    assert result["missing_query_count"] == 1
    assert result["ppm_error"]["count"] == 3
    assert result["ppm_error_by_adduct"]["[M+Na]+"]["max"] == pytest.approx(1.0)


def test_prediction_audit_detects_default_rows_and_mass_error() -> None:
    result = audit_prediction_identities(
        ["q1", "q2"],
        {"q1": ["A", "B"], "q2": ["A", "B"]},
        catalog_identities={"A", "B"},
        query_mass_by_id={"q1": 100.0, "q2": 101.0},
        candidate_mass_by_id={"A": 100.0, "B": 100.0001},
    )
    assert result["missing_query_count"] == 0
    assert result["unique_ranking_count"] == 1
    assert result["most_common_ranking_fraction"] == 1.0
    assert result["catalog_candidate_fraction"] == 1.0
    assert result["first_candidate_mass_error_ppm"]["max"] > 9_000
