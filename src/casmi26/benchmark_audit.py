"""Pure, serialisable diagnostics for Goal 3 ranking benchmarks.

The helpers in this module deliberately keep target-aware *controlled* candidate
construction separate from target-blind *realistic* construction.  This makes a
candidate-generation ceiling measurable without accidentally presenting target
injection as retrieval quality.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import re
from typing import Any

import numpy as np

from .goal3_contracts import CandidatePoolAudit, CandidatePoolMode


_INCHIKEY_RE = re.compile(r"^[A-Z]{14}(?:-[A-Z]{10}-[A-Z])?$")
_EPSILON = 1e-12


def _identity(value: Any) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError("Candidate identities must not be empty")
    upper = result.upper()
    return upper[:14] if _INCHIKEY_RE.fullmatch(upper) else result


def _deduplicate(values: Sequence[Any]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value)
        key = _identity(candidate)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return tuple(result)


def _validate_mode(mode: CandidatePoolMode) -> None:
    if mode not in ("controlled", "realistic"):
        raise ValueError(f"Unsupported candidate-pool mode: {mode!r}")


@dataclass(frozen=True, slots=True)
class CatalogConstructionTrace:
    """Trace proving whether validation targets influenced catalog selection."""

    mode: CandidatePoolMode
    source_candidate_count: int
    candidate_ids: tuple[str, ...]
    target_ids_consulted: tuple[str, ...]
    prioritized_target_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "source_candidate_count": self.source_candidate_count,
            "candidate_ids": list(self.candidate_ids),
            "target_ids_consulted": list(self.target_ids_consulted),
            "prioritized_target_ids": list(self.prioritized_target_ids),
        }


@dataclass(frozen=True, slots=True)
class PoolConstructionTrace:
    """Candidate-pool provenance for one query."""

    query_id: str
    mode: CandidatePoolMode
    retrieved_candidate_ids: tuple[str, ...]
    final_candidate_ids: tuple[str, ...]
    target_was_consulted: bool
    target_was_injected: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "mode": self.mode,
            "retrieved_candidate_ids": list(self.retrieved_candidate_ids),
            "final_candidate_ids": list(self.final_candidate_ids),
            "target_was_consulted": self.target_was_consulted,
            "target_was_injected": self.target_was_injected,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkAuditReport:
    """Aggregate contract plus query-level evidence and integrity violations."""

    summary: CandidatePoolAudit
    per_query: tuple[dict[str, Any], ...]
    violations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        summary = self.summary
        return {
            "summary": {
                "mode": summary.mode,
                "query_count": summary.query_count,
                "catalog_size": summary.catalog_size,
                "target_in_catalog_count": summary.target_in_catalog_count,
                "target_in_pool_count": summary.target_in_pool_count,
                "target_in_top25_count": summary.target_in_top25_count,
                "explicit_target_injection_count": summary.explicit_target_injection_count,
                "median_pool_size": summary.median_pool_size,
                "median_same_formula_competitors": summary.median_same_formula_competitors,
                "median_exact_mass_competitors": summary.median_exact_mass_competitors,
                "catalog_recall": summary.catalog_recall,
                "pool_recall": summary.pool_recall,
                "recall_at_25": summary.recall_at_25,
            },
            "per_query": list(self.per_query),
            "violations": list(self.violations),
        }


def construct_candidate_catalog(
    source_candidate_ids: Sequence[str],
    *,
    mode: CandidatePoolMode,
    max_size: int | None = None,
    controlled_target_ids: Sequence[str] = (),
) -> CatalogConstructionTrace:
    """Select a catalog while making target-aware selection impossible in realistic mode.

    In controlled mode targets already present in ``source_candidate_ids`` are
    moved to the front.  No new chemical identity is manufactured.  In realistic
    mode ``controlled_target_ids`` is intentionally not inspected.
    """

    _validate_mode(mode)
    if max_size is not None and max_size <= 0:
        raise ValueError("max_size must be positive when provided")
    source = _deduplicate(source_candidate_ids)
    if mode == "realistic":
        selected = source if max_size is None else source[:max_size]
        return CatalogConstructionTrace(mode, len(source), selected, (), ())

    targets = _deduplicate(controlled_target_ids)
    target_keys = {_identity(value) for value in targets}
    prioritized = tuple(value for value in source if _identity(value) in target_keys)
    remainder = tuple(value for value in source if _identity(value) not in target_keys)
    ordered = (*prioritized, *remainder)
    selected = tuple(ordered if max_size is None else ordered[:max_size])
    selected_keys = {_identity(value) for value in selected}
    selected_prioritized = tuple(
        value for value in prioritized if _identity(value) in selected_keys
    )
    return CatalogConstructionTrace(
        mode,
        len(source),
        selected,
        targets,
        selected_prioritized,
    )


def construct_candidate_pool(
    query_id: str,
    retrieved_candidate_ids: Sequence[str],
    *,
    mode: CandidatePoolMode,
    max_size: int | None = None,
    controlled_target_id: str | None = None,
) -> PoolConstructionTrace:
    """Construct a pool with an auditable controlled-only target backstop.

    Passing ``controlled_target_id`` in realistic mode has no effect: the target
    is neither inspected nor copied into the output.  This behavior is important
    for adversarial tests of validation plumbing.
    """

    _validate_mode(mode)
    if max_size is not None and max_size <= 0:
        raise ValueError("max_size must be positive when provided")
    retrieved = _deduplicate(retrieved_candidate_ids)
    limited = list(retrieved if max_size is None else retrieved[:max_size])
    if mode == "realistic":
        return PoolConstructionTrace(str(query_id), mode, retrieved, tuple(limited), False, False)

    if controlled_target_id is None:
        return PoolConstructionTrace(str(query_id), mode, retrieved, tuple(limited), False, False)
    target = str(controlled_target_id)
    target_key = _identity(target)
    present = any(_identity(value) == target_key for value in limited)
    injected = not present
    if injected:
        if max_size is not None and len(limited) >= max_size:
            limited[-1] = target
        else:
            limited.append(target)
    return PoolConstructionTrace(str(query_id), mode, retrieved, tuple(limited), True, injected)


def _mapped_identity(
    candidate_id: str,
    candidate_identity_by_id: Mapping[str, str] | None,
) -> str:
    value = (
        candidate_identity_by_id.get(candidate_id, candidate_id)
        if candidate_identity_by_id is not None
        else candidate_id
    )
    return _identity(value)


def _candidate_keys(
    candidates: Sequence[str],
    candidate_identity_by_id: Mapping[str, str] | None,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _mapped_identity(str(candidate), candidate_identity_by_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return tuple(result)


def _lookup(mapping: Mapping[str, Any] | None, candidate_id: str, key: str) -> Any:
    if mapping is None:
        return None
    value = mapping.get(candidate_id)
    return mapping.get(key) if value is None else value


def audit_candidate_pools(
    truth_keys: Mapping[str, str],
    catalog_candidate_ids: Sequence[str],
    candidate_pools: Mapping[str, Sequence[str]],
    *,
    mode: CandidatePoolMode,
    ranked_candidates: Mapping[str, Sequence[str]] | None = None,
    pool_traces: Mapping[str, PoolConstructionTrace] | None = None,
    catalog_trace: CatalogConstructionTrace | None = None,
    candidate_identity_by_id: Mapping[str, str] | None = None,
    candidate_formula_by_id: Mapping[str, str] | None = None,
    truth_formula_by_query: Mapping[str, str] | None = None,
    candidate_exact_mass_by_id: Mapping[str, float] | None = None,
    truth_exact_mass_by_query: Mapping[str, float] | None = None,
    exact_mass_tolerance_da: float = 1e-6,
) -> BenchmarkAuditReport:
    """Audit catalog construction, candidate recovery, and target injection.

    Explicit injection is inferred from either construction trace or from a truth
    that occurs in a final pool but not in the corresponding retrieved pool.
    Target-informed catalog prioritisation counts as injection for affected
    queries because it changes measured catalog recall at a finite catalog cap.
    """

    _validate_mode(mode)
    if not math.isfinite(exact_mass_tolerance_da) or exact_mass_tolerance_da < 0:
        raise ValueError("exact_mass_tolerance_da must be finite and non-negative")
    catalog = _candidate_keys(catalog_candidate_ids, candidate_identity_by_id)
    catalog_keys = set(catalog)
    prioritized_keys = (
        {
            _mapped_identity(value, candidate_identity_by_id)
            for value in catalog_trace.prioritized_target_ids
        }
        if catalog_trace is not None
        else set()
    )
    observations: list[dict[str, Any]] = []
    violations: list[str] = []
    for raw_query_id, raw_truth in truth_keys.items():
        query_id = str(raw_query_id)
        truth = _identity(raw_truth)
        pool_values = candidate_pools.get(raw_query_id, candidate_pools.get(query_id, ()))
        pool_ids = tuple(str(value) for value in pool_values)
        pool_keys = _candidate_keys(pool_ids, candidate_identity_by_id)
        pool_key_set = set(pool_keys)
        ranking_values = (
            pool_values
            if ranked_candidates is None
            else ranked_candidates.get(raw_query_id, ranked_candidates.get(query_id, ()))
        )
        ranking_keys = _candidate_keys(
            tuple(str(value) for value in ranking_values), candidate_identity_by_id
        )
        trace = None if pool_traces is None else pool_traces.get(query_id)
        injection_reasons: list[str] = []
        if trace is not None:
            retrieved_keys = set(
                _candidate_keys(trace.retrieved_candidate_ids, candidate_identity_by_id)
            )
            final_keys = set(_candidate_keys(trace.final_candidate_ids, candidate_identity_by_id))
            if trace.target_was_injected or (truth not in retrieved_keys and truth in final_keys):
                injection_reasons.append("pool_target_injection")
            if trace.mode != mode:
                violations.append(
                    f"query {query_id}: pool trace mode {trace.mode!r} != audit mode {mode!r}"
                )
        if truth in prioritized_keys:
            injection_reasons.append("target_informed_catalog_selection")
        if catalog_trace is not None and catalog_trace.mode != mode:
            violations.append(
                f"catalog trace mode {catalog_trace.mode!r} != audit mode {mode!r}"
            )

        truth_formula = _lookup(truth_formula_by_query, query_id, query_id)
        truth_mass = _lookup(truth_exact_mass_by_query, query_id, query_id)
        same_formula = 0
        exact_mass = 0
        for candidate_id in pool_ids:
            key = _mapped_identity(candidate_id, candidate_identity_by_id)
            if key == truth:
                continue
            candidate_formula = _lookup(candidate_formula_by_id, candidate_id, key)
            if truth_formula is not None and candidate_formula == truth_formula:
                same_formula += 1
            candidate_mass = _lookup(candidate_exact_mass_by_id, candidate_id, key)
            if truth_mass is not None and candidate_mass is not None:
                try:
                    if abs(float(candidate_mass) - float(truth_mass)) <= exact_mass_tolerance_da:
                        exact_mass += 1
                except (TypeError, ValueError):
                    pass
        try:
            pool_rank = pool_keys.index(truth) + 1
        except ValueError:
            pool_rank = None
        try:
            ranked_rank = ranking_keys.index(truth) + 1
        except ValueError:
            ranked_rank = None
        observation = {
            "query_id": query_id,
            "truth_key": truth,
            "target_in_catalog": truth in catalog_keys,
            "target_in_pool": truth in pool_key_set,
            "target_in_top25": ranked_rank is not None and ranked_rank <= 25,
            "pool_rank": pool_rank,
            "ranked_rank": ranked_rank,
            "pool_size": len(pool_keys),
            "same_formula_competitors": same_formula,
            "exact_mass_competitors": exact_mass,
            "explicit_target_injection": bool(injection_reasons),
            "injection_reasons": injection_reasons,
        }
        observations.append(observation)
        if mode == "realistic" and injection_reasons:
            violations.append(
                f"query {query_id}: target evidence used in realistic mode "
                f"({', '.join(injection_reasons)})"
            )

    def median(field: str) -> float:
        return float(np.median([item[field] for item in observations])) if observations else 0.0

    summary = CandidatePoolAudit(
        mode=mode,
        query_count=len(observations),
        catalog_size=len(catalog),
        target_in_catalog_count=sum(item["target_in_catalog"] for item in observations),
        target_in_pool_count=sum(item["target_in_pool"] for item in observations),
        target_in_top25_count=sum(item["target_in_top25"] for item in observations),
        explicit_target_injection_count=sum(
            item["explicit_target_injection"] for item in observations
        ),
        median_pool_size=median("pool_size"),
        median_same_formula_competitors=median("same_formula_competitors"),
        median_exact_mass_competitors=median("exact_mass_competitors"),
    )
    return BenchmarkAuditReport(summary, tuple(observations), tuple(dict.fromkeys(violations)))


def assert_realistic_candidate_integrity(report: BenchmarkAuditReport) -> None:
    """Fail closed when a realistic benchmark contains target-aware construction."""

    if report.summary.mode != "realistic":
        raise ValueError("Integrity assertion requires a realistic-mode report")
    if report.summary.explicit_target_injection_count or report.violations:
        detail = "; ".join(report.violations) or "explicit target injection detected"
        raise AssertionError(detail)


def _rank(candidates: Sequence[str], truth: str, cutoff: int) -> int | None:
    keys = _candidate_keys(tuple(str(item) for item in candidates), None)
    try:
        rank = keys.index(truth) + 1
    except ValueError:
        return None
    return rank if rank <= cutoff else None


def rank_shift_diagnostics(
    truth_keys: Mapping[str, str],
    rankings_by_method: Mapping[str, Mapping[str, Sequence[str]]],
    *,
    baseline_method: str,
    cutoff: int = 25,
) -> dict[str, Any]:
    """Compare truth-rank movement for every method against one baseline."""

    if cutoff <= 0:
        raise ValueError("cutoff must be positive")
    if baseline_method not in rankings_by_method:
        raise ValueError(f"Unknown baseline method: {baseline_method!r}")
    methods: dict[str, Any] = {}
    ranks: dict[str, dict[str, int | None]] = {}
    for method, rankings in rankings_by_method.items():
        method_ranks: dict[str, int | None] = {}
        reciprocal: list[float] = []
        for raw_query_id, raw_truth in truth_keys.items():
            query_id = str(raw_query_id)
            candidates = rankings.get(raw_query_id, rankings.get(query_id, ()))
            value = _rank(candidates, _identity(raw_truth), cutoff)
            method_ranks[query_id] = value
            reciprocal.append(0.0 if value is None else 1.0 / value)
        ranks[method] = method_ranks
        methods[method] = {
            "query_count": len(truth_keys),
            "recovered_at_cutoff": sum(value is not None for value in method_ranks.values()),
            "mrr_at_cutoff": float(np.mean(reciprocal)) if reciprocal else 0.0,
            "mean_rank_when_recovered": (
                float(np.mean([value for value in method_ranks.values() if value is not None]))
                if any(value is not None for value in method_ranks.values())
                else None
            ),
        }

    comparisons: dict[str, Any] = {}
    baseline = ranks[baseline_method]
    for method in rankings_by_method:
        if method == baseline_method:
            continue
        rows: list[dict[str, Any]] = []
        shifts: list[int] = []
        rr_deltas: list[float] = []
        for query_id in baseline:
            before = baseline[query_id]
            after = ranks[method][query_id]
            effective_before = cutoff + 1 if before is None else before
            effective_after = cutoff + 1 if after is None else after
            shift = effective_before - effective_after
            rr_before = 0.0 if before is None else 1.0 / before
            rr_after = 0.0 if after is None else 1.0 / after
            shifts.append(shift)
            rr_deltas.append(rr_after - rr_before)
            rows.append(
                {
                    "query_id": query_id,
                    "baseline_rank": before,
                    "challenger_rank": after,
                    "rank_shift": shift,
                    "reciprocal_rank_delta": rr_after - rr_before,
                }
            )
        comparisons[method] = {
            "baseline_method": baseline_method,
            "challenger_method": method,
            "positive_shift_means_improvement": True,
            "improved_count": sum(value > 0 for value in shifts),
            "unchanged_count": sum(value == 0 for value in shifts),
            "worsened_count": sum(value < 0 for value in shifts),
            "mean_rank_shift": float(np.mean(shifts)) if shifts else 0.0,
            "median_rank_shift": float(np.median(shifts)) if shifts else 0.0,
            "mean_reciprocal_rank_delta": float(np.mean(rr_deltas)) if rr_deltas else 0.0,
            "per_query": rows,
        }
    return {"cutoff": cutoff, "methods": methods, "comparisons": comparisons}


def candidate_prior_diagnostics(
    groups: Mapping[str, Sequence[Any]],
    truth_keys: Mapping[str, str],
) -> dict[str, Any]:
    """Measure source/rank priors that a supervised ranker could exploit."""

    rows: list[dict[str, Any]] = []
    for raw_query_id, hits in groups.items():
        query_id = str(raw_query_id)
        raw_truth = truth_keys.get(raw_query_id, truth_keys.get(query_id))
        if raw_truth is None:
            raise KeyError(f"Missing truth for query {query_id!r}")
        truth = _identity(raw_truth)
        for hit in hits:
            source_rank = int(hit.source_rank)
            rows.append(
                {
                    "source": str(hit.source or "<missing>"),
                    "source_rank": source_rank,
                    "source_rank_bin": (
                        "1"
                        if source_rank <= 1
                        else "2-5"
                        if source_rank <= 5
                        else "6-25"
                        if source_rank <= 25
                        else "26+"
                    ),
                    "retrieval_score": float(hit.retrieval_score),
                    "positive": int(_identity(hit.candidate_id) == truth),
                    "query_id": query_id,
                }
            )

    def aggregate(field: str) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row[field])].append(row)
        result: dict[str, Any] = {}
        for value, members in sorted(grouped.items()):
            positives = sum(int(row["positive"]) for row in members)
            result[value] = {
                "candidate_count": len(members),
                "positive_count": positives,
                "positive_rate": positives / len(members),
                "mean_source_rank": float(
                    np.mean([row["source_rank"] for row in members])
                ),
                "mean_retrieval_score": float(
                    np.mean([row["retrieval_score"] for row in members])
                ),
            }
        return result

    return {
        "candidate_count": len(rows),
        "positive_count": sum(int(row["positive"]) for row in rows),
        "by_source": aggregate("source"),
        "by_source_rank_bin": aggregate("source_rank_bin"),
    }


def _feature_columns(
    features: Mapping[str, Sequence[float]] | np.ndarray,
    feature_names: Sequence[str] | None,
) -> tuple[tuple[str, ...], tuple[np.ndarray, ...]]:
    if isinstance(features, Mapping):
        names = tuple(str(name) for name in features)
        return names, tuple(np.asarray(features[name], dtype=np.float64) for name in features)
    array = np.asarray(features, dtype=np.float64)
    if array.ndim != 2:
        raise ValueError("Feature matrices must have shape [rows, features]")
    names = (
        tuple(str(name) for name in feature_names)
        if feature_names is not None
        else tuple(f"feature_{index}" for index in range(array.shape[1]))
    )
    if len(names) != array.shape[1]:
        raise ValueError("feature_names must match the feature matrix width")
    return names, tuple(array[:, index] for index in range(array.shape[1]))


def _ks_statistic(first: np.ndarray, second: np.ndarray) -> float | None:
    if not len(first) or not len(second):
        return None
    points = np.unique(np.concatenate((first, second)))
    first_cdf = np.searchsorted(np.sort(first), points, side="right") / len(first)
    second_cdf = np.searchsorted(np.sort(second), points, side="right") / len(second)
    return float(np.max(np.abs(first_cdf - second_cdf)))


def _population_stability_index(
    train: np.ndarray, validation: np.ndarray, n_bins: int
) -> float | None:
    if not len(train) or not len(validation):
        return None
    edges = np.unique(np.quantile(train, np.linspace(0.0, 1.0, n_bins + 1)))
    if len(edges) < 2:
        return 0.0 if np.all(validation == train[0]) else None
    edges[0], edges[-1] = -np.inf, np.inf
    train_counts = np.histogram(train, bins=edges)[0].astype(float)
    validation_counts = np.histogram(validation, bins=edges)[0].astype(float)
    train_rate = np.maximum(train_counts / len(train), _EPSILON)
    validation_rate = np.maximum(validation_counts / len(validation), _EPSILON)
    return float(np.sum((validation_rate - train_rate) * np.log(validation_rate / train_rate)))


def feature_drift_diagnostics(
    train_features: Mapping[str, Sequence[float]] | np.ndarray,
    validation_features: Mapping[str, Sequence[float]] | np.ndarray,
    *,
    feature_names: Sequence[str] | None = None,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Measure train/validation feature drift with SMD, KS, PSI, and missingness."""

    if n_bins < 2:
        raise ValueError("n_bins must be at least two")
    train_names, train_columns = _feature_columns(train_features, feature_names)
    validation_names, validation_columns = _feature_columns(validation_features, feature_names)
    if train_names != validation_names:
        raise ValueError("Train and validation feature schemas differ")
    output: dict[str, Any] = {}
    for name, raw_train, raw_validation in zip(
        train_names, train_columns, validation_columns, strict=True
    ):
        finite_train = raw_train[np.isfinite(raw_train)]
        finite_validation = raw_validation[np.isfinite(raw_validation)]
        train_mean = float(np.mean(finite_train)) if len(finite_train) else None
        validation_mean = float(np.mean(finite_validation)) if len(finite_validation) else None
        train_std = float(np.std(finite_train)) if len(finite_train) else None
        validation_std = float(np.std(finite_validation)) if len(finite_validation) else None
        pooled = (
            math.sqrt((train_std**2 + validation_std**2) / 2.0)
            if train_std is not None and validation_std is not None
            else None
        )
        if train_mean is None or validation_mean is None:
            smd = None
        elif pooled and pooled > 0:
            smd = (validation_mean - train_mean) / pooled
        else:
            smd = 0.0 if train_mean == validation_mean else None
        ks = _ks_statistic(finite_train, finite_validation)
        psi = _population_stability_index(finite_train, finite_validation, n_bins)
        output[name] = {
            "train_count": int(len(raw_train)),
            "validation_count": int(len(raw_validation)),
            "train_finite_count": int(len(finite_train)),
            "validation_finite_count": int(len(finite_validation)),
            "train_missing_rate": float(1.0 - len(finite_train) / len(raw_train))
            if len(raw_train)
            else 0.0,
            "validation_missing_rate": float(1.0 - len(finite_validation) / len(raw_validation))
            if len(raw_validation)
            else 0.0,
            "train_mean": train_mean,
            "validation_mean": validation_mean,
            "train_std": train_std,
            "validation_std": validation_std,
            "standardized_mean_difference": smd,
            "ks_statistic": ks,
            "population_stability_index": psi,
            "drift_flag": bool(
                (smd is not None and abs(smd) >= 0.2)
                or (ks is not None and ks >= 0.1)
                or (psi is not None and psi >= 0.2)
            ),
        }
    return {"feature_count": len(output), "features": output}


def _positive_probabilities(model: Any, features: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        probabilities = np.asarray(model.predict_proba(features), dtype=np.float64)
        if probabilities.ndim == 2 and probabilities.shape[1] >= 2:
            return probabilities[:, 1]
        return probabilities.reshape(-1)
    if hasattr(model, "decision_function"):
        decision = np.asarray(model.decision_function(features), dtype=np.float64).reshape(-1)
        return 1.0 / (1.0 + np.exp(-np.clip(decision, -50.0, 50.0)))
    if hasattr(model, "predict"):
        decision = np.asarray(model.predict(features), dtype=np.float64).reshape(-1)
        return 1.0 / (1.0 + np.exp(-np.clip(decision, -50.0, 50.0)))
    raise TypeError("Model has neither predict_proba, decision_function, nor predict")


def model_importance_diagnostics(
    model: Any,
    feature_names: Sequence[str],
    *,
    validation_features: np.ndarray | None = None,
    validation_labels: Sequence[int] | None = None,
    n_repeats: int = 5,
    seed: int = 2026,
) -> dict[str, Any]:
    """Return native and deterministic log-loss permutation importance when available."""

    names = tuple(str(name) for name in feature_names)
    native_values = None
    native_kind = None
    if hasattr(model, "feature_importances_"):
        native_values = np.asarray(model.feature_importances_, dtype=np.float64).reshape(-1)
        native_kind = "feature_importances_"
    elif hasattr(model, "coef_"):
        coefficients = np.asarray(model.coef_, dtype=np.float64)
        native_values = np.mean(np.abs(np.atleast_2d(coefficients)), axis=0)
        native_kind = "absolute_coef"
    if native_values is not None and len(native_values) != len(names):
        raise ValueError("Native model importance width does not match feature_names")
    native = (
        sorted(
            (
                {"feature": name, "importance": float(value)}
                for name, value in zip(names, native_values, strict=True)
            ),
            key=lambda item: (-item["importance"], item["feature"]),
        )
        if native_values is not None
        else None
    )

    permutation = None
    unavailable_reason = None
    if validation_features is not None or validation_labels is not None:
        if validation_features is None or validation_labels is None:
            raise ValueError("Both validation_features and validation_labels are required")
        if n_repeats <= 0:
            raise ValueError("n_repeats must be positive")
        features = np.asarray(validation_features, dtype=np.float64)
        labels = np.asarray(validation_labels, dtype=np.float64).reshape(-1)
        if features.ndim != 2 or features.shape != (len(labels), len(names)):
            raise ValueError("Validation data shape does not match labels and feature_names")
        try:
            baseline_probability = np.clip(
                _positive_probabilities(model, features), _EPSILON, 1.0 - _EPSILON
            )
            baseline_loss = float(
                -np.mean(
                    labels * np.log(baseline_probability)
                    + (1.0 - labels) * np.log(1.0 - baseline_probability)
                )
            )
            rng = np.random.default_rng(seed)
            items: list[dict[str, Any]] = []
            for column, name in enumerate(names):
                changes: list[float] = []
                for _ in range(n_repeats):
                    permuted = features.copy()
                    permuted[:, column] = permuted[rng.permutation(len(features)), column]
                    probability = np.clip(
                        _positive_probabilities(model, permuted), _EPSILON, 1.0 - _EPSILON
                    )
                    loss = float(
                        -np.mean(
                            labels * np.log(probability)
                            + (1.0 - labels) * np.log(1.0 - probability)
                        )
                    )
                    changes.append(loss - baseline_loss)
                items.append(
                    {
                        "feature": name,
                        "mean_log_loss_increase": float(np.mean(changes)),
                        "std_log_loss_increase": float(np.std(changes)),
                    }
                )
            permutation = sorted(
                items,
                key=lambda item: (-item["mean_log_loss_increase"], item["feature"]),
            )
        except (TypeError, ValueError) as error:
            unavailable_reason = str(error)
    elif native is None:
        unavailable_reason = "model has no native importance and no validation data was supplied"
    return {
        "native_kind": native_kind,
        "native": native,
        "permutation": permutation,
        "permutation_metric": "log_loss_increase" if permutation is not None else None,
        "unavailable_reason": unavailable_reason,
    }


def calibration_diagnostics(
    labels: Sequence[int],
    probabilities: Sequence[float],
    *,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Binary calibration table with Brier, log loss, ECE, and MCE."""

    truth = np.asarray(labels, dtype=np.float64).reshape(-1)
    predicted = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    if len(truth) != len(predicted):
        raise ValueError("labels and probabilities must have equal length")
    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
    if np.any((truth != 0) & (truth != 1)):
        raise ValueError("labels must be binary")
    if np.any(~np.isfinite(predicted)) or np.any((predicted < 0) | (predicted > 1)):
        raise ValueError("probabilities must be finite values in [0, 1]")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.minimum(np.searchsorted(edges, predicted, side="right") - 1, n_bins - 1)
    bin_indices = np.maximum(bin_indices, 0)
    bins: list[dict[str, Any]] = []
    weighted_error = 0.0
    maximum_error = 0.0
    for index in range(n_bins):
        mask = bin_indices == index
        count = int(mask.sum())
        mean_probability = float(np.mean(predicted[mask])) if count else None
        observed_rate = float(np.mean(truth[mask])) if count else None
        error = (
            abs(mean_probability - observed_rate)
            if mean_probability is not None and observed_rate is not None
            else 0.0
        )
        weighted_error += count * error
        maximum_error = max(maximum_error, error)
        bins.append(
            {
                "lower": float(edges[index]),
                "upper": float(edges[index + 1]),
                "count": count,
                "mean_probability": mean_probability,
                "observed_positive_rate": observed_rate,
                "absolute_calibration_error": error if count else None,
            }
        )
    clipped = np.clip(predicted, _EPSILON, 1.0 - _EPSILON)
    return {
        "sample_count": len(truth),
        "positive_count": int(truth.sum()),
        "brier_score": float(np.mean((predicted - truth) ** 2)) if len(truth) else 0.0,
        "log_loss": float(
            -np.mean(truth * np.log(clipped) + (1.0 - truth) * np.log(1.0 - clipped))
        )
        if len(truth)
        else 0.0,
        "expected_calibration_error": weighted_error / len(truth) if len(truth) else 0.0,
        "maximum_calibration_error": maximum_error,
        "bins": bins,
    }


def _isomer_bin(count: int) -> str:
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 4:
        return "2-4"
    return "5+"


def _pool_size_bin(count: int) -> str:
    if count < 25:
        return "0-24"
    if count < 100:
        return "25-99"
    if count < 1000:
        return "100-999"
    return "1000+"


def ranking_breakdowns(
    truth_keys: Mapping[str, str],
    candidate_pools: Mapping[str, Sequence[str]],
    ranked_candidates: Mapping[str, Sequence[str]],
    *,
    candidate_formula_by_id: Mapping[str, str] | None = None,
    truth_formula_by_query: Mapping[str, str] | None = None,
    cutoff: int = 25,
) -> dict[str, Any]:
    """MRR/recall breakdowns by formula, isomer competition, and pool size."""

    if cutoff <= 0:
        raise ValueError("cutoff must be positive")
    rows: list[dict[str, Any]] = []
    for raw_query_id, raw_truth in truth_keys.items():
        query_id = str(raw_query_id)
        truth = _identity(raw_truth)
        pool = tuple(str(item) for item in candidate_pools.get(query_id, ()))
        ranking = tuple(str(item) for item in ranked_candidates.get(query_id, ()))
        pool_keys = _candidate_keys(pool, None)
        rank = _rank(ranking, truth, cutoff)
        formula = _lookup(truth_formula_by_query, query_id, query_id)
        isomers = 0
        if formula is not None:
            for candidate_id in pool:
                key = _identity(candidate_id)
                if key != truth and _lookup(candidate_formula_by_id, candidate_id, key) == formula:
                    isomers += 1
        rows.append(
            {
                "query_id": query_id,
                "formula": "<missing>" if formula is None else str(formula),
                "isomer_count": isomers,
                "isomer_count_bin": _isomer_bin(isomers),
                "pool_size": len(pool_keys),
                "pool_size_bin": _pool_size_bin(len(pool_keys)),
                "recovered": truth in set(pool_keys),
                "rank": rank,
                "reciprocal_rank": 0.0 if rank is None else 1.0 / rank,
            }
        )

    def aggregate(field: str) -> dict[str, dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row[field])].append(row)
        return {
            label: {
                "query_count": len(group),
                "pool_recall": float(np.mean([row["recovered"] for row in group])),
                "mrr_at_cutoff": float(np.mean([row["reciprocal_rank"] for row in group])),
                "hit_at_1": float(np.mean([row["rank"] == 1 for row in group])),
                "median_pool_size": float(np.median([row["pool_size"] for row in group])),
                "median_isomer_count": float(
                    np.median([row["isomer_count"] for row in group])
                ),
            }
            for label, group in sorted(groups.items())
        }

    return {
        "cutoff": cutoff,
        "formula": aggregate("formula"),
        "isomer_count": aggregate("isomer_count_bin"),
        "pool_size": aggregate("pool_size_bin"),
        "per_query": rows,
    }
