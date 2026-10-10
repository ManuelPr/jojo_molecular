from __future__ import annotations

from casmi26.goal4_ranking import (
    annotate_ranking_context,
    confidence_aware_ranking,
    linear_evidence_ranking,
    reciprocal_rank_fusion,
    same_anchor_formula_reranking,
    tune_confidence_gate,
    tune_evidence_weight,
)
from casmi26.schemas import CandidateHit


def _hit(candidate_id: str, mass: float, evidence: float, formula: str) -> CandidateHit:
    return CandidateHit(
        candidate_id=candidate_id,
        smiles="C",
        source="fixture",
        source_rank=1,
        retrieval_score=1.0 / (1.0 + mass),
        features={"mass_error_ppm": mass, "evidence": evidence},
        metadata={"formula": formula},
    )


def test_zero_weight_exactly_preserves_nearest_mass() -> None:
    hits = [_hit("b", 2.0, 1.0, "CH4"), _hit("a", 1.0, 0.0, "CH4")]
    assert linear_evidence_ranking(hits, evidence_feature="evidence", evidence_weight=0.0) == [
        "a",
        "b",
    ]


def test_context_uses_mass_anchor_not_truth() -> None:
    annotated = annotate_ranking_context(
        [_hit("wrong", 1.0, 0.0, "C2H6"), _hit("truth", 2.0, 1.0, "CH4")]
    )
    assert annotated[0].features["same_as_mass_anchor_formula"] == 1.0
    assert annotated[1].features["same_as_mass_anchor_formula"] == 0.0


def test_rrf_deduplicates_and_is_deterministic() -> None:
    result = reciprocal_rank_fusion([["a", "b", "b"], ["b", "a", "c"]], constant=1.0)
    assert result[:2] == ["a", "b"]
    assert result.count("b") == 1


def test_same_formula_reranking_only_moves_anchor_formula() -> None:
    mass = ["a", "x", "b", "c"]
    evidence = ["b", "c", "x", "a"]
    formulas = {"a": "F", "b": "F", "c": "F", "x": "X"}
    assert same_anchor_formula_reranking(mass, evidence, formulas) == ["b", "x", "c", "a"]


def test_weight_and_gate_tuning_are_development_only_and_conservative_on_ties() -> None:
    groups = {
        "q": [_hit("wrong", 1.0, 0.0, "F"), _hit("truth", 2.0, 1.0, "F")]
    }
    selected = tune_evidence_weight(
        {"q": "truth"}, groups, evidence_feature="evidence", weights=(0.0, 2.0)
    )
    assert selected.weight == 2.0
    gate = tune_confidence_gate(
        {"q": "truth"},
        {"q": ["wrong", "truth"]},
        {"q": ["truth", "wrong"]},
        {"q": 0.5},
        thresholds=(0.0, 0.5, 1.01),
    )
    assert gate.threshold == 0.5
    assert confidence_aware_ranking(["a"], ["b"], confidence=0.4, threshold=0.5) == ["a"]
