from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence, Set
import math
from typing import Any

import numpy as np


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if not len(finite):
        return {
            "count": 0,
            "min": None,
            "median": None,
            "p90": None,
            "max": None,
            "mean": None,
        }
    return {
        "count": int(len(finite)),
        "min": float(np.min(finite)),
        "median": float(np.median(finite)),
        "p90": float(np.quantile(finite, 0.9)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
    }


def summarize_candidate_tier(
    truth_by_query: Mapping[str, str],
    rankings: Mapping[str, Sequence[str]],
    *,
    catalog_identities: Set[str],
    formula_by_candidate: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Summarize closed-world coverage separately from mass-ranking quality."""

    if not truth_by_query:
        raise ValueError("truth_by_query must not be empty")
    ranks: list[int | None] = []
    in_catalog: list[bool] = []
    formula_counts = Counter(
        formula
        for candidate_id, formula in (formula_by_candidate or {}).items()
        if candidate_id in catalog_identities and formula
    )
    same_formula_competitors: list[float] = []
    for query_id, truth in truth_by_query.items():
        candidates = list(dict.fromkeys(rankings.get(query_id, ())))
        rank = next(
            (index for index, candidate in enumerate(candidates, start=1) if candidate == truth),
            None,
        )
        ranks.append(rank)
        present = truth in catalog_identities
        in_catalog.append(present)
        if formula_by_candidate is not None:
            formula = formula_by_candidate.get(truth)
            count = formula_counts.get(formula or "", 0)
            same_formula_competitors.append(float(max(0, count - int(present))))

    reciprocal = [
        1.0 / rank if rank is not None and rank <= 25 else 0.0 for rank in ranks
    ]
    recovered = [rank is not None for rank in ranks]
    conditional = [value for value, is_recovered in zip(reciprocal, recovered) if is_recovered]
    result: dict[str, Any] = {
        "query_count": len(ranks),
        "catalog_present_count": int(sum(in_catalog)),
        "catalog_recall": float(np.mean(in_catalog)),
        "candidate_recall_at_25": float(
            np.mean([rank is not None and rank <= 25 for rank in ranks])
        ),
        "candidate_recall_at_100": float(
            np.mean([rank is not None and rank <= 100 for rank in ranks])
        ),
        "candidate_recall_at_1000": float(np.mean(recovered)),
        "mrr_at_25": float(np.mean(reciprocal)),
        "conditional_mrr_at_25": float(np.mean(conditional)) if conditional else 0.0,
        "hit_at_1": float(np.mean([rank == 1 for rank in ranks])),
        "hit_at_5": float(
            np.mean([rank is not None and rank <= 5 for rank in ranks])
        ),
        "hit_at_10": float(
            np.mean([rank is not None and rank <= 10 for rank in ranks])
        ),
        "truth_rank": _distribution(
            [float(rank) for rank in ranks if rank is not None]
        ),
    }
    if formula_by_candidate is not None:
        result["same_formula_competitors"] = _distribution(same_formula_competitors)
    return result


def summarize_neutral_mass_residuals(
    neutral_masses_by_query: Mapping[str, Sequence[float]],
    truth_mass_by_query: Mapping[str, float],
    adducts_by_query: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Measure precursor/adduct inversion error against structure exact masses."""

    overall: list[float] = []
    by_adduct: dict[str, list[float]] = defaultdict(list)
    missing_queries: list[str] = []
    for query_id, truth_mass in truth_mass_by_query.items():
        masses = neutral_masses_by_query.get(query_id, ())
        adducts = adducts_by_query.get(query_id, ())
        if not masses:
            missing_queries.append(query_id)
            continue
        if len(masses) != len(adducts):
            raise ValueError(f"Mass/adduct count mismatch for {query_id}")
        for mass, adduct in zip(masses, adducts):
            if not math.isfinite(mass) or mass <= 0 or truth_mass <= 0:
                continue
            ppm = abs(float(mass) - float(truth_mass)) / float(truth_mass) * 1e6
            overall.append(ppm)
            by_adduct[str(adduct)].append(ppm)
    return {
        "query_count": len(truth_mass_by_query),
        "missing_query_count": len(missing_queries),
        "missing_queries": sorted(missing_queries),
        "ppm_error": _distribution(overall),
        "ppm_error_by_adduct": {
            key: _distribution(values) for key, values in sorted(by_adduct.items())
        },
    }


def audit_prediction_identities(
    expected_query_ids: Sequence[str],
    predictions: Mapping[str, Sequence[str]],
    *,
    catalog_identities: Set[str],
    query_mass_by_id: Mapping[str, float] | None = None,
    candidate_mass_by_id: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Detect missing/default rows and mass-incoherent output identities."""

    expected = list(dict.fromkeys(map(str, expected_query_ids)))
    missing = [query_id for query_id in expected if query_id not in predictions]
    extra = sorted(set(predictions) - set(expected))
    ranking_signatures: Counter[tuple[str, ...]] = Counter()
    candidate_counts: list[float] = []
    catalog_membership: list[bool] = []
    ppm_errors: list[float] = []
    first_candidate_ppm: list[float] = []
    duplicate_identity_rows = 0
    for query_id in expected:
        candidates = list(predictions.get(query_id, ()))
        ranking_signatures[tuple(candidates)] += 1
        candidate_counts.append(float(len(candidates)))
        if len(candidates) != len(set(candidates)):
            duplicate_identity_rows += 1
        catalog_membership.extend(candidate in catalog_identities for candidate in candidates)
        if query_mass_by_id is None or candidate_mass_by_id is None:
            continue
        query_mass = query_mass_by_id.get(query_id)
        if query_mass is None or not math.isfinite(query_mass) or query_mass <= 0:
            continue
        row_errors = []
        for candidate in candidates:
            candidate_mass = candidate_mass_by_id.get(candidate)
            if candidate_mass is None:
                continue
            row_errors.append(abs(candidate_mass - query_mass) / query_mass * 1e6)
        ppm_errors.extend(row_errors)
        if row_errors:
            first_candidate_ppm.append(row_errors[0])

    most_common = ranking_signatures.most_common(1)
    most_common_count = most_common[0][1] if most_common else 0
    return {
        "expected_query_count": len(expected),
        "prediction_query_count": len(predictions),
        "missing_query_count": len(missing),
        "extra_query_count": len(extra),
        "missing_queries": missing,
        "extra_queries": extra,
        "candidate_count": _distribution(candidate_counts),
        "duplicate_identity_row_count": duplicate_identity_rows,
        "unique_ranking_count": len(ranking_signatures),
        "most_common_ranking_count": most_common_count,
        "most_common_ranking_fraction": (
            float(most_common_count / len(expected)) if expected else 0.0
        ),
        "catalog_candidate_fraction": (
            float(np.mean(catalog_membership)) if catalog_membership else 0.0
        ),
        "candidate_mass_error_ppm": _distribution(ppm_errors),
        "first_candidate_mass_error_ppm": _distribution(first_candidate_ppm),
    }
