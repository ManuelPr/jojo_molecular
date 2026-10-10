from __future__ import annotations

import json

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from casmi26.benchmark_audit import (
    assert_realistic_candidate_integrity,
    audit_candidate_pools,
    calibration_diagnostics,
    candidate_prior_diagnostics,
    construct_candidate_catalog,
    construct_candidate_pool,
    feature_drift_diagnostics,
    model_importance_diagnostics,
    rank_shift_diagnostics,
    ranking_breakdowns,
)
from casmi26.schemas import CandidateHit


def test_realistic_catalog_does_not_prioritize_or_add_adversarial_targets() -> None:
    source = ["A", "B", "C", "D"]
    trace = construct_candidate_catalog(
        source,
        mode="realistic",
        max_size=2,
        controlled_target_ids=["D", "NOT_IN_SOURCE"],
    )

    assert trace.candidate_ids == ("A", "B")
    assert trace.target_ids_consulted == ()
    assert trace.prioritized_target_ids == ()
    assert "D" not in trace.candidate_ids
    assert "NOT_IN_SOURCE" not in trace.candidate_ids


def test_realistic_pool_cannot_add_target_even_when_passed_explicitly() -> None:
    trace = construct_candidate_pool(
        "q",
        ["A", "B"],
        mode="realistic",
        max_size=2,
        controlled_target_id="SECRET_TARGET",
    )

    assert trace.final_candidate_ids == ("A", "B")
    assert not trace.target_was_consulted
    assert not trace.target_was_injected
    assert "SECRET_TARGET" not in trace.final_candidate_ids


def test_controlled_construction_is_target_aware_and_fully_traced() -> None:
    catalog = construct_candidate_catalog(
        ["A", "B", "TARGET"],
        mode="controlled",
        max_size=2,
        controlled_target_ids=["TARGET"],
    )
    pool = construct_candidate_pool(
        "q",
        ["A", "B"],
        mode="controlled",
        max_size=2,
        controlled_target_id="TARGET",
    )

    assert catalog.candidate_ids == ("TARGET", "A")
    assert catalog.prioritized_target_ids == ("TARGET",)
    assert pool.final_candidate_ids == ("A", "TARGET")
    assert pool.target_was_injected


def test_candidate_audit_separates_catalog_pool_and_top25_recall() -> None:
    pool_q2 = [f"D{index}" for index in range(30)] + ["T2"]
    report = audit_candidate_pools(
        {"q1": "T1", "q2": "T2", "q3": "T3"},
        ["T1", "T2", "A", "B"],
        {"q1": ["ISO", "MASS", "T1"], "q2": pool_q2, "q3": ["A", "B"]},
        mode="realistic",
        candidate_formula_by_id={"ISO": "C2H6O", "T1": "C2H6O"},
        truth_formula_by_query={"q1": "C2H6O", "q2": "X", "q3": "Y"},
        candidate_exact_mass_by_id={"MASS": 46.0419, "T1": 46.0419},
        truth_exact_mass_by_query={"q1": 46.0419},
    )

    audit = report.summary
    assert audit.catalog_recall == pytest.approx(2 / 3)
    assert audit.pool_recall == pytest.approx(2 / 3)
    assert audit.recall_at_25 == pytest.approx(1 / 3)
    assert audit.median_pool_size == 3.0
    assert audit.median_same_formula_competitors == 0.0
    assert audit.median_exact_mass_competitors == 0.0
    q1 = next(row for row in report.per_query if row["query_id"] == "q1")
    assert q1["same_formula_competitors"] == 1
    assert q1["exact_mass_competitors"] == 1
    assert json.loads(json.dumps(report.to_dict()))["summary"]["pool_recall"] == pytest.approx(2 / 3)
    assert_realistic_candidate_integrity(report)


def test_audit_detects_hidden_pool_injection_and_fails_closed_in_realistic_mode() -> None:
    forged_trace = construct_candidate_pool(
        "q", ["A", "B"], mode="controlled", controlled_target_id="TARGET"
    )
    report = audit_candidate_pools(
        {"q": "TARGET"},
        ["TARGET", "A", "B"],
        {"q": forged_trace.final_candidate_ids},
        mode="realistic",
        pool_traces={"q": forged_trace},
    )

    assert report.summary.explicit_target_injection_count == 1
    assert any("trace mode" in violation for violation in report.violations)
    assert any("target evidence" in violation for violation in report.violations)
    with pytest.raises(AssertionError, match="query q"):
        assert_realistic_candidate_integrity(report)


def test_audit_counts_target_informed_catalog_construction() -> None:
    trace = construct_candidate_catalog(
        ["A", "B", "TARGET"],
        mode="controlled",
        max_size=1,
        controlled_target_ids=["TARGET"],
    )
    report = audit_candidate_pools(
        {"q": "TARGET"},
        trace.candidate_ids,
        {"q": ["TARGET"]},
        mode="controlled",
        catalog_trace=trace,
    )

    assert report.summary.catalog_recall == 1.0
    assert report.summary.explicit_target_injection_count == 1
    assert report.per_query[0]["injection_reasons"] == [
        "target_informed_catalog_selection"
    ]


def test_rank_shift_diagnostics_reports_improvements_and_regressions() -> None:
    diagnostics = rank_shift_diagnostics(
        {"q1": "T1", "q2": "T2", "q3": "T3"},
        {
            "mass": {
                "q1": ["A", "T1"],
                "q2": ["T2"],
                "q3": ["T3"],
            },
            "ranker": {
                "q1": ["T1", "A"],
                "q2": ["A", "T2"],
                "q3": ["T3"],
            },
        },
        baseline_method="mass",
    )

    comparison = diagnostics["comparisons"]["ranker"]
    assert comparison["improved_count"] == 1
    assert comparison["worsened_count"] == 1
    assert comparison["unchanged_count"] == 1
    assert comparison["mean_rank_shift"] == 0.0


def test_candidate_prior_diagnostics_exposes_source_shortcuts() -> None:
    groups = {
        "q": [
            CandidateHit("T", "C", "mass", 1, 0.9, {}),
            CandidateHit("N", "CC", "spectral", 8, 0.2, {}),
        ]
    }
    report = candidate_prior_diagnostics(groups, {"q": "T"})

    assert report["candidate_count"] == 2
    assert report["by_source"]["mass"]["positive_rate"] == 1.0
    assert report["by_source_rank_bin"]["6-25"]["positive_rate"] == 0.0


def test_feature_drift_handles_missing_values_and_flags_shift() -> None:
    report = feature_drift_diagnostics(
        {"stable": [0.0, 1.0, 2.0, np.nan], "shifted": [0.0, 0.0, 0.1, 0.2]},
        {"stable": [0.0, 1.0, 2.0], "shifted": [5.0, 5.1, 5.2]},
        n_bins=3,
    )

    assert report["features"]["stable"]["train_missing_rate"] == 0.25
    assert report["features"]["shifted"]["drift_flag"]
    json.dumps(report)


def test_model_and_permutation_importance_are_serializable() -> None:
    features = np.asarray(
        [[0.0, 0.0], [0.1, 1.0], [0.9, 0.0], [1.0, 1.0], [0.8, 0.2], [0.2, 0.8]]
    )
    labels = np.asarray([0, 0, 1, 1, 1, 0])
    model = LogisticRegression(random_state=1).fit(features, labels)
    report = model_importance_diagnostics(
        model,
        ["signal", "noise"],
        validation_features=features,
        validation_labels=labels,
        n_repeats=4,
        seed=4,
    )

    assert report["native_kind"] == "absolute_coef"
    assert report["native"][0]["feature"] == "signal"
    assert report["permutation"] is not None
    assert report["permutation"][0]["feature"] == "signal"
    json.dumps(report)


def test_calibration_metrics_and_bins() -> None:
    report = calibration_diagnostics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], n_bins=5)

    assert report["sample_count"] == 4
    assert report["positive_count"] == 2
    assert report["brier_score"] == pytest.approx(0.025)
    assert report["expected_calibration_error"] == pytest.approx(0.15)
    assert sum(item["count"] for item in report["bins"]) == 4


def test_ranking_breakdowns_cover_formula_isomer_and_pool_size() -> None:
    report = ranking_breakdowns(
        {"q1": "T1", "q2": "T2"},
        {"q1": ["I1", "T1"], "q2": [*[f"D{x}" for x in range(30)], "T2"]},
        {"q1": ["I1", "T1"], "q2": ["T2"]},
        candidate_formula_by_id={"I1": "C2H6O", "T1": "C2H6O"},
        truth_formula_by_query={"q1": "C2H6O", "q2": "C10H20"},
    )

    assert report["formula"]["C2H6O"]["mrr_at_cutoff"] == 0.5
    assert report["isomer_count"]["1"]["query_count"] == 1
    assert report["pool_size"]["25-99"]["query_count"] == 1
    json.dumps(report)
