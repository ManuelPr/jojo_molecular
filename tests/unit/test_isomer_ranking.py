from __future__ import annotations

import numpy as np
import pytest

from casmi26.isomer_ranking import (
    FP_FEATURE_NAMES,
    IsomerAwareRanker,
    annotate_fingerprint_features,
    fingerprint_compatibility,
    mine_hard_negatives,
)
from casmi26.mass_retrieval import StructureCandidate
from casmi26.schemas import CandidateHit


def _hit(candidate: StructureCandidate, score: float) -> CandidateHit:
    return CandidateHit(
        candidate_id=candidate.candidate_id,
        smiles=candidate.smiles,
        source="test",
        source_rank=1,
        retrieval_score=score,
        features={"mass_error_ppm": 1.0 - score, "retrieval_score": score},
        metadata={"formula": candidate.formula, "exact_mass": candidate.exact_mass},
    )


def test_fingerprint_compatibility_prefers_matching_bits() -> None:
    probability = np.asarray([0.95, 0.05, 0.9, 0.1])
    match = fingerprint_compatibility(probability, np.asarray([1, 0, 1, 0]))
    mismatch = fingerprint_compatibility(probability, np.asarray([0, 1, 0, 1]))
    assert match["fingerprint_log_likelihood"] > mismatch["fingerprint_log_likelihood"]
    assert match["fingerprint_soft_jaccard"] > mismatch["fingerprint_soft_jaccard"]


def test_annotation_uses_only_prediction_and_candidate_context() -> None:
    candidates = [
        StructureCandidate("a", "CCO", 46.0419, "C2H6O"),
        StructureCandidate("b", "COC", 46.0419, "C2H6O"),
    ]
    hits = [_hit(candidate, 0.5) for candidate in candidates]
    annotated = annotate_fingerprint_features(
        hits,
        np.asarray([0.9, 0.1]),
        {"a": np.asarray([1, 0]), "b": np.asarray([0, 1])},
    )
    assert annotated[0].features["formula_group_size"] == 2.0
    assert annotated[0].features["exact_mass_group_size"] == 2.0
    assert annotated[0].features["fingerprint_log_likelihood"] > annotated[1].features["fingerprint_log_likelihood"]
    assert "fingerprint_log_likelihood" not in hits[0].features


def test_hard_negative_mining_prioritizes_same_formula_and_excludes_truth() -> None:
    target = StructureCandidate("truth", "CCO", 46.0419, "C2H6O")
    candidates = [
        target,
        StructureCandidate("isomer", "COC", 46.0419, "C2H6O"),
        StructureCandidate("near", "CCN", 45.0578, "C2H7N"),
        StructureCandidate("far", "CCCCCCCC", 114.1409, "C8H18"),
    ]
    selected, summary = mine_hard_negatives(
        target,
        candidates,
        baseline_ranks={"near": 1},
        max_negatives=3,
    )
    assert all(item.candidate_id != "truth" for item in selected)
    assert selected[0].candidate_id == "isomer"
    assert selected[0].tier >= 2
    assert summary.same_formula_count == 1


def test_isomer_aware_ranker_fits_and_requires_complete_features() -> None:
    candidates = [
        StructureCandidate("a", "CCO", 46.0419, "C2H6O"),
        StructureCandidate("b", "COC", 46.0419, "C2H6O"),
    ]
    groups = {}
    truths = {}
    for idx in range(8):
        truth = candidates[idx % 2]
        other = candidates[(idx + 1) % 2]
        groups[str(idx)] = [_hit(truth, 0.9), _hit(other, 0.1)]
        truths[str(idx)] = truth.candidate_id
    ranker = IsomerAwareRanker(("retrieval_score",), random_state=7)
    summary = ranker.fit(groups, truths)
    assert summary["query_count"] == 8
    assert ranker.rank(groups["0"])[0].candidate_id == "a"
    with pytest.raises(ValueError, match="Missing ranking features"):
        IsomerAwareRanker(FP_FEATURE_NAMES).fit(groups, truths)
