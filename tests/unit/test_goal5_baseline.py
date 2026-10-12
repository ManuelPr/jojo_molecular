from __future__ import annotations

from copy import deepcopy

import pytest

from casmi26.goal5_baseline import assert_e6_replication, frozen_e6_signature


def _results() -> dict:
    evaluation = {
        "E0": {
            "metrics": {
                "mrr_at_25": 0.3,
                "hit_at_1": 0.2,
                "hit_at_5": 0.4,
                "hit_at_10": 0.5,
                "candidate_recall_at": {"25": 0.8, "100": 1.0, "1000": 1.0},
            }
        },
        "E6": {
            "metrics": {
                "mrr_at_25": 0.4,
                "hit_at_1": 0.3,
                "hit_at_5": 0.5,
                "hit_at_10": 0.6,
                "candidate_recall_at": {"25": 0.8, "100": 1.0, "1000": 1.0},
            }
        },
    }
    return {
        "manifest_hash": "manifest",
        "canonical_catalog": {
            "selected_before_validation": 10,
            "valid_structure_count": 9,
            "identity_mismatch_count": 1,
        },
        "selected_by_model_selection": "E6",
        "model_selection": {
            "E3": {
                "selected_aggregation_feature": "analog_score",
                "selected_weight": 0.5,
            }
        },
        "evaluations": {
            "all_validation": deepcopy(evaluation),
            "model_selection": deepcopy(evaluation),
            "final_evaluation": deepcopy(evaluation),
        },
    }


def test_frozen_signature_ignores_runtime_but_checks_all_metrics() -> None:
    reference = _results()
    replicate = deepcopy(reference)
    reference["elapsed_seconds"] = 1.0
    replicate["elapsed_seconds"] = 2.0
    assert frozen_e6_signature(reference) == frozen_e6_signature(replicate)
    assert assert_e6_replication(reference, replicate)["replicated"] is True


def test_replication_fails_on_selection_or_metric_drift() -> None:
    reference = _results()
    replicate = deepcopy(reference)
    replicate["evaluations"]["final_evaluation"]["E6"]["metrics"][
        "mrr_at_25"
    ] = 0.39
    with pytest.raises(AssertionError, match="metrics"):
        assert_e6_replication(reference, replicate)
