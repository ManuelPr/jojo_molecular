from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
import re
from typing import Any

import numpy as np

from .validation_contracts import RetrievalDiagnostics


REQUIRED_RECALL_CUTOFFS = (25, 100, 1000)
DEFAULT_BREAKDOWN_FIELDS = (
    "mass_bin",
    "formula",
    "adduct",
    "instrument_type",
    "source",
)
MISSING_GROUP = "<missing>"
_INCHIKEY_RE = re.compile(r"^[A-Z]{14}(?:-[A-Z]{10}-[A-Z])?$")


@dataclass(frozen=True, slots=True)
class _QueryObservation:
    query_id: str
    truth_key: str
    pool_rank: int | None
    ranked_rank: int | None
    same_formula_error: bool


def _normalise_identity(value: Any) -> str | None:
    if value is None:
        return None
    identity = str(value).strip()
    if not identity:
        return None
    # Accept either the competition key or a full InChIKey. Arbitrary IDs are
    # retained so synthetic fixtures and pre-normalised database IDs work too.
    if _INCHIKEY_RE.fullmatch(identity):
        return identity[:14]
    return identity


def _candidate_identity(
    candidate_id: Any,
    candidate_identity_keys: Mapping[str, str] | None,
) -> str | None:
    raw_id = str(candidate_id)
    identity = (
        candidate_identity_keys.get(raw_id, raw_id)
        if candidate_identity_keys is not None
        else raw_id
    )
    return _normalise_identity(identity)


def _deduplicate_candidates(
    candidates: Sequence[str],
    candidate_identity_keys: Mapping[str, str] | None,
) -> tuple[tuple[str, str], ...]:
    """Return ``(original_id, identity_key)`` pairs, preserving first order."""

    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate_id = str(candidate)
        identity = _candidate_identity(candidate_id, candidate_identity_keys)
        if identity is None or identity in seen:
            continue
        seen.add(identity)
        result.append((candidate_id, identity))
    return tuple(result)


def _first_rank(candidates: Sequence[tuple[str, str]], truth_key: str) -> int | None:
    return next(
        (rank for rank, (_, identity) in enumerate(candidates, start=1) if identity == truth_key),
        None,
    )


def _formula_for_candidate(
    candidate_id: str,
    identity_key: str,
    candidate_formula_by_id: Mapping[str, str] | None,
) -> str | None:
    if candidate_formula_by_id is None:
        return None
    value = candidate_formula_by_id.get(candidate_id)
    if value is None:
        value = candidate_formula_by_id.get(identity_key)
    if value is None:
        return None
    formula = str(value).strip()
    return formula or None


def _same_formula_error(
    *,
    truth_key: str,
    truth_formula: str | None,
    ranked_candidates: Sequence[tuple[str, str]],
    ranked_rank: int | None,
    candidate_formula_by_id: Mapping[str, str] | None,
) -> bool:
    """Identify a same-formula competitor ranked ahead of the truth.

    This is an isomer-confusion proxy, not proof that two structures are
    constitutional isomers. A query counts once when at least one incorrect
    candidate before the correct candidate has the same molecular formula. If
    the truth is absent from the top 25, all top-25 candidates are inspected.
    """

    if not truth_formula or ranked_rank == 1:
        return False
    normalised_formula = truth_formula.strip()
    if not normalised_formula:
        return False
    stop = min(25, (ranked_rank - 1) if ranked_rank is not None else 25)
    for candidate_id, identity_key in ranked_candidates[:stop]:
        if identity_key == truth_key:
            continue
        if (
            _formula_for_candidate(candidate_id, identity_key, candidate_formula_by_id)
            == normalised_formula
        ):
            return True
    return False


def _build_observations(
    truth_keys: Mapping[str, str],
    candidate_pools: Mapping[str, Sequence[str]],
    ranked_candidates: Mapping[str, Sequence[str]],
    *,
    candidate_identity_keys: Mapping[str, str] | None,
    candidate_formula_by_id: Mapping[str, str] | None,
    truth_formula_by_query: Mapping[str, str] | None,
    strict_ranked_subset: bool,
) -> tuple[_QueryObservation, ...]:
    observations: list[_QueryObservation] = []
    for raw_query_id, raw_truth_key in truth_keys.items():
        query_id = str(raw_query_id)
        truth_key = _normalise_identity(raw_truth_key)
        if truth_key is None:
            raise ValueError(f"Query {query_id!r} has an empty truth identity key")

        pool = _deduplicate_candidates(
            candidate_pools.get(raw_query_id, candidate_pools.get(query_id, ())),
            candidate_identity_keys,
        )
        ranking = _deduplicate_candidates(
            ranked_candidates.get(raw_query_id, ranked_candidates.get(query_id, ())),
            candidate_identity_keys,
        )
        if strict_ranked_subset:
            pool_keys = {identity for _, identity in pool}
            outside_pool = [
                identity for _, identity in ranking if identity not in pool_keys
            ]
            if outside_pool:
                preview = ", ".join(outside_pool[:3])
                raise ValueError(
                    f"Ranked candidates for query {query_id!r} are outside its pool: {preview}"
                )

        pool_rank = _first_rank(pool, truth_key)
        ranked_rank = _first_rank(ranking, truth_key)
        truth_formula = None
        if truth_formula_by_query is not None:
            value = truth_formula_by_query.get(raw_query_id)
            if value is None:
                value = truth_formula_by_query.get(query_id)
            truth_formula = None if value is None else str(value)
        observations.append(
            _QueryObservation(
                query_id=query_id,
                truth_key=truth_key,
                pool_rank=pool_rank,
                ranked_rank=ranked_rank,
                same_formula_error=_same_formula_error(
                    truth_key=truth_key,
                    truth_formula=truth_formula,
                    ranked_candidates=ranking,
                    ranked_rank=ranked_rank,
                    candidate_formula_by_id=candidate_formula_by_id,
                ),
            )
        )
    return tuple(observations)


def _safe_mean(values: Sequence[float] | np.ndarray) -> float:
    return float(np.mean(values)) if len(values) else 0.0


def _metric_values(observations: Sequence[_QueryObservation]) -> dict[str, float | int]:
    n_queries = len(observations)
    if not n_queries:
        return {
            "query_count": 0,
            "candidate_recall_at_25": 0.0,
            "candidate_recall_at_100": 0.0,
            "candidate_recall_at_1000": 0.0,
            "pool_recall": 0.0,
            "mrr_at_25": 0.0,
            "hit_at_1": 0.0,
            "hit_at_5": 0.0,
            "hit_at_10": 0.0,
            "conditional_mrr_at_25": 0.0,
            "oracle_mrr_at_25": 0.0,
            "recovered_query_count": 0,
            "missing_query_count": 0,
            "same_formula_error_count": 0,
        }

    pool_ranks = np.asarray(
        [0 if item.pool_rank is None else item.pool_rank for item in observations],
        dtype=np.int64,
    )
    ranked_ranks = np.asarray(
        [0 if item.ranked_rank is None else item.ranked_rank for item in observations],
        dtype=np.int64,
    )
    recovered = pool_ranks > 0
    ranked_in_25 = (ranked_ranks > 0) & (ranked_ranks <= 25)
    reciprocal = np.where(ranked_in_25, 1.0 / np.maximum(ranked_ranks, 1), 0.0)
    recovered_count = int(recovered.sum())
    conditional_mrr = (
        float(reciprocal[recovered].mean()) if recovered_count else 0.0
    )
    values: dict[str, float | int] = {
        "query_count": n_queries,
        "pool_recall": _safe_mean(recovered.astype(float)),
        "mrr_at_25": _safe_mean(reciprocal),
        "hit_at_1": _safe_mean((ranked_ranks == 1).astype(float)),
        "hit_at_5": _safe_mean(
            ((ranked_ranks > 0) & (ranked_ranks <= 5)).astype(float)
        ),
        "hit_at_10": _safe_mean(
            ((ranked_ranks > 0) & (ranked_ranks <= 10)).astype(float)
        ),
        "conditional_mrr_at_25": conditional_mrr,
        # A perfect ranker can place a recovered truth first, but cannot recover
        # a truth absent from the full pool. Thus this oracle equals pool recall.
        "oracle_mrr_at_25": _safe_mean(recovered.astype(float)),
        "recovered_query_count": recovered_count,
        "missing_query_count": n_queries - recovered_count,
        "same_formula_error_count": sum(item.same_formula_error for item in observations),
    }
    for cutoff in REQUIRED_RECALL_CUTOFFS:
        values[f"candidate_recall_at_{cutoff}"] = _safe_mean(
            ((pool_ranks > 0) & (pool_ranks <= cutoff)).astype(float)
        )
    return values


def _format_bin_edge(value: float) -> str:
    return f"{value:g}"


def _mass_bin(value: Any, width: float) -> str | None:
    try:
        mass = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(mass):
        return None
    lower = math.floor(mass / width) * width
    upper = lower + width
    return f"[{_format_bin_edge(lower)},{_format_bin_edge(upper)})"


def _group_label(value: Any) -> str:
    if value is None or value == "":
        return MISSING_GROUP
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _metadata_for_query(
    query_metadata: Mapping[str, Mapping[str, Any]] | None,
    query_id: str,
) -> Mapping[str, Any]:
    if query_metadata is None:
        return {}
    return query_metadata.get(query_id, {})


def _breakdown_value(
    *,
    field: str,
    query_id: str,
    metadata: Mapping[str, Any],
    truth_formula_by_query: Mapping[str, str] | None,
    mass_bin_width: float,
) -> tuple[bool, str]:
    if field == "mass_bin":
        if "mass_bin" in metadata:
            return True, _group_label(metadata.get("mass_bin"))
        for mass_field in ("neutral_mass", "mass"):
            if mass_field in metadata:
                return True, _group_label(_mass_bin(metadata.get(mass_field), mass_bin_width))
        return False, MISSING_GROUP
    if field == "formula" and "formula" not in metadata:
        if truth_formula_by_query is not None and query_id in truth_formula_by_query:
            return True, _group_label(truth_formula_by_query[query_id])
        return False, MISSING_GROUP
    if field in metadata:
        return True, _group_label(metadata.get(field))
    return False, MISSING_GROUP


def _build_breakdowns(
    observations: Sequence[_QueryObservation],
    *,
    query_metadata: Mapping[str, Mapping[str, Any]] | None,
    truth_formula_by_query: Mapping[str, str] | None,
    breakdown_fields: Sequence[str],
    mass_bin_width: float,
) -> dict[str, dict[str, dict[str, float | int]]]:
    breakdowns: dict[str, dict[str, dict[str, float | int]]] = {}
    for field in breakdown_fields:
        groups: dict[str, list[_QueryObservation]] = defaultdict(list)
        field_observed = False
        for observation in observations:
            metadata = _metadata_for_query(query_metadata, observation.query_id)
            observed, label = _breakdown_value(
                field=field,
                query_id=observation.query_id,
                metadata=metadata,
                truth_formula_by_query=truth_formula_by_query,
                mass_bin_width=mass_bin_width,
            )
            field_observed = field_observed or observed
            groups[label].append(observation)
        if not field_observed:
            breakdowns[field] = {}
            continue
        breakdowns[field] = {
            label: _metric_values(group) for label, group in sorted(groups.items())
        }
    return breakdowns


def evaluate_retrieval_diagnostics(
    truth_keys: Mapping[str, str],
    candidate_pools: Mapping[str, Sequence[str]],
    ranked_candidates: Mapping[str, Sequence[str]],
    *,
    candidate_identity_keys: Mapping[str, str] | None = None,
    candidate_formula_by_id: Mapping[str, str] | None = None,
    truth_formula_by_query: Mapping[str, str] | None = None,
    query_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    breakdown_fields: Sequence[str] = DEFAULT_BREAKDOWN_FIELDS,
    mass_bin_width: float = 200.0,
    strict_ranked_subset: bool = True,
) -> RetrievalDiagnostics:
    """Measure candidate generation separately from candidate ranking.

    ``truth_keys`` contains competition-normalised InChIKey14 identities.
    Candidate sequences contain ordered candidate IDs. When those IDs are not
    already identity keys, ``candidate_identity_keys`` maps them to InChIKey14;
    aliases resolving to the same identity are deduplicated at their first
    occurrence in both the pool and ranking.

    Candidate recall is measured on the ordered, deduplicated pre-ranking pool.
    Conditional MRR@25 is averaged only over queries whose truth occurs anywhere
    in that full pool; an available truth that the ranker misses still contributes
    zero. Oracle MRR@25 assumes a perfect ranker over the same pool, so it equals
    full-pool recall and makes the candidate-generation ceiling explicit.
    """

    if not math.isfinite(mass_bin_width) or mass_bin_width <= 0:
        raise ValueError("mass_bin_width must be a finite positive number")
    observations = _build_observations(
        truth_keys,
        candidate_pools,
        ranked_candidates,
        candidate_identity_keys=candidate_identity_keys,
        candidate_formula_by_id=candidate_formula_by_id,
        truth_formula_by_query=truth_formula_by_query,
        strict_ranked_subset=strict_ranked_subset,
    )
    values = _metric_values(observations)
    return RetrievalDiagnostics(
        query_count=int(values["query_count"]),
        candidate_recall_at={
            cutoff: float(values[f"candidate_recall_at_{cutoff}"])
            for cutoff in REQUIRED_RECALL_CUTOFFS
        },
        pool_recall=float(values["pool_recall"]),
        mrr_at_25=float(values["mrr_at_25"]),
        hit_at_1=float(values["hit_at_1"]),
        hit_at_5=float(values["hit_at_5"]),
        hit_at_10=float(values["hit_at_10"]),
        conditional_mrr_at_25=float(values["conditional_mrr_at_25"]),
        oracle_mrr_at_25=float(values["oracle_mrr_at_25"]),
        recovered_query_count=int(values["recovered_query_count"]),
        missing_query_ids=tuple(
            item.query_id for item in observations if item.pool_rank is None
        ),
        same_formula_error_count=int(values["same_formula_error_count"]),
        breakdowns=_build_breakdowns(
            observations,
            query_metadata=query_metadata,
            truth_formula_by_query=truth_formula_by_query,
            breakdown_fields=breakdown_fields,
            mass_bin_width=mass_bin_width,
        ),
    )


def _per_query_arrays(
    observations: Sequence[_QueryObservation],
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    pool_ranks = np.asarray(
        [0 if item.pool_rank is None else item.pool_rank for item in observations],
        dtype=np.int64,
    )
    ranked_ranks = np.asarray(
        [0 if item.ranked_rank is None else item.ranked_rank for item in observations],
        dtype=np.int64,
    )
    recovered = (pool_ranks > 0).astype(float)
    ranked_in_25 = (ranked_ranks > 0) & (ranked_ranks <= 25)
    reciprocal = np.where(ranked_in_25, 1.0 / np.maximum(ranked_ranks, 1), 0.0)
    arrays = {
        "candidate_recall_at_25": ((pool_ranks > 0) & (pool_ranks <= 25)).astype(float),
        "candidate_recall_at_100": ((pool_ranks > 0) & (pool_ranks <= 100)).astype(float),
        "candidate_recall_at_1000": ((pool_ranks > 0) & (pool_ranks <= 1000)).astype(float),
        "pool_recall": recovered,
        "mrr_at_25": reciprocal,
        "hit_at_1": (ranked_ranks == 1).astype(float),
        "hit_at_5": ((ranked_ranks > 0) & (ranked_ranks <= 5)).astype(float),
        "hit_at_10": ((ranked_ranks > 0) & (ranked_ranks <= 10)).astype(float),
        "oracle_mrr_at_25": recovered,
        "same_formula_error_rate": np.asarray(
            [float(item.same_formula_error) for item in observations]
        ),
    }
    return arrays, recovered.astype(bool)


def bootstrap_retrieval_confidence_intervals(
    truth_keys: Mapping[str, str],
    candidate_pools: Mapping[str, Sequence[str]],
    ranked_candidates: Mapping[str, Sequence[str]],
    *,
    candidate_identity_keys: Mapping[str, str] | None = None,
    candidate_formula_by_id: Mapping[str, str] | None = None,
    truth_formula_by_query: Mapping[str, str] | None = None,
    strict_ranked_subset: bool = True,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 2026,
) -> dict[str, dict[str, float | int]]:
    """Return deterministic molecule-level percentile bootstrap intervals.

    Queries (the competition prediction unit) are resampled with replacement.
    Conditional MRR is recomputed on recovered queries within each resample;
    resamples containing no recovered target are excluded for that metric.
    """

    if n_bootstrap <= 0:
        raise ValueError("n_bootstrap must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between zero and one")
    observations = _build_observations(
        truth_keys,
        candidate_pools,
        ranked_candidates,
        candidate_identity_keys=candidate_identity_keys,
        candidate_formula_by_id=candidate_formula_by_id,
        truth_formula_by_query=truth_formula_by_query,
        strict_ranked_subset=strict_ranked_subset,
    )
    arrays, recovered = _per_query_arrays(observations)
    n_queries = len(observations)
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = {name: [] for name in arrays}
    samples["conditional_mrr_at_25"] = []
    reciprocal = arrays["mrr_at_25"]

    if n_queries:
        for _ in range(n_bootstrap):
            indices = rng.integers(0, n_queries, size=n_queries)
            for name, values in arrays.items():
                samples[name].append(float(values[indices].mean()))
            recovered_sample = recovered[indices]
            if recovered_sample.any():
                samples["conditional_mrr_at_25"].append(
                    float(reciprocal[indices][recovered_sample].mean())
                )

    alpha = (1.0 - confidence) / 2.0
    result: dict[str, dict[str, float | int]] = {}
    for name, values in samples.items():
        if name == "conditional_mrr_at_25":
            point = float(reciprocal[recovered].mean()) if recovered.any() else 0.0
        else:
            point = float(arrays[name].mean()) if n_queries else 0.0
        if values:
            lower, upper = np.quantile(values, [alpha, 1.0 - alpha])
        else:
            lower = upper = point
        result[name] = {
            "point": point,
            "lower": float(lower),
            "upper": float(upper),
            "confidence": confidence,
            "n_bootstrap": n_bootstrap,
            "effective_bootstrap": len(values),
            "seed": seed,
        }
    return result


def bootstrap_paired_ranking_differences(
    truth_keys: Mapping[str, str],
    candidate_pools: Mapping[str, Sequence[str]],
    baseline_rankings: Mapping[str, Sequence[str]],
    challenger_rankings: Mapping[str, Sequence[str]],
    *,
    candidate_identity_keys: Mapping[str, str] | None = None,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 2026,
) -> dict[str, dict[str, float | int]]:
    """Paired molecule-level CI for challenger minus baseline ranking metrics."""

    if n_bootstrap <= 0:
        raise ValueError("n_bootstrap must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between zero and one")
    baseline = _build_observations(
        truth_keys,
        candidate_pools,
        baseline_rankings,
        candidate_identity_keys=candidate_identity_keys,
        candidate_formula_by_id=None,
        truth_formula_by_query=None,
        strict_ranked_subset=True,
    )
    challenger = _build_observations(
        truth_keys,
        candidate_pools,
        challenger_rankings,
        candidate_identity_keys=candidate_identity_keys,
        candidate_formula_by_id=None,
        truth_formula_by_query=None,
        strict_ranked_subset=True,
    )
    if [item.query_id for item in baseline] != [item.query_id for item in challenger]:
        raise ValueError("Paired rankings must contain the same ordered query set")
    baseline_arrays, recovered = _per_query_arrays(baseline)
    challenger_arrays, challenger_recovered = _per_query_arrays(challenger)
    if not np.array_equal(recovered, challenger_recovered):
        raise AssertionError("Candidate pool recovery changed between paired rankings")

    metric_names = ("mrr_at_25", "hit_at_1", "hit_at_5", "hit_at_10")
    differences = {
        name: challenger_arrays[name] - baseline_arrays[name] for name in metric_names
    }
    differences["conditional_mrr_at_25"] = differences["mrr_at_25"][recovered]
    rng = np.random.default_rng(seed)
    n_queries = len(baseline)
    samples: dict[str, list[float]] = {name: [] for name in differences}
    if n_queries:
        for _ in range(n_bootstrap):
            indices = rng.integers(0, n_queries, size=n_queries)
            for name in metric_names:
                samples[name].append(float(differences[name][indices].mean()))
            recovered_indices = indices[recovered[indices]]
            if recovered_indices.size:
                samples["conditional_mrr_at_25"].append(
                    float(differences["mrr_at_25"][recovered_indices].mean())
                )

    alpha = (1.0 - confidence) / 2.0
    result: dict[str, dict[str, float | int]] = {}
    for name, values in samples.items():
        point = float(differences[name].mean()) if len(differences[name]) else 0.0
        if values:
            lower, upper = np.quantile(values, [alpha, 1.0 - alpha])
        else:
            lower = upper = point
        result[name] = {
            "point": point,
            "lower": float(lower),
            "upper": float(upper),
            "confidence": confidence,
            "n_bootstrap": n_bootstrap,
            "effective_bootstrap": len(values),
            "seed": seed,
        }
    return result


# A short alias is convenient for callers while retaining a descriptive public
# name at the implementation site.
compute_retrieval_diagnostics = evaluate_retrieval_diagnostics
