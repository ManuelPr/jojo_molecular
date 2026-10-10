"""Target-blind benchmark integrity and error diagnostics for Goal 4.

The functions in this module are deliberately model-agnostic.  They consume an
already constructed catalog, candidate pools and rankings; they never add a
truth structure to a pool.  This keeps candidate coverage separate from ranking
quality and makes the assumptions behind ``Recall@100 == 1`` explicit.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
import re
from typing import Any, Literal

import numpy as np


_INCHIKEY_RE = re.compile(r"^[A-Z]{14}(?:-[A-Z]{10}-[A-Z])?$")
_TARGET_AWARE_TERMS = ("oracle", "target", "truth", "validation", "holdout")
_PPM_WINDOWS = (5.0, 10.0, 20.0, 50.0)
BenchmarkMode = Literal["controlled", "realistic"]


def identity_key(value: Any) -> str:
    """Return the competition connectivity key while retaining fixture IDs."""

    text = str(value).strip()
    if not text:
        raise ValueError("Identity keys must not be empty")
    upper = text.upper()
    return upper[:14] if _INCHIKEY_RE.fullmatch(upper) else text


def _deduplicate_ids(values: Sequence[str]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = identity_key(value)
        if key in seen:
            continue
        seen.add(key)
        output.append(str(value))
    return tuple(output)


@dataclass(frozen=True, slots=True)
class CandidateDescriptor:
    """Minimal structure metadata needed by the benchmark audit."""

    candidate_id: str
    identity_key: str
    exact_mass: float
    formula: str | None = None
    source_set: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must not be empty")
        if not self.identity_key:
            raise ValueError("identity_key must not be empty")
        if not math.isfinite(self.exact_mass) or self.exact_mass <= 0:
            raise ValueError("exact_mass must be finite and positive")


@dataclass(frozen=True, slots=True)
class QueryMetadata:
    """Inference-visible query metadata plus optional diagnostic annotations."""

    neutral_mass: float | None
    formula: str | None = None
    adduct: str = "<missing>"
    instrument: str = "<missing>"
    spectrum_count: int = 1
    source: str = "<missing>"
    spectral_evidence_informative: bool | None = None
    ranker_used_informative_evidence: bool | None = None

    def __post_init__(self) -> None:
        if self.neutral_mass is not None and (
            not math.isfinite(self.neutral_mass) or self.neutral_mass <= 0
        ):
            raise ValueError("neutral_mass must be finite and positive when present")
        if self.spectrum_count <= 0:
            raise ValueError("spectrum_count must be positive")


@dataclass(frozen=True, slots=True)
class ConstructionProvenance:
    """Evidence that a benchmark was built without consulting holdout truth."""

    mode: BenchmarkMode
    catalog_selection_policy: str
    catalog_source_count: int
    catalog_selected_count: int
    catalog_target_ids_consulted: tuple[str, ...] = ()
    catalog_prioritized_target_ids: tuple[str, ...] = ()
    validation_identities_used: tuple[str, ...] = ()
    pool_target_consulted: Mapping[str, bool] = field(default_factory=dict)
    pool_target_injected: Mapping[str, bool] = field(default_factory=dict)
    inference_available_fields: tuple[str, ...] = (
        "precursor_mz",
        "adduct",
        "ionization_mode",
        "ms2_mzs",
        "ms2_normalized_intensities",
        "collision_energy_ev",
        "instrument_type",
    )

    def __post_init__(self) -> None:
        if self.mode not in ("controlled", "realistic"):
            raise ValueError(f"Unsupported benchmark mode: {self.mode!r}")
        if self.catalog_source_count < 0 or self.catalog_selected_count < 0:
            raise ValueError("Catalog counts must be non-negative")
        if self.catalog_selected_count > self.catalog_source_count:
            raise ValueError("Selected catalog cannot exceed its source")


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    mode: BenchmarkMode
    passed: bool
    violations: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "passed": self.passed,
            "violations": list(self.violations),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class Goal4AuditReport:
    summary: Mapping[str, Any]
    distributions: Mapping[str, Any]
    breakdowns: Mapping[str, Any]
    error_taxonomy: Mapping[str, Any]
    per_query: tuple[Mapping[str, Any], ...]
    integrity: IntegrityReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": dict(self.summary),
            "distributions": dict(self.distributions),
            "breakdowns": dict(self.breakdowns),
            "error_taxonomy": dict(self.error_taxonomy),
            "per_query": [dict(item) for item in self.per_query],
            "integrity": self.integrity.to_dict(),
        }


def _candidate_lookup(
    candidates: Mapping[str, CandidateDescriptor], candidate_id: str
) -> CandidateDescriptor | None:
    direct = candidates.get(candidate_id)
    if direct is not None:
        return direct
    key = identity_key(candidate_id)
    return next(
        (item for item in candidates.values() if identity_key(item.identity_key) == key),
        None,
    )


def _deduplicate_candidate_ids(
    values: Sequence[str], candidates: Mapping[str, CandidateDescriptor]
) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        descriptor = _candidate_lookup(candidates, str(value))
        key = identity_key(descriptor.identity_key if descriptor else value)
        if key in seen:
            continue
        seen.add(key)
        output.append(str(value))
    return tuple(output)


def _rank(
    values: Sequence[str],
    truth: str,
    candidates: Mapping[str, CandidateDescriptor],
) -> int | None:
    truth_key = identity_key(truth)
    for rank, candidate_id in enumerate(
        _deduplicate_candidate_ids(values, candidates), start=1
    ):
        descriptor = _candidate_lookup(candidates, candidate_id)
        key = identity_key(
            descriptor.identity_key if descriptor is not None else candidate_id
        )
        if key == truth_key:
            return rank
    return None


def _percentile_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if finite.size == 0:
        return {"count": 0, "min": None, "median": None, "p90": None, "max": None}
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "median": float(np.median(finite)),
        "p90": float(np.percentile(finite, 90)),
        "max": float(np.max(finite)),
    }


def _mass_bin(mass: float | None) -> str:
    if mass is None:
        return "<missing>"
    if mass < 200:
        return "<200"
    if mass < 400:
        return "200-399"
    if mass < 600:
        return "400-599"
    if mass < 800:
        return "600-799"
    return "800+"


def _spectrum_count_bin(count: int) -> str:
    if count == 1:
        return "1"
    if count <= 3:
        return "2-3"
    if count <= 7:
        return "4-7"
    return "8+"


def audit_construction_integrity(
    provenance: ConstructionProvenance,
    *,
    truth_keys: Mapping[str, str],
    catalog_candidate_ids: Sequence[str],
    candidate_pools: Mapping[str, Sequence[str]],
    candidates: Mapping[str, CandidateDescriptor],
) -> IntegrityReport:
    """Fail closed on target consultation, injection and out-of-catalog pools."""

    violations: list[str] = []
    limitations: list[str] = []
    catalog_ids = set(_deduplicate_ids(catalog_candidate_ids))
    catalog_keys = {
        identity_key(
            descriptor.identity_key if (descriptor := _candidate_lookup(candidates, item)) else item
        )
        for item in catalog_ids
    }
    policy = provenance.catalog_selection_policy.strip().lower()
    if provenance.mode == "realistic":
        if provenance.catalog_target_ids_consulted:
            violations.append("realistic catalog consulted target identities")
        if provenance.catalog_prioritized_target_ids:
            violations.append("realistic catalog prioritized target identities")
        if provenance.validation_identities_used:
            violations.append("validation identities influenced realistic construction")
        policy_without_blind_markers = policy.replace("target_blind", "").replace(
            "target-blind", ""
        )
        if any(term in policy_without_blind_markers for term in _TARGET_AWARE_TERMS):
            violations.append("catalog selection policy is target-aware")
        consulted = sorted(
            query_id
            for query_id, value in provenance.pool_target_consulted.items()
            if value
        )
        injected = sorted(
            query_id
            for query_id, value in provenance.pool_target_injected.items()
            if value
        )
        if consulted:
            violations.append(f"target consulted for {len(consulted)} pool(s)")
        if injected:
            violations.append(f"target injected into {len(injected)} pool(s)")

    for raw_query_id, pool in candidate_pools.items():
        query_id = str(raw_query_id)
        pool_ids = _deduplicate_candidate_ids(tuple(str(item) for item in pool), candidates)
        outside: list[str] = []
        for item in pool_ids:
            descriptor = _candidate_lookup(candidates, item)
            key = identity_key(descriptor.identity_key if descriptor else item)
            if item not in catalog_ids and key not in catalog_keys:
                outside.append(item)
        if outside:
            violations.append(
                f"query {query_id}: {len(outside)} candidate(s) are outside the catalog"
            )

    missing_provenance = sorted(set(map(str, truth_keys)) - set(provenance.pool_target_injected))
    if missing_provenance:
        limitations.append(
            "per-query injection flags were not supplied for "
            f"{len(missing_provenance)} query(s); absence cannot be inferred from ranks alone"
        )
    if provenance.catalog_source_count == provenance.catalog_selected_count:
        limitations.append(
            "catalog restriction is not tested against a larger source; external coverage "
            "must be measured separately"
        )
    return IntegrityReport(
        mode=provenance.mode,
        passed=not violations,
        violations=tuple(dict.fromkeys(violations)),
        limitations=tuple(dict.fromkeys(limitations)),
    )


def assert_realistic_integrity(report: IntegrityReport) -> None:
    if report.mode != "realistic":
        raise ValueError("Realistic integrity assertion requires realistic mode")
    if not report.passed:
        raise AssertionError("; ".join(report.violations))


def _aggregate_rows(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(row)
    output: dict[str, Any] = {}
    for value in sorted(grouped):
        members = grouped[value]
        ranks = [row["ranked_rank"] for row in members]
        pool_ranks = [row["pool_rank"] for row in members]
        rr = [0.0 if rank is None or rank > 25 else 1.0 / rank for rank in ranks]
        output[value] = {
            "query_count": len(members),
            "mrr_at_25": float(np.mean(rr)),
            "hit_at_1": float(np.mean([rank == 1 for rank in ranks])),
            "hit_at_5": float(
                np.mean([rank is not None and rank <= 5 for rank in ranks])
            ),
            "hit_at_10": float(
                np.mean([rank is not None and rank <= 10 for rank in ranks])
            ),
            "candidate_recall_at_25": float(
                np.mean([rank is not None and rank <= 25 for rank in pool_ranks])
            ),
            "candidate_recall_at_100": float(
                np.mean([rank is not None and rank <= 100 for rank in pool_ranks])
            ),
        }
    return output


def _query_error_flags(
    *,
    pool_rank: int | None,
    ranked_rank: int | None,
    truth_formula: str | None,
    top_candidate: CandidateDescriptor | None,
    same_formula_competitors: int,
    metadata: QueryMetadata,
) -> tuple[str, ...]:
    flags: list[str] = []
    if pool_rank is None:
        flags.append("target_absent_from_candidate_pool")
    elif pool_rank > 25:
        flags.append("target_present_beyond_25")
    elif ranked_rank != 1:
        flags.append("target_in_top25_not_rank1")
    if ranked_rank != 1 and top_candidate is not None:
        if truth_formula and top_candidate.formula == truth_formula:
            flags.append("top_error_same_formula")
            if identity_key(top_candidate.identity_key):
                flags.append("constitutional_isomer_proxy")
        else:
            flags.append("top_error_different_formula")
    if same_formula_competitors > 0:
        flags.append("same_formula_ambiguity")
    if metadata.adduct == "<missing>":
        flags.append("missing_adduct_metadata")
    if metadata.instrument.lower() not in {"timstof", "<missing>"}:
        flags.append("instrument_domain_shift_proxy")
    if metadata.spectral_evidence_informative is False:
        flags.append("spectral_features_uninformative")
    if (
        metadata.spectral_evidence_informative is True
        and metadata.ranker_used_informative_evidence is False
    ):
        flags.append("informative_features_not_exploited")
    return tuple(flags)


def audit_realistic_benchmark(
    *,
    truth_keys: Mapping[str, str],
    catalog_candidate_ids: Sequence[str],
    candidate_pools: Mapping[str, Sequence[str]],
    rankings: Mapping[str, Sequence[str]],
    candidates: Mapping[str, CandidateDescriptor],
    query_metadata: Mapping[str, QueryMetadata],
    provenance: ConstructionProvenance,
    ppm_windows: Sequence[float] = _PPM_WINDOWS,
) -> Goal4AuditReport:
    """Audit coverage, ambiguity, ranks, metadata slices and error classes.

    Candidate counts inside ppm windows are computed over the *entire supplied
    catalog*, not over a truncated pool.  This is essential for explaining ties
    and for comparing future catalog expansions at a constant retrieval rule.
    """

    if not truth_keys:
        raise ValueError("At least one query is required")
    windows = tuple(float(value) for value in ppm_windows)
    if any(not math.isfinite(value) or value <= 0 for value in windows):
        raise ValueError("ppm windows must be finite and positive")
    if len(set(windows)) != len(windows):
        raise ValueError("ppm windows must be unique")
    missing_meta = sorted(set(map(str, truth_keys)) - set(query_metadata))
    if missing_meta:
        raise ValueError(f"Missing query metadata for {len(missing_meta)} query(s)")

    integrity = audit_construction_integrity(
        provenance,
        truth_keys=truth_keys,
        catalog_candidate_ids=catalog_candidate_ids,
        candidate_pools=candidate_pools,
        candidates=candidates,
    )
    if provenance.mode == "realistic":
        assert_realistic_integrity(integrity)

    catalog_descriptors: list[CandidateDescriptor] = []
    seen_catalog: set[str] = set()
    for candidate_id in _deduplicate_ids(tuple(map(str, catalog_candidate_ids))):
        descriptor = _candidate_lookup(candidates, candidate_id)
        if descriptor is None:
            raise ValueError(f"Missing descriptor for catalog candidate {candidate_id!r}")
        key = identity_key(descriptor.identity_key)
        if key not in seen_catalog:
            seen_catalog.add(key)
            catalog_descriptors.append(descriptor)

    rows: list[dict[str, Any]] = []
    for raw_query_id, raw_truth in truth_keys.items():
        query_id = str(raw_query_id)
        truth = identity_key(raw_truth)
        metadata = query_metadata[query_id]
        pool = tuple(map(str, candidate_pools.get(query_id, ())))
        ranking = tuple(map(str, rankings.get(query_id, ())))
        pool_rank = _rank(pool, truth, candidates)
        ranked_rank = _rank(ranking, truth, candidates)
        truth_descriptor = next(
            (
                item
                for item in catalog_descriptors
                if identity_key(item.identity_key) == truth
            ),
            None,
        )
        truth_formula = metadata.formula or (
            truth_descriptor.formula if truth_descriptor is not None else None
        )
        truth_mass = metadata.neutral_mass
        ppm_counts: dict[str, int] = {}
        if truth_mass is None:
            ppm_counts = {f"{window:g}": 0 for window in windows}
        else:
            errors = np.asarray(
                [
                    abs(item.exact_mass - truth_mass) / truth_mass * 1e6
                    for item in catalog_descriptors
                ]
            )
            ppm_counts = {
                f"{window:g}": int(np.count_nonzero(errors <= window))
                for window in windows
            }

        pool_descriptors = [
            descriptor
            for candidate_id in _deduplicate_candidate_ids(pool, candidates)
            if (descriptor := _candidate_lookup(candidates, candidate_id)) is not None
        ]
        same_formula = sum(
            truth_formula is not None
            and item.formula == truth_formula
            and identity_key(item.identity_key) != truth
            for item in pool_descriptors
        )
        top_descriptor = (
            _candidate_lookup(candidates, ranking[0]) if ranking else None
        )
        error_flags = _query_error_flags(
            pool_rank=pool_rank,
            ranked_rank=ranked_rank,
            truth_formula=truth_formula,
            top_candidate=top_descriptor,
            same_formula_competitors=same_formula,
            metadata=metadata,
        )
        rows.append(
            {
                "query_id": query_id,
                "truth_key": truth,
                "neutral_mass": truth_mass,
                "mass_bin": _mass_bin(truth_mass),
                "adduct": metadata.adduct,
                "instrument": metadata.instrument,
                "source": metadata.source,
                "spectrum_count": metadata.spectrum_count,
                "spectrum_count_bin": _spectrum_count_bin(metadata.spectrum_count),
                "pool_size": len(_deduplicate_candidate_ids(pool, candidates)),
                "pool_rank": pool_rank,
                "ranked_rank": ranked_rank,
                "target_in_catalog": truth in seen_catalog,
                "same_formula_competitors": same_formula,
                "constitutional_isomer_proxy_count": same_formula,
                "candidates_within_ppm": ppm_counts,
                "error_flags": list(error_flags),
            }
        )

    pool_ranks = [row["pool_rank"] for row in rows]
    ranked_ranks = [row["ranked_rank"] for row in rows]
    reciprocal = [
        0.0 if rank is None or rank > 25 else 1.0 / rank for rank in ranked_ranks
    ]
    present = [rank is not None for rank in pool_ranks]
    error_counter = Counter(
        flag for row in rows for flag in row["error_flags"]
    )
    summary = {
        "mode": provenance.mode,
        "query_count": len(rows),
        "catalog_size": len(catalog_descriptors),
        "candidate_recall_at_25": float(
            np.mean([rank is not None and rank <= 25 for rank in pool_ranks])
        ),
        "candidate_recall_at_100": float(
            np.mean([rank is not None and rank <= 100 for rank in pool_ranks])
        ),
        "candidate_recall_at_1000": float(
            np.mean([rank is not None and rank <= 1000 for rank in pool_ranks])
        ),
        "pool_recall": float(np.mean(present)),
        "mrr_at_25": float(np.mean(reciprocal)),
        "hit_at_1": float(np.mean([rank == 1 for rank in ranked_ranks])),
        "hit_at_5": float(
            np.mean([rank is not None and rank <= 5 for rank in ranked_ranks])
        ),
        "hit_at_10": float(
            np.mean([rank is not None and rank <= 10 for rank in ranked_ranks])
        ),
        "conditional_mrr_at_25": (
            float(np.mean([rr for rr, recovered in zip(reciprocal, present) if recovered]))
            if any(present)
            else 0.0
        ),
        "oracle_mrr_at_25": float(np.mean(present)),
        "same_formula_query_fraction": float(
            np.mean([row["same_formula_competitors"] > 0 for row in rows])
        ),
    }
    distributions = {
        "neutral_mass": _percentile_summary(
            [row["neutral_mass"] for row in rows if row["neutral_mass"] is not None]
        ),
        "pool_size": _percentile_summary([row["pool_size"] for row in rows]),
        "truth_pool_rank": _percentile_summary(
            [rank for rank in pool_ranks if rank is not None]
        ),
        "same_formula_competitors": _percentile_summary(
            [row["same_formula_competitors"] for row in rows]
        ),
        "candidate_counts_within_ppm": {
            f"{window:g}": _percentile_summary(
                [row["candidates_within_ppm"][f"{window:g}"] for row in rows]
            )
            for window in windows
        },
    }
    breakdowns = {
        "mass": _aggregate_rows(rows, "mass_bin"),
        "adduct": _aggregate_rows(rows, "adduct"),
        "instrument": _aggregate_rows(rows, "instrument"),
        "source": _aggregate_rows(rows, "source"),
        "spectrum_count": _aggregate_rows(rows, "spectrum_count_bin"),
    }
    error_taxonomy = {
        "counts": dict(sorted(error_counter.items())),
        "query_ids_by_error": {
            flag: [row["query_id"] for row in rows if flag in row["error_flags"]]
            for flag in sorted(error_counter)
        },
    }
    return Goal4AuditReport(
        summary=summary,
        distributions=distributions,
        breakdowns=breakdowns,
        error_taxonomy=error_taxonomy,
        per_query=tuple(rows),
        integrity=integrity,
    )


def explain_recall_at_100(report: Goal4AuditReport) -> dict[str, Any]:
    """Return the evidence needed to interpret a perfect Recall@100 safely."""

    ranks = {
        str(row["query_id"]): row["pool_rank"] for row in report.per_query
    }
    perfect = bool(ranks) and all(
        rank is not None and int(rank) <= 100 for rank in ranks.values()
    )
    if report.integrity.mode == "realistic" and not report.integrity.passed:
        raise AssertionError("Cannot explain realistic recall from a failed integrity audit")
    return {
        "recall_at_100_is_one": perfect,
        "query_count": len(ranks),
        "maximum_truth_rank": max((int(rank) for rank in ranks.values() if rank), default=None),
        "truth_ranks": ranks,
        "target_consultation_detected": any(
            "consult" in item or "target-aware" in item
            for item in report.integrity.violations
        ),
        "target_injection_detected": any(
            "inject" in item for item in report.integrity.violations
        ),
        "interpretation": (
            "Every target was independently present in the catalog and retrieved within "
            "the first 100 candidates under the audited construction policy. This does "
            "not imply that the top-25 is easy or that an expanded catalog retains the same recall."
            if perfect
            else "At least one target is absent or ranked beyond 100."
        ),
        "limitations": list(report.integrity.limitations),
    }
