from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

import numpy as np

from .schemas import CandidateHit


@dataclass(frozen=True, slots=True)
class WeightSelection:
    weight: float
    mrr_at_25: float
    trials: tuple[dict[str, float], ...]


@dataclass(frozen=True, slots=True)
class GateSelection:
    threshold: float
    mrr_at_25: float
    trials: tuple[dict[str, float], ...]


def _clone_hit(hit: CandidateHit, extra_features: Mapping[str, float]) -> CandidateHit:
    return CandidateHit(
        candidate_id=hit.candidate_id,
        smiles=hit.smiles,
        source=hit.source,
        source_rank=hit.source_rank,
        retrieval_score=hit.retrieval_score,
        features={**hit.features, **extra_features},
        references_seen=hit.references_seen,
        metadata=dict(hit.metadata),
    )


def annotate_ranking_context(hits: Sequence[CandidateHit]) -> list[CandidateHit]:
    """Add inference-safe ambiguity and mass-confidence features.

    The anchor formula is the formula of the nearest-mass candidate, never the
    (unknown) target formula.  This distinction is important for E6: the
    resulting same-formula reranker remains usable at competition inference.
    """

    if not hits:
        return []
    formulas = [str(hit.metadata.get("formula") or "") for hit in hits]
    formula_counts = Counter(formulas)
    mass_errors = [float(hit.features.get("mass_error_ppm", 1_000_000.0)) for hit in hits]
    finite_errors = sorted(value for value in mass_errors if math.isfinite(value))
    mass_gap = (
        finite_errors[1] - finite_errors[0]
        if len(finite_errors) >= 2
        else (finite_errors[0] if finite_errors else 0.0)
    )
    anchor_index = min(
        range(len(hits)),
        key=lambda idx: (mass_errors[idx], hits[idx].candidate_id),
    )
    anchor_formula = formulas[anchor_index]
    annotated: list[CandidateHit] = []
    for rank, (hit, formula) in enumerate(zip(hits, formulas, strict=True), start=1):
        annotated.append(
            _clone_hit(
                hit,
                {
                    "baseline_reciprocal_rank": 1.0 / rank,
                    "formula_group_size_goal4": float(formula_counts[formula]) if formula else 0.0,
                    "same_as_mass_anchor_formula": float(bool(formula) and formula == anchor_formula),
                    "mass_confidence_gap_ppm": float(max(0.0, mass_gap)),
                },
            )
        )
    return annotated


def _finite_score(hit: CandidateHit, feature: str, default: float = 0.0) -> float:
    value = float(hit.features.get(feature, default))
    return value if math.isfinite(value) else default


def rank_by_feature(
    hits: Sequence[CandidateHit],
    feature: str,
    *,
    descending: bool = True,
) -> list[str]:
    direction = -1.0 if descending else 1.0
    return [
        hit.candidate_id
        for hit in sorted(
            hits,
            key=lambda item: (direction * _finite_score(item, feature), item.candidate_id),
        )
    ]


def linear_evidence_ranking(
    hits: Sequence[CandidateHit],
    *,
    evidence_feature: str,
    evidence_weight: float,
) -> list[str]:
    """Fuse evidence with mass using within-query ranks.

    Rank normalisation is deliberate: raw cosine, ppm and learned scores have
    unrelated scales.  A zero evidence weight reproduces nearest mass exactly.
    """

    if not hits:
        return []
    mass_order = sorted(
        range(len(hits)),
        key=lambda idx: (
            _finite_score(hits[idx], "mass_error_ppm", 1_000_000.0),
            hits[idx].candidate_id,
        ),
    )
    evidence_order = sorted(
        range(len(hits)),
        key=lambda idx: (-_finite_score(hits[idx], evidence_feature), hits[idx].candidate_id),
    )
    mass_rank = {idx: rank for rank, idx in enumerate(mass_order, start=1)}
    evidence_rank = {idx: rank for rank, idx in enumerate(evidence_order, start=1)}
    normaliser = max(1, len(hits) - 1)
    scores = []
    for idx, hit in enumerate(hits):
        mass_score = 1.0 - (mass_rank[idx] - 1) / normaliser
        evidence_score = 1.0 - (evidence_rank[idx] - 1) / normaliser
        scores.append((mass_score + evidence_weight * evidence_score, hit.candidate_id))
    scores.sort(key=lambda item: (-item[0], item[1]))
    return [candidate_id for _, candidate_id in scores]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    weights: Sequence[float] | None = None,
    constant: float = 60.0,
) -> list[str]:
    if constant <= 0:
        raise ValueError("RRF constant must be positive")
    if weights is None:
        weights = [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("One RRF weight is required per ranking")
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    position = 0
    for ranking, weight in zip(rankings, weights, strict=True):
        if weight < 0 or not math.isfinite(float(weight)):
            raise ValueError("RRF weights must be finite and non-negative")
        seen: set[str] = set()
        for rank, candidate_id in enumerate(ranking, start=1):
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            first_seen.setdefault(candidate_id, position)
            position += 1
            scores[candidate_id] = scores.get(candidate_id, 0.0) + float(weight) / (
                constant + rank
            )
    return sorted(scores, key=lambda candidate_id: (-scores[candidate_id], first_seen[candidate_id], candidate_id))


def same_anchor_formula_reranking(
    mass_ranking: Sequence[str],
    evidence_ranking: Sequence[str],
    formula_by_candidate: Mapping[str, str],
) -> list[str]:
    """Rerank only the mass-top formula group using inference-safe evidence."""

    if not mass_ranking:
        return []
    anchor_formula = str(formula_by_candidate.get(mass_ranking[0], "") or "")
    if not anchor_formula:
        return list(dict.fromkeys(mass_ranking))
    eligible = {
        candidate_id
        for candidate_id in mass_ranking
        if str(formula_by_candidate.get(candidate_id, "") or "") == anchor_formula
    }
    evidence_eligible = [candidate_id for candidate_id in evidence_ranking if candidate_id in eligible]
    iterator = iter(evidence_eligible)
    result: list[str] = []
    seen: set[str] = set()
    for candidate_id in mass_ranking:
        replacement = next(iterator) if candidate_id in eligible else candidate_id
        if replacement not in seen:
            seen.add(replacement)
            result.append(replacement)
    return result


def confidence_aware_ranking(
    baseline: Sequence[str],
    proposed: Sequence[str],
    *,
    confidence: float,
    threshold: float,
) -> list[str]:
    if not math.isfinite(confidence):
        confidence = 0.0
    return list(proposed if confidence >= threshold else baseline)


def _mrr_at_25(truths: Mapping[str, str], rankings: Mapping[str, Sequence[str]]) -> float:
    reciprocal: list[float] = []
    for query_id, truth in truths.items():
        rank = next(
            (index for index, candidate in enumerate(rankings[query_id][:25], start=1) if candidate == truth),
            None,
        )
        reciprocal.append(0.0 if rank is None else 1.0 / rank)
    return float(np.mean(reciprocal)) if reciprocal else 0.0


def tune_evidence_weight(
    truths: Mapping[str, str],
    groups: Mapping[str, Sequence[CandidateHit]],
    *,
    evidence_feature: str,
    weights: Sequence[float] = (0.0, 0.1, 0.25, 0.5, 1.0, 2.0),
) -> WeightSelection:
    trials: list[dict[str, float]] = []
    for weight in weights:
        rankings = {
            query_id: linear_evidence_ranking(
                hits,
                evidence_feature=evidence_feature,
                evidence_weight=float(weight),
            )
            for query_id, hits in groups.items()
        }
        trials.append({"weight": float(weight), "mrr_at_25": _mrr_at_25(truths, rankings)})
    best = max(trials, key=lambda item: (item["mrr_at_25"], -item["weight"]))
    return WeightSelection(
        weight=best["weight"],
        mrr_at_25=best["mrr_at_25"],
        trials=tuple(trials),
    )


def tune_confidence_gate(
    truths: Mapping[str, str],
    baseline: Mapping[str, Sequence[str]],
    proposed: Mapping[str, Sequence[str]],
    confidence: Mapping[str, float],
    *,
    thresholds: Sequence[float] = (0.0, 0.25, 0.5, 0.75, 1.01),
) -> GateSelection:
    trials: list[dict[str, float]] = []
    for threshold in thresholds:
        rankings = {
            query_id: confidence_aware_ranking(
                baseline[query_id],
                proposed[query_id],
                confidence=float(confidence.get(query_id, 0.0)),
                threshold=float(threshold),
            )
            for query_id in truths
        }
        trials.append(
            {"threshold": float(threshold), "mrr_at_25": _mrr_at_25(truths, rankings)}
        )
    # Ties prefer the conservative gate (higher threshold, hence more E0).
    best = max(trials, key=lambda item: (item["mrr_at_25"], item["threshold"]))
    return GateSelection(
        threshold=best["threshold"],
        mrr_at_25=best["mrr_at_25"],
        trials=tuple(trials),
    )
