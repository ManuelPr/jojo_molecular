from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

from .analog_propagation import (
    AnalogCandidate,
    AnalogReference,
    LeakagePolicy,
    score_analog_candidates,
    spectrum_content_hash,
)
from .candidate_catalogs import CatalogRecord
from .data import ParquetSpectrumReader, PreprocessConfig, preprocess_spectrum
from .diagnostics import (
    bootstrap_paired_ranking_differences,
    evaluate_retrieval_diagnostics,
)
from .domain_validation import (
    DomainStage,
    DomainValidationPlan,
)
from .fingerprints import molecular_fingerprint
from .goal3_contracts import FingerprintSpec
from .goal4_ranking import (
    annotate_ranking_context,
    linear_evidence_ranking,
    same_anchor_formula_reranking,
)
from .mass_retrieval import MassCandidateIndex, StructureCandidate
from .scalable_analog import ScalableAnalogIndex
from .scalable_retrieval import (
    CandidateChannel,
    DynamicPoolConfig,
    ScalableMassFormulaIndex,
    retrieve_dynamic_pool,
    union_candidate_channels,
)
from .schemas import CandidateHit, ProcessedSpectrum


@dataclass(frozen=True, slots=True)
class Goal5ExperimentConfig:
    seed: int = 2027
    query_source: str = "enveda-np-examples"
    required_instrument: str | None = "timsTOF"
    background_reference_identities: int = 2_000
    spectra_per_background_identity: int = 1
    reference_spectra_per_domain_identity: int = 4
    fixed_pool_size: int = 100
    dynamic_pool_size: int = 1_000
    cheap_stage_size: int = 300
    expensive_stage_size: int = 100
    analog_top_k: int = 5
    analog_mass_window_da: float = 200.0
    peak_tolerance_da: float = 0.02
    fingerprint_bits: int = 512
    evidence_weight: float = 0.5
    max_peaks: int = 256
    intensity_floor: float = 0.001
    bootstrap_samples: int = 500


@dataclass(frozen=True, slots=True)
class DomainCollectionReport:
    scan_rows: int
    domain_identity_count: int
    selected_background_identity_count: int
    retained_spectrum_count: int
    retained_domain_spectrum_count: int
    retained_background_spectrum_count: int
    preprocessing_rejection_count: int
    source_counts: Mapping[str, int]
    instrument_counts: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_counts"] = dict(self.source_counts)
        payload["instrument_counts"] = dict(self.instrument_counts)
        return payload


def _identity(value: object) -> str | None:
    if value is None:
        return None
    key = str(value).strip().upper()[:14]
    return key if len(key) == 14 and key.isalpha() else None


def _normalized_label(value: object) -> str:
    return "".join(character for character in str(value or "").lower() if character.isalnum())


def _seed_order(keys: Sequence[str], *, seed: int, namespace: str) -> list[str]:
    return sorted(
        set(keys),
        key=lambda key: (
            hashlib.sha256(f"{namespace}\0{seed}\0{key}".encode()).digest(),
            key,
        ),
    )


def read_identity_file(path: str | Path) -> tuple[str, ...]:
    values = tuple(
        key
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if (key := _identity(line)) is not None
    )
    if not values:
        raise ValueError(f"No valid InChIKey14 identities in {path}")
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate identities in {path}")
    return values


def collect_domain_spectra(
    train_path: str | Path,
    *,
    catalog_identity_keys: Sequence[str],
    prior_final_identity_keys: Sequence[str],
    config: Goal5ExperimentConfig = Goal5ExperimentConfig(),
) -> tuple[tuple[ProcessedSpectrum, ...], DomainCollectionReport]:
    """Two-pass bounded collection; full peak arrays are read only in pass two."""

    reader = ParquetSpectrumReader(train_path)
    prior = set(prior_final_identity_keys)
    catalog_keys = set(catalog_identity_keys)
    expected_source = _normalized_label(config.query_source)
    expected_instrument = (
        None
        if config.required_instrument is None
        else _normalized_label(config.required_instrument)
    )
    domain_keys: set[str] = set()
    scan_rows = 0
    for record in reader.iter_records(
        columns=("inchikey14", "ingest_lib", "instrument_type")
    ):
        scan_rows += 1
        key = _identity(record.inchikey14)
        if key is None or key in prior or key not in catalog_keys:
            continue
        if _normalized_label(record.ingest_lib) != expected_source:
            continue
        if (
            expected_instrument is not None
            and _normalized_label(record.instrument) != expected_instrument
        ):
            continue
        domain_keys.add(key)
    if len(domain_keys) < 2:
        raise RuntimeError(
            f"Only {len(domain_keys)} domain identities matched source/instrument"
        )

    background_eligible = sorted(catalog_keys - domain_keys - prior)
    background_keys = set(
        _seed_order(
            background_eligible,
            seed=config.seed,
            namespace="goal5-background-reference",
        )[: config.background_reference_identities]
    )
    retained_background: Counter[str] = Counter()
    retained_domain_references: Counter[str] = Counter()
    preprocessing = PreprocessConfig(
        intensity_floor=config.intensity_floor,
        max_peaks=config.max_peaks,
    )
    spectra: list[ProcessedSpectrum] = []
    rejected = 0
    source_counts: Counter[str] = Counter()
    instrument_counts: Counter[str] = Counter()
    for record in reader.iter_records():
        key = _identity(record.inchikey14)
        if key is None or key in prior:
            continue
        is_domain_identity = key in domain_keys
        is_background = key in background_keys
        if not is_domain_identity and not is_background:
            continue
        is_domain_query_spectrum = (
            is_domain_identity
            and _normalized_label(record.ingest_lib) == expected_source
            and (
                expected_instrument is None
                or _normalized_label(record.instrument) == expected_instrument
            )
        )
        if (
            is_domain_identity
            and not is_domain_query_spectrum
            and retained_domain_references[key]
            >= config.reference_spectra_per_domain_identity
        ):
            continue
        if (
            is_background
            and retained_background[key] >= config.spectra_per_background_identity
        ):
            continue
        try:
            spectrum = preprocess_spectrum(record, preprocessing)
        except ValueError:
            rejected += 1
            continue
        if not spectrum.mz.size:
            rejected += 1
            continue
        spectra.append(spectrum)
        if is_domain_identity and not is_domain_query_spectrum:
            retained_domain_references[key] += 1
        if is_background and not is_domain_identity:
            retained_background[key] += 1
        source_counts[str(spectrum.ingest_lib or "<missing>")] += 1
        instrument_counts[str(spectrum.instrument or "<missing>")] += 1
    domain_count = sum(_identity(item.inchikey14) in domain_keys for item in spectra)
    report = DomainCollectionReport(
        scan_rows=scan_rows,
        domain_identity_count=len(domain_keys),
        selected_background_identity_count=len(background_keys),
        retained_spectrum_count=len(spectra),
        retained_domain_spectrum_count=int(domain_count),
        retained_background_spectrum_count=len(spectra) - int(domain_count),
        preprocessing_rejection_count=rejected,
        source_counts=dict(sorted(source_counts.items())),
        instrument_counts=dict(sorted(instrument_counts.items())),
    )
    return tuple(sorted(spectra, key=lambda item: item.spectrum_id)), report


def catalog_to_structure_candidates(
    records: Sequence[CatalogRecord],
) -> list[StructureCandidate]:
    return [
        StructureCandidate(
            candidate_id=record.inchikey14,
            smiles=record.smiles,
            exact_mass=record.exact_mass,
            formula=record.formula,
            source="+".join(record.sources),
        )
        for record in records
    ]


def _query_mass(spectra: Sequence[ProcessedSpectrum]) -> float:
    values = [
        float(item.neutral_mass)
        for item in spectra
        if item.neutral_mass is not None and math.isfinite(float(item.neutral_mass))
    ]
    if not values:
        raise RuntimeError("Query has no finite inference-safe neutral mass")
    return float(np.median(values))


def _fingerprint(
    candidate: StructureCandidate,
    cache: dict[str, np.ndarray],
    spec: FingerprintSpec,
) -> np.ndarray:
    value = cache.get(candidate.candidate_id)
    if value is None:
        try:
            value = molecular_fingerprint(candidate.smiles, spec)
        except ValueError:
            value = np.zeros(spec.n_bits, dtype=np.float32)
        cache[candidate.candidate_id] = value
    return value


def _build_references(
    spectrum_ids: Sequence[str],
    spectra_by_id: Mapping[str, ProcessedSpectrum],
    candidates: Mapping[str, StructureCandidate],
    fingerprint_cache: dict[str, np.ndarray],
    spec: FingerprintSpec,
) -> list[AnalogReference]:
    references: list[AnalogReference] = []
    for spectrum_id in spectrum_ids:
        spectrum = spectra_by_id[spectrum_id]
        key = _identity(spectrum.inchikey14)
        candidate = candidates.get(key or "")
        if key is None or candidate is None:
            continue
        references.append(
            AnalogReference(
                reference_id=spectrum_id,
                structure_id=key,
                inchikey14=key,
                neutral_mass=candidate.exact_mass,
                spectrum=spectrum,
                fingerprint=_fingerprint(candidate, fingerprint_cache, spec),
                formula=candidate.formula,
                source=candidate.source,
            )
        )
    if not references:
        raise RuntimeError("Domain analog reference library is empty")
    return references


def _clone_with_analog_score(hit: CandidateHit, score: float) -> CandidateHit:
    return CandidateHit(
        candidate_id=hit.candidate_id,
        smiles=hit.smiles,
        source=hit.source,
        source_rank=hit.source_rank,
        retrieval_score=hit.retrieval_score,
        features={**hit.features, "analog_score": float(score)},
        references_seen=hit.references_seen,
        metadata=dict(hit.metadata),
    )


def _analog_channel_hits(
    analog_hits: Sequence[Any],
    candidates: Mapping[str, StructureCandidate],
    *,
    query_mass: float,
) -> list[CandidateHit]:
    output: list[CandidateHit] = []
    for rank, analog in enumerate(analog_hits, start=1):
        candidate = candidates.get(analog.reference.inchikey14)
        if candidate is None:
            continue
        error = abs(candidate.exact_mass - query_mass) / query_mass * 1e6
        output.append(
            CandidateHit(
                candidate_id=candidate.candidate_id,
                smiles=candidate.smiles,
                source="analog_reference",
                source_rank=rank,
                retrieval_score=float(analog.spectral_similarity),
                features={
                    "mass_error_ppm": float(error),
                    "abs_precursor_delta": abs(candidate.exact_mass - query_mass),
                    "retrieval_score": float(analog.spectral_similarity),
                    "analog_score": float(analog.spectral_similarity),
                },
                metadata={
                    "inchikey14": candidate.candidate_id,
                    "formula": candidate.formula,
                    "exact_mass": candidate.exact_mass,
                    "candidate_channel": "analog_reference",
                },
            )
        )
    return output


def _e6_rank(
    hits: Sequence[CandidateHit],
    *,
    candidate_by_id: Mapping[str, StructureCandidate],
    analog_hits: Sequence[Any],
    query_mass: float,
    fingerprint_cache: dict[str, np.ndarray],
    spec: FingerprintSpec,
    evidence_weight: float,
    expensive_limit: int,
    mass_anchor_order: Sequence[str] | None = None,
) -> list[str]:
    head = list(hits[:expensive_limit])
    analog_candidates = [
        AnalogCandidate(
            candidate_id=hit.candidate_id,
            inchikey14=hit.candidate_id,
            neutral_mass=candidate_by_id[hit.candidate_id].exact_mass,
            fingerprint=_fingerprint(candidate_by_id[hit.candidate_id], fingerprint_cache, spec),
            formula=candidate_by_id[hit.candidate_id].formula,
            smiles=candidate_by_id[hit.candidate_id].smiles,
        )
        for hit in head
    ]
    scores = score_analog_candidates(
        analog_candidates,
        analog_hits,
        query_neutral_mass=query_mass,
    )
    score_by_id = {item.candidate_id: item.score for item in scores}
    annotated = annotate_ranking_context(
        [_clone_with_analog_score(hit, score_by_id[hit.candidate_id]) for hit in head]
    )
    evidence = linear_evidence_ranking(
        annotated,
        evidence_feature="analog_score",
        evidence_weight=evidence_weight,
    )
    evidence.extend(hit.candidate_id for hit in hits[len(head) :])
    mass = (
        list(mass_anchor_order)
        if mass_anchor_order is not None
        else [hit.candidate_id for hit in hits]
    )
    formulas = {
        candidate_id: candidate.formula or ""
        for candidate_id, candidate in candidate_by_id.items()
    }
    return same_anchor_formula_reranking(mass, evidence, formulas)


def _paired_changes(
    truths: Mapping[str, str],
    baseline: Mapping[str, Sequence[str]],
    challenger: Mapping[str, Sequence[str]],
) -> dict[str, int]:
    result = Counter({"improved": 0, "unchanged": 0, "worsened": 0})
    for query_id, truth in truths.items():
        def reciprocal(values: Sequence[str]) -> float:
            rank = next(
                (idx for idx, candidate in enumerate(values[:25], start=1) if candidate == truth),
                None,
            )
            return 0.0 if rank is None else 1.0 / rank

        delta = reciprocal(challenger[query_id]) - reciprocal(baseline[query_id])
        result["improved" if delta > 0 else "worsened" if delta < 0 else "unchanged"] += 1
    return dict(result)


def _mass_anchor_order_for_union(
    mass_hits: Sequence[CandidateHit],
    union_hits: Sequence[CandidateHit],
) -> list[str]:
    """Preserve mass order without introducing IDs absent from the fused pool."""

    allowed = {item.candidate_id for item in union_hits}
    return list(
        dict.fromkeys(
            (
                *(item.candidate_id for item in mass_hits if item.candidate_id in allowed),
                *(item.candidate_id for item in union_hits),
            )
        )
    )


def evaluate_goal5_stage(
    plan: DomainValidationPlan,
    spectra: Sequence[ProcessedSpectrum],
    catalog_tiers: Mapping[str, Sequence[CatalogRecord]],
    *,
    stage: DomainStage,
    config: Goal5ExperimentConfig = Goal5ExperimentConfig(),
) -> dict[str, Any]:
    """Evaluate pre-registered E7-E12 variants on one domain stage."""

    if "C0" not in catalog_tiers or "C1" not in catalog_tiers:
        raise ValueError("Goal 5 requires C0 and C1 catalog tiers")
    spectra_by_id = {item.spectrum_id: item for item in spectra}
    full_c1 = catalog_to_structure_candidates(catalog_tiers["C1"])
    full_candidate_by_id = {item.candidate_id: item for item in full_c1}
    fingerprint_cache: dict[str, np.ndarray] = {}
    spec = FingerprintSpec(n_bits=config.fingerprint_bits)
    condition_results: dict[str, Any] = {}

    for condition in (
        "A_library_visible",
        "B_structure_known_spectra_hidden",
        "C_structure_absent",
    ):
        manifest = plan.manifest(
            condition,
            stage=stage,
            allow_sealed=stage == "sealed",
        )
        allowed = set(manifest.candidate_identity_keys)
        tier_records = {
            name: tuple(record for record in records if record.inchikey14 in allowed)
            for name, records in catalog_tiers.items()
        }
        if not tier_records["C0"] or not tier_records["C1"]:
            raise RuntimeError(f"Empty catalog after {condition} visibility filtering")
        candidates = {
            name: catalog_to_structure_candidates(records)
            for name, records in tier_records.items()
        }
        candidate_maps = {
            name: {item.candidate_id: item for item in values}
            for name, values in candidates.items()
        }
        brute = {name: MassCandidateIndex(list(values)) for name, values in candidates.items()}
        indexed = {
            name: ScalableMassFormulaIndex.build(records, tier_name=name)
            for name, records in tier_records.items()
        }
        references = _build_references(
            manifest.reference_spectrum_ids,
            spectra_by_id,
            full_candidate_by_id,
            fingerprint_cache,
            spec,
        )
        analog_index = ScalableAnalogIndex(references)
        queries: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
        for spectrum_id in manifest.query_spectrum_ids:
            spectrum = spectra_by_id[spectrum_id]
            key = _identity(spectrum.inchikey14)
            if key is None:
                raise RuntimeError(f"Invalid query identity: {spectrum_id}")
            queries[key].append(spectrum)
        truths = {query_id: query_id for query_id in sorted(queries)}
        forbidden_hashes = frozenset(
            spectrum_content_hash(item)
            for values in queries.values()
            for item in values
        )
        forbidden_identities = (
            frozenset() if manifest.same_identity_reference_allowed else frozenset(truths)
        )
        pools: dict[str, dict[str, list[str]]] = {
            name: {} for name in ("E7", "E8", "E9", "E10", "E12")
        }
        rankings: dict[str, dict[str, list[str]]] = {
            name: {} for name in pools
        }
        resources: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"retrieval_seconds": 0.0, "ranking_seconds": 0.0, "candidate_rows": 0}
        )
        analog_reports: dict[str, Any] = {}

        for query_id in sorted(queries):
            query_spectra = sorted(queries[query_id], key=lambda item: item.spectrum_id)
            query_mass = _query_mass(query_spectra)
            policy = LeakagePolicy(
                forbidden_inchikey14=forbidden_identities,
                forbidden_spectrum_hashes=forbidden_hashes,
                query_inchikey14=query_id,
                allow_same_identity=manifest.same_identity_reference_allowed,
            )
            analog_hits, analog_report = analog_index.retrieve(
                query_spectra,
                query_neutral_mass=query_mass,
                policy=policy,
                mass_window_da=config.analog_mass_window_da,
                top_k=config.analog_top_k,
                tolerance_da=config.peak_tolerance_da,
            )
            analog_reports[query_id] = analog_report.to_dict()

            started = time.perf_counter()
            e7 = brute["C0"].retrieve(query_mass, top_k=config.fixed_pool_size)
            resources["E7"]["retrieval_seconds"] += time.perf_counter() - started
            started = time.perf_counter()
            e8 = brute["C1"].retrieve(query_mass, top_k=config.fixed_pool_size)
            resources["E8"]["retrieval_seconds"] += time.perf_counter() - started
            started = time.perf_counter()
            e9 = indexed["C1"].retrieve(query_mass, top_k=config.fixed_pool_size)
            resources["E9"]["retrieval_seconds"] += time.perf_counter() - started
            if [item.candidate_id for item in e8] != [item.candidate_id for item in e9]:
                raise AssertionError("E8 brute and E9 indexed retrieval diverged")
            dynamic_config = DynamicPoolConfig(
                target_pool_size=config.dynamic_pool_size,
                maximum_pool_size=config.dynamic_pool_size,
                cheap_stage_size=min(config.cheap_stage_size, config.dynamic_pool_size),
                expensive_stage_size=min(config.expensive_stage_size, config.dynamic_pool_size),
            )
            started = time.perf_counter()
            e10_pool = retrieve_dynamic_pool(
                indexed["C1"],
                query_mass,
                config=dynamic_config,
                formula_hint=None,
            )
            e10 = list(e10_pool.hits)
            resources["E10"]["retrieval_seconds"] += time.perf_counter() - started
            analog_candidates = _analog_channel_hits(
                analog_hits,
                candidate_maps["C1"],
                query_mass=query_mass,
            )
            started = time.perf_counter()
            e12 = union_candidate_channels(
                (
                    CandidateChannel("exact_mass", e10, 1.0),
                    CandidateChannel("analog", analog_candidates, 1.0),
                ),
                limit=config.dynamic_pool_size,
            )
            resources["E12"]["retrieval_seconds"] += time.perf_counter() - started

            experiment_hits = {
                "E7": e7,
                "E8": e8,
                "E9": e9,
                "E10": e10,
                "E12": e12,
            }
            for experiment, hits in experiment_hits.items():
                pools[experiment][query_id] = [item.candidate_id for item in hits]
                resources[experiment]["candidate_rows"] += len(hits)
                candidate_map = candidate_maps["C0" if experiment == "E7" else "C1"]
                started = time.perf_counter()
                rankings[experiment][query_id] = _e6_rank(
                    hits,
                    candidate_by_id=candidate_map,
                    analog_hits=analog_hits,
                    query_mass=query_mass,
                    fingerprint_cache=fingerprint_cache,
                    spec=spec,
                    evidence_weight=config.evidence_weight,
                    expensive_limit=config.expensive_stage_size,
                    mass_anchor_order=(
                        _mass_anchor_order_for_union(e10, e12)
                        if experiment == "E12"
                        else None
                    ),
                )
                resources[experiment]["ranking_seconds"] += time.perf_counter() - started

        formulas = {
            item.candidate_id: item.formula or ""
            for values in candidates.values()
            for item in values
        }
        truth_formulas = {
            query_id: queries[query_id][0].molecular_formula or ""
            for query_id in truths
        }
        metadata = {
            query_id: {
                "neutral_mass": _query_mass(queries[query_id]),
                "formula": truth_formulas[query_id],
                "adduct": queries[query_id][0].adduct,
                "instrument_type": queries[query_id][0].instrument,
                "source": queries[query_id][0].ingest_lib,
                "spectrum_count": len(queries[query_id]),
            }
            for query_id in truths
        }
        evaluations = {
            experiment: evaluate_retrieval_diagnostics(
                truths,
                pools[experiment],
                rankings[experiment],
                candidate_formula_by_id=formulas,
                truth_formula_by_query=truth_formulas,
                query_metadata=metadata,
            ).to_dict()
            for experiment in rankings
        }
        paired: dict[str, Any] = {}
        for experiment in ("E8", "E9", "E10", "E12"):
            common_pools = {
                query_id: list(
                    dict.fromkeys((*pools["E7"][query_id], *pools[experiment][query_id]))
                )
                for query_id in truths
            }
            paired[experiment] = {
                "vs_E7": bootstrap_paired_ranking_differences(
                    truths,
                    common_pools,
                    rankings["E7"],
                    rankings[experiment],
                    n_bootstrap=config.bootstrap_samples,
                    seed=config.seed,
                ),
                "changes": _paired_changes(truths, rankings["E7"], rankings[experiment]),
            }
        condition_results[condition] = {
            "stage": stage,
            "query_identity_count": len(truths),
            "query_spectrum_count": len(manifest.query_spectrum_ids),
            "reference_spectrum_count": len(references),
            "catalog_sizes": {name: len(values) for name, values in candidates.items()},
            "experiment_descriptions": {
                "E7": "frozen_E6_logic_original_C0_brute_mass_control",
                "E8": "frozen_E6_logic_expanded_C1_brute_mass",
                "E9": "E8_with_exact_index_equivalent_retrieval",
                "E10": "C1_dynamic_pool_with_expensive_E6_head_only",
                "E11": "not_run_no_verified_inference_safe_database_prior",
                "E12": "C1_exact_mass_plus_analog_reference_RRF_union",
            },
            "evaluations": evaluations,
            "paired": paired,
            "resources": {key: dict(value) for key, value in resources.items()},
            "analog_index": {
                "reference_spectra": len(analog_index),
                "reference_identities": analog_index.identity_count,
                "per_query": analog_reports,
            },
        }
    return {
        "stage": stage,
        "conditions": condition_results,
    }


def write_goal5_results(
    output_dir: str | Path,
    *,
    config: Goal5ExperimentConfig,
    plan: DomainValidationPlan,
    collection_report: DomainCollectionReport,
    catalog_reports: Mapping[str, Any],
    domain_audit: Mapping[str, Any],
    domain_diagnostics: Mapping[str, Any],
    frozen_e6: Mapping[str, Any],
    development: Mapping[str, Any],
    sealed: Mapping[str, Any],
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results = {
        "experiment_id": "goal5_scalable_retrieval_v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "domain_plan_hash": plan.manifest_hash,
        "sealed_holdout_commitment": plan.sealed_holdout_commitment,
        "domain_audit": dict(domain_audit),
        "domain_diagnostics": dict(domain_diagnostics),
        "frozen_e6": dict(frozen_e6),
        "collection": collection_report.to_dict(),
        "catalogs": dict(catalog_reports),
        "development": dict(development),
        "sealed": dict(sealed),
        "guardrails": {
            "e6_weight_frozen": config.evidence_weight,
            "large_neural_training": False,
            "official_submission": False,
            "sealed_used_for_tuning": False,
        },
    }
    (output / "goal5_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results
