from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from typing import Any

import numpy as np

from .analog_propagation import (
    AnalogCandidate,
    AnalogReference,
    LeakagePolicy,
    propagate_analog_scores,
    score_analog_candidates,
    spectrum_content_hash,
)
from .benchmark_audit import construct_candidate_catalog
from .chemistry import canonical_inchikey14
from .diagnostics import (
    bootstrap_paired_ranking_differences,
    bootstrap_retrieval_confidence_intervals,
    evaluate_retrieval_diagnostics,
)
from .fingerprints import molecular_fingerprint
from .goal3_contracts import FingerprintSpec
from .goal3_pipeline import (
    Goal3ExperimentConfig,
    _group_queries,
    _identity_key,
    _query_mass,
    collect_goal3_dataset,
)
from .goal3_training import deterministic_group_folds
from .goal4_audit import (
    CandidateDescriptor,
    ConstructionProvenance,
    QueryMetadata,
    audit_realistic_benchmark,
    explain_recall_at_100,
)
from .goal4_ranking import (
    annotate_ranking_context,
    confidence_aware_ranking,
    linear_evidence_ranking,
    reciprocal_rank_fusion,
    same_anchor_formula_reranking,
    tune_confidence_gate,
    tune_evidence_weight,
)
from .isomer_ranking import IsomerAwareRanker
from .leakage import assert_leakage_free
from .mass_retrieval import MassCandidateIndex, StructureCandidate
from .schemas import CandidateHit, ProcessedSpectrum
from .spectral_evidence import (
    aggregate_candidate_scores,
    balanced_acquisition_weights,
    detect_neutral_losses,
    neutral_loss_candidate_compatibility,
)
from .splits import generate_split, spectrum_hash_mapping, spectrum_identity_mapping


NEUTRAL_FEATURE = "neutral_loss_candidate_compatibility"
FRAGMENT_FEATURE = "fragment_analog_compatibility"
ANALOG_FEATURE = "analog_score"
ANALOG_FEATURE_NAMES = (
    "analog_score",
    "analog_mean_top3",
    "analog_best_spectral_similarity",
    "analog_best_structural_similarity",
    "analog_best_neutral_loss_similarity",
    "analog_best_shared_fragment_coverage",
    "analog_mass_alignment",
    "analog_transform_compatibility",
    "analog_adduct_compatibility",
    "analog_same_instrument",
    "analog_reference_count",
)
MULTISPECTRUM_FEATURE_NAMES = (
    "analog_score_mean",
    "analog_score_max",
    "analog_score_weighted",
    "analog_score_confidence_weighted",
    "analog_score_rrf",
)
ANALOG_ABLATION_FEATURE_NAMES = (
    "analog_score_power1",
    "analog_score_power2",
    "analog_score_no_transform",
    "analog_score_no_adduct",
)
RANKER_FEATURE_NAMES = (
    "mass_error_ppm",
    "retrieval_score",
    NEUTRAL_FEATURE,
    FRAGMENT_FEATURE,
    *ANALOG_FEATURE_NAMES,
    *MULTISPECTRUM_FEATURE_NAMES,
    *ANALOG_ABLATION_FEATURE_NAMES,
    "baseline_reciprocal_rank",
    "formula_group_size_goal4",
    "same_as_mass_anchor_formula",
    "mass_confidence_gap_ppm",
)


def _resource_snapshot() -> dict[str, int | None]:
    rss: int | None = None
    peak_rss: int | None = None
    try:
        import psutil

        rss = int(psutil.Process(os.getpid()).memory_info().rss)
    except ImportError:
        pass
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        peak_rss = value * 1024 if value < 10**10 else value
    except ImportError:  # pragma: no cover - unavailable on Windows
        peak_rss = rss
    allocated: int | None = None
    peak_vram: int | None = None
    try:
        import torch

        if torch.cuda.is_available():
            allocated = int(torch.cuda.memory_allocated())
            peak_vram = int(torch.cuda.max_memory_allocated())
    except ImportError:
        pass
    return {
        "rss_bytes": rss,
        "peak_rss_bytes": peak_rss,
        "vram_allocated_bytes": allocated,
        "peak_vram_bytes": peak_vram,
    }


@dataclass(frozen=True, slots=True)
class Goal4ExperimentConfig:
    seed: int = 2026
    max_scan_rows: int = 300_000
    spectra_per_identity: int = 3
    validation_fraction: float = 0.25
    realistic_catalog_size: int = 50_000
    candidate_pool_size: int = 100
    max_peaks: int = 256
    intensity_floor: float = 0.001
    peak_tolerance_da: float = 0.02
    analog_top_k: int = 5
    analog_mass_window_da: float = 200.0
    oof_folds: int = 3
    fingerprint_bits: int = 512
    bootstrap_samples: int = 500
    ranker_backend: str = "lightgbm"


def _clone_with_features(hit: CandidateHit, features: Mapping[str, float]) -> CandidateHit:
    return CandidateHit(
        candidate_id=hit.candidate_id,
        smiles=hit.smiles,
        source=hit.source,
        source_rank=hit.source_rank,
        retrieval_score=hit.retrieval_score,
        features={**hit.features, **features},
        references_seen=hit.references_seen,
        metadata=dict(hit.metadata),
    )


def _candidate_fingerprint(
    candidate: StructureCandidate,
    cache: dict[str, np.ndarray],
    spec: FingerprintSpec,
) -> np.ndarray:
    if candidate.candidate_id not in cache:
        try:
            cache[candidate.candidate_id] = molecular_fingerprint(candidate.smiles, spec)
        except ValueError:
            # A malformed external-catalog structure must not abort the whole
            # run.  The zero vector makes its analog structural evidence
            # explicitly unavailable while mass retrieval remains auditable.
            cache[candidate.candidate_id] = np.zeros(spec.n_bits, dtype=np.float32)
    return cache[candidate.candidate_id]


def _reference_library(
    spectrum_ids: Sequence[str],
    spectra_by_id: Mapping[str, ProcessedSpectrum],
    candidate_by_id: Mapping[str, StructureCandidate],
    fingerprint_cache: dict[str, np.ndarray],
    spec: FingerprintSpec,
) -> list[AnalogReference]:
    references: list[AnalogReference] = []
    for spectrum_id in spectrum_ids:
        spectrum = spectra_by_id[spectrum_id]
        identity = _identity_key(spectrum)
        candidate = candidate_by_id.get(identity)
        if candidate is None:
            continue
        references.append(
            AnalogReference(
                reference_id=spectrum.spectrum_id,
                structure_id=identity,
                inchikey14=identity,
                neutral_mass=candidate.exact_mass,
                spectrum=spectrum,
                fingerprint=_candidate_fingerprint(candidate, fingerprint_cache, spec),
                formula=candidate.formula,
                source=candidate.source,
            )
        )
    if not references:
        raise RuntimeError("Analog reference library is empty")
    return references


def _mass_groups(
    queries: Mapping[str, Sequence[ProcessedSpectrum]],
    index: MassCandidateIndex,
    *,
    pool_size: int,
) -> dict[str, list[CandidateHit]]:
    return {
        query_id: index.retrieve(_query_mass(spectra), top_k=pool_size)
        for query_id, spectra in queries.items()
    }


def _neutral_compatibility(
    spectra: Sequence[ProcessedSpectrum], candidate_formula: str | None, tolerance_da: float
) -> float:
    values: list[float] = []
    for spectrum in spectra:
        losses = detect_neutral_losses(
            spectrum.precursor_mz,
            spectrum.mz,
            spectrum.intensity,
            tolerance_da=tolerance_da,
        )
        values.append(neutral_loss_candidate_compatibility(candidate_formula, losses))
    return float(np.mean(values)) if values else 0.0


def _annotate_query(
    query_id: str,
    query_spectra: Sequence[ProcessedSpectrum],
    hits: Sequence[CandidateHit],
    references: Sequence[AnalogReference],
    candidate_by_id: Mapping[str, StructureCandidate],
    fingerprint_cache: dict[str, np.ndarray],
    spec: FingerprintSpec,
    *,
    forbidden_identities: frozenset[str],
    forbidden_hashes: frozenset[str],
    config: Goal4ExperimentConfig,
) -> tuple[list[CandidateHit], dict[str, Any]]:
    neutral_mass = _query_mass(query_spectra)
    if neutral_mass is None:
        raise RuntimeError(f"Query {query_id} has no inference-safe neutral mass")
    analog_candidates = []
    for hit in hits:
        candidate = candidate_by_id[hit.candidate_id]
        analog_candidates.append(
            AnalogCandidate(
                candidate_id=candidate.candidate_id,
                inchikey14=candidate.candidate_id,
                neutral_mass=candidate.exact_mass,
                fingerprint=_candidate_fingerprint(candidate, fingerprint_cache, spec),
                formula=candidate.formula,
                smiles=candidate.smiles,
            )
        )
    policy = LeakagePolicy(
        forbidden_inchikey14=forbidden_identities,
        forbidden_spectrum_hashes=forbidden_hashes,
        query_inchikey14=query_id,
        allow_same_identity=False,
    )
    candidate_scores, analog_hits = propagate_analog_scores(
        query_spectra,
        analog_candidates,
        references,
        query_neutral_mass=neutral_mass,
        policy=policy,
        mass_window_da=config.analog_mass_window_da,
        top_analogs=config.analog_top_k,
        tolerance_da=config.peak_tolerance_da,
    )
    by_candidate = {item.candidate_id: item for item in candidate_scores}
    ablation_scores = {
        "analog_score_power1": score_analog_candidates(
            analog_candidates,
            analog_hits,
            query_neutral_mass=neutral_mass,
            spectral_power=1.0,
        ),
        "analog_score_power2": score_analog_candidates(
            analog_candidates,
            analog_hits,
            query_neutral_mass=neutral_mass,
            spectral_power=2.0,
        ),
        "analog_score_no_transform": score_analog_candidates(
            analog_candidates,
            analog_hits,
            query_neutral_mass=neutral_mass,
            include_transform=False,
        ),
        "analog_score_no_adduct": score_analog_candidates(
            analog_candidates,
            analog_hits,
            query_neutral_mass=neutral_mass,
            include_adduct=False,
        ),
    }
    ablation_by_candidate = {
        name: {item.candidate_id: item.score for item in values}
        for name, values in ablation_scores.items()
    }
    per_acquisition_rows: list[list[float]] = []
    per_acquisition_confidence: list[float] = []
    for spectrum in query_spectra:
        acquisition_scores, acquisition_hits = propagate_analog_scores(
            [spectrum],
            analog_candidates,
            references,
            query_neutral_mass=neutral_mass,
            policy=policy,
            mass_window_da=config.analog_mass_window_da,
            top_analogs=config.analog_top_k,
            tolerance_da=config.peak_tolerance_da,
        )
        acquisition_by_id = {item.candidate_id: item.score for item in acquisition_scores}
        per_acquisition_rows.append(
            [float(acquisition_by_id[candidate.candidate_id]) for candidate in analog_candidates]
        )
        per_acquisition_confidence.append(
            float(acquisition_hits[0].spectral_similarity) if acquisition_hits else 0.0
        )
    score_matrix = np.asarray(per_acquisition_rows, dtype=np.float64)
    collision_energies = [
        float(np.mean(spectrum.collision_energy_ev))
        if spectrum.collision_energy_ev
        else None
        for spectrum in query_spectra
    ]
    acquisition_weights = balanced_acquisition_weights(
        [spectrum.adduct for spectrum in query_spectra],
        collision_energies,
        quality=[
            float(spectrum.quality.get("retained_fraction", 1.0))
            for spectrum in query_spectra
        ],
    )
    safe_confidence = np.asarray(per_acquisition_confidence, dtype=np.float64)
    if float(safe_confidence.sum()) <= 0.0:
        safe_confidence = np.ones_like(safe_confidence)
    multispectrum = {
        "analog_score_mean": aggregate_candidate_scores(score_matrix, method="mean"),
        "analog_score_max": aggregate_candidate_scores(score_matrix, method="max"),
        "analog_score_weighted": aggregate_candidate_scores(
            score_matrix, method="weighted", weights=acquisition_weights
        ),
        "analog_score_confidence_weighted": aggregate_candidate_scores(
            score_matrix,
            method="confidence_weighted",
            weights=acquisition_weights,
            confidence=safe_confidence,
        ),
        "analog_score_rrf": aggregate_candidate_scores(
            score_matrix, method="rrf", weights=acquisition_weights
        ),
    }
    annotated: list[CandidateHit] = []
    for candidate_index, hit in enumerate(hits):
        candidate = candidate_by_id[hit.candidate_id]
        score = by_candidate[hit.candidate_id]
        neutral = _neutral_compatibility(
            query_spectra, candidate.formula, config.peak_tolerance_da
        )
        fragment = (
            float(score.features["analog_best_spectral_similarity"])
            * float(score.features["analog_best_structural_similarity"])
            * float(score.features["analog_best_shared_fragment_coverage"])
        )
        annotated.append(
            _clone_with_features(
                hit,
                {
                    **{name: float(score.features[name]) for name in ANALOG_FEATURE_NAMES},
                    **{
                        name: float(values[candidate_index])
                        for name, values in multispectrum.items()
                    },
                    **{
                        name: float(values[hit.candidate_id])
                        for name, values in ablation_by_candidate.items()
                    },
                    NEUTRAL_FEATURE: neutral,
                    FRAGMENT_FEATURE: fragment,
                },
            )
        )
    spectral_values = [item.spectral_similarity for item in analog_hits]
    best = spectral_values[0] if spectral_values else 0.0
    second = spectral_values[1] if len(spectral_values) > 1 else 0.0
    confidence = float(best * (0.5 + 0.5 * max(0.0, best - second)))
    return annotate_ranking_context(annotated), {
        "query_id": query_id,
        "reference_count": len(references),
        "analog_hit_count": len(analog_hits),
        "best_analog_similarity": best,
        "best_vs_second_margin": max(0.0, best - second),
        "analog_confidence": confidence,
        "multi_spectrum": {
            "acquisition_count": len(query_spectra),
            "balanced_weights": acquisition_weights.tolist(),
            "per_acquisition_confidence": per_acquisition_confidence,
        },
        "top_analogs": [
            {
                "reference_id": item.reference.reference_id,
                "reference_identity": item.reference.inchikey14,
                "spectral_similarity": item.spectral_similarity,
                "modified_cosine": item.modified_cosine,
                "entropy_similarity": item.entropy_similarity,
                "neutral_loss_similarity": item.neutral_loss_similarity,
            }
            for item in analog_hits[:5]
        ],
    }


def _annotate_groups(
    queries: Mapping[str, Sequence[ProcessedSpectrum]],
    mass_groups: Mapping[str, Sequence[CandidateHit]],
    references: Sequence[AnalogReference],
    candidate_by_id: Mapping[str, StructureCandidate],
    fingerprint_cache: dict[str, np.ndarray],
    spec: FingerprintSpec,
    *,
    forbidden_identities: frozenset[str],
    config: Goal4ExperimentConfig,
) -> tuple[dict[str, list[CandidateHit]], dict[str, dict[str, Any]]]:
    forbidden_hashes = frozenset(
        spectrum_content_hash(spectrum)
        for spectra in queries.values()
        for spectrum in spectra
    )
    groups: dict[str, list[CandidateHit]] = {}
    reports: dict[str, dict[str, Any]] = {}
    for query_id in sorted(queries):
        groups[query_id], reports[query_id] = _annotate_query(
            query_id,
            queries[query_id],
            mass_groups[query_id],
            references,
            candidate_by_id,
            fingerprint_cache,
            spec,
            forbidden_identities=forbidden_identities,
            forbidden_hashes=forbidden_hashes,
            config=config,
        )
    return groups, reports


def _oof_training_groups(
    train_queries: Mapping[str, Sequence[ProcessedSpectrum]],
    train_mass_groups: Mapping[str, Sequence[CandidateHit]],
    all_references: Sequence[AnalogReference],
    candidate_by_id: Mapping[str, StructureCandidate],
    fingerprint_cache: dict[str, np.ndarray],
    spec: FingerprintSpec,
    config: Goal4ExperimentConfig,
) -> tuple[dict[str, list[CandidateHit]], dict[str, Any]]:
    fold_by_identity = deterministic_group_folds(
        list(train_queries), n_folds=config.oof_folds, seed=config.seed
    )
    result: dict[str, list[CandidateHit]] = {}
    reports: dict[str, Any] = {}
    for fold in range(config.oof_folds):
        fold_queries = {
            key: value for key, value in train_queries.items() if fold_by_identity[key] == fold
        }
        held_identities = frozenset(fold_queries)
        fold_references = [
            reference
            for reference in all_references
            if reference.inchikey14 not in held_identities
        ]
        fold_groups, fold_reports = _annotate_groups(
            fold_queries,
            {key: train_mass_groups[key] for key in fold_queries},
            fold_references,
            candidate_by_id,
            fingerprint_cache,
            spec,
            forbidden_identities=held_identities,
            config=config,
        )
        result.update(fold_groups)
        reports.update(fold_reports)
    if set(result) != set(train_queries):
        raise AssertionError("Each training identity must receive exactly one OOF annotation")
    return result, {"fold_by_identity": fold_by_identity, "query_reports": reports}


def _mass_rankings(groups: Mapping[str, Sequence[CandidateHit]]) -> dict[str, list[str]]:
    return {
        query_id: [
            hit.candidate_id
            for hit in sorted(
                hits,
                key=lambda item: (
                    float(item.features["mass_error_ppm"]),
                    item.candidate_id,
                ),
            )
        ]
        for query_id, hits in groups.items()
    }


def _per_query_change_counts(
    truths: Mapping[str, str],
    baseline: Mapping[str, Sequence[str]],
    challenger: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    improved: list[str] = []
    worsened: list[str] = []
    unchanged: list[str] = []
    for query_id, truth in truths.items():
        def rr(ranking: Sequence[str]) -> float:
            rank = next(
                (idx for idx, candidate in enumerate(ranking[:25], start=1) if candidate == truth),
                None,
            )
            return 0.0 if rank is None else 1.0 / rank

        delta = rr(challenger[query_id]) - rr(baseline[query_id])
        (improved if delta > 0 else worsened if delta < 0 else unchanged).append(query_id)
    return {
        "improved_count": len(improved),
        "worsened_count": len(worsened),
        "unchanged_count": len(unchanged),
        "improved_query_ids": improved,
        "worsened_query_ids": worsened,
    }


def _evaluate_experiments(
    truths: Mapping[str, str],
    pools: Mapping[str, Sequence[str]],
    rankings: Mapping[str, Mapping[str, Sequence[str]]],
    *,
    model_selection_keys: set[str],
    final_keys: set[str],
    formula_by_candidate: Mapping[str, str],
    truth_formula: Mapping[str, str],
    query_metadata: Mapping[str, Mapping[str, Any]],
    config: Goal4ExperimentConfig,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    stages = {
        "all_validation": set(truths),
        "model_selection": model_selection_keys,
        "final_evaluation": final_keys,
    }
    for stage, keys in stages.items():
        stage_truths = {key: truths[key] for key in sorted(keys)}
        stage_pools = {key: list(pools[key]) for key in stage_truths}
        baseline = {key: list(rankings["E0"][key]) for key in stage_truths}
        stage_result: dict[str, Any] = {}
        for experiment_id, values in rankings.items():
            selected = {key: list(values[key]) for key in stage_truths}
            diagnostics = evaluate_retrieval_diagnostics(
                stage_truths,
                stage_pools,
                selected,
                candidate_formula_by_id=formula_by_candidate,
                truth_formula_by_query={key: truth_formula[key] for key in stage_truths},
                query_metadata={key: query_metadata[key] for key in stage_truths},
            )
            evaluation: dict[str, Any] = {
                "metrics": diagnostics.to_dict(),
                "confidence_intervals": bootstrap_retrieval_confidence_intervals(
                    stage_truths,
                    stage_pools,
                    selected,
                    candidate_formula_by_id=formula_by_candidate,
                    truth_formula_by_query={key: truth_formula[key] for key in stage_truths},
                    n_bootstrap=config.bootstrap_samples,
                    seed=config.seed,
                ),
            }
            if experiment_id != "E0":
                evaluation["paired_delta_vs_E0"] = bootstrap_paired_ranking_differences(
                    stage_truths,
                    stage_pools,
                    baseline,
                    selected,
                    n_bootstrap=config.bootstrap_samples,
                    seed=config.seed,
                )
                evaluation["query_changes_vs_E0"] = _per_query_change_counts(
                    stage_truths, baseline, selected
                )
            stage_result[experiment_id] = evaluation
        output[stage] = stage_result
    return output


def run_goal4_experiment(
    train_path: str | Path,
    frozen_identity_path: str | Path,
    output_dir: str | Path,
    *,
    config: Goal4ExperimentConfig = Goal4ExperimentConfig(),
) -> dict[str, Any]:
    """Run Goal 4 E0-E7 on a fixed target-blind top-100 candidate pool."""

    started = time.perf_counter()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stage_resources: dict[str, Any] = {}
    collection_started = time.perf_counter()
    collection_config = Goal3ExperimentConfig(
        seed=config.seed,
        max_scan_rows=config.max_scan_rows,
        spectra_per_identity=config.spectra_per_identity,
        validation_fraction=config.validation_fraction,
        realistic_catalog_size=config.realistic_catalog_size,
        candidate_pool_size=config.candidate_pool_size,
        max_peaks=config.max_peaks,
        intensity_floor=config.intensity_floor,
        peak_tolerance_da=config.peak_tolerance_da,
        bootstrap_samples=config.bootstrap_samples,
        fingerprint_bits=config.fingerprint_bits,
        fingerprint_folds=config.oof_folds,
    )
    dataset = collect_goal3_dataset(train_path, frozen_identity_path, collection_config)
    stage_resources["dataset_collection"] = {
        "elapsed_seconds": time.perf_counter() - collection_started,
        **_resource_snapshot(),
    }
    spectra = list(dataset.spectra)
    spectra_by_id = {spectrum.spectrum_id: spectrum for spectrum in spectra}
    manifest = generate_split(
        "molecule_disjoint",
        spectra,
        validation_fraction=config.validation_fraction,
        seed=config.seed,
        candidate_identity_keys=dataset.source_candidate_ids,
    )
    manifest.save(output / "goal4_molecule_disjoint_manifest.json")
    leakage_report = assert_leakage_free(
        manifest,
        spectrum_identity_keys=spectrum_identity_mapping(spectra),
        spectrum_hashes=spectrum_hash_mapping(spectra),
        ranker_train_spectrum_ids=manifest.train_spectrum_ids,
        feature_provenance={
            NEUTRAL_FEATURE: "query_spectrum_and_candidate_formula_only",
            FRAGMENT_FEATURE: "identity_oof_analog_spectrum_and_candidate_structure",
            ANALOG_FEATURE: "identity_oof_analog_spectrum_and_candidate_structure",
        },
    )
    catalog_trace = construct_candidate_catalog(
        dataset.source_candidate_ids,
        mode="realistic",
        max_size=config.realistic_catalog_size,
        controlled_target_ids=(),
    )
    source_by_id = {candidate.candidate_id: candidate for candidate in dataset.source_catalog}
    selected_catalog = [
        source_by_id[candidate_id] for candidate_id in catalog_trace.candidate_ids
    ]
    catalog = [
        candidate
        for candidate in selected_catalog
        if canonical_inchikey14(candidate.smiles) == candidate.candidate_id
    ]
    canonical_mismatch_count = len(selected_catalog) - len(catalog)
    if not set(manifest.validation_identity_keys) <= {
        candidate.candidate_id for candidate in catalog
    }:
        raise RuntimeError("Canonical catalog filtering removed a frozen validation target")
    candidate_by_id = {candidate.candidate_id: candidate for candidate in catalog}
    mass_index = MassCandidateIndex(catalog)
    train_queries = _group_queries(manifest.train_spectrum_ids, spectra_by_id)
    validation_queries = _group_queries(manifest.validation_spectrum_ids, spectra_by_id)
    candidate_started = time.perf_counter()
    train_mass_groups = _mass_groups(
        train_queries, mass_index, pool_size=config.candidate_pool_size
    )
    validation_mass_groups = _mass_groups(
        validation_queries, mass_index, pool_size=config.candidate_pool_size
    )
    stage_resources["mass_candidate_generation"] = {
        "elapsed_seconds": time.perf_counter() - candidate_started,
        "train_query_count": len(train_queries),
        "validation_query_count": len(validation_queries),
        "candidate_pool_size": config.candidate_pool_size,
        **_resource_snapshot(),
    }
    spectral_started = time.perf_counter()
    fingerprint_cache: dict[str, np.ndarray] = {}
    fingerprint_spec = FingerprintSpec(n_bits=config.fingerprint_bits)
    references = _reference_library(
        manifest.reference_spectrum_ids,
        spectra_by_id,
        candidate_by_id,
        fingerprint_cache,
        fingerprint_spec,
    )
    train_groups, train_analog_report = _oof_training_groups(
        train_queries,
        train_mass_groups,
        references,
        candidate_by_id,
        fingerprint_cache,
        fingerprint_spec,
        config,
    )
    validation_groups, validation_analog_report = _annotate_groups(
        validation_queries,
        validation_mass_groups,
        references,
        candidate_by_id,
        fingerprint_cache,
        fingerprint_spec,
        forbidden_identities=frozenset(validation_queries),
        config=config,
    )
    stage_resources["spectral_and_analog_feature_generation"] = {
        "elapsed_seconds": time.perf_counter() - spectral_started,
        "annotated_candidate_rows": sum(map(len, train_groups.values()))
        + sum(map(len, validation_groups.values())),
        **_resource_snapshot(),
    }
    truths = {query_id: query_id for query_id in validation_queries}
    model_selection_keys = set(manifest.metadata["model_selection_identity_keys"])
    final_keys = set(manifest.metadata["final_evaluation_identity_keys"])
    selection_truths = {key: key for key in model_selection_keys}
    selection_groups = {key: validation_groups[key] for key in model_selection_keys}
    experiment_resources: dict[str, Any] = {}
    experiment_started = time.perf_counter()
    rankings: dict[str, dict[str, list[str]]] = {"E0": _mass_rankings(validation_groups)}
    experiment_resources["E0"] = {
        "inference_seconds": time.perf_counter() - experiment_started,
        "fit_seconds": 0.0,
    }
    selection: dict[str, Any] = {}
    descriptions = {
        "E0": "nearest_mass_fixed_top100",
        "E1": "mass_plus_candidate_formula_neutral_loss_compatibility",
        "E2": "mass_plus_analog_linked_fragment_compatibility",
        "E3": "mass_plus_analog_propagation",
        "E4": "reciprocal_rank_fusion_E0_E1_E2_E3",
        "E5": "identity_oof_lightgbm_lambdarank",
        "E6": "inference_safe_mass_anchor_same_formula_reranking",
        "E7": "confidence_gated_E3_vs_E0",
    }
    for experiment_id, feature in (
        ("E1", NEUTRAL_FEATURE),
        ("E2", FRAGMENT_FEATURE),
    ):
        experiment_started = time.perf_counter()
        chosen = tune_evidence_weight(
            selection_truths,
            selection_groups,
            evidence_feature=feature,
        )
        selection[experiment_id] = asdict(chosen)
        rankings[experiment_id] = {
            query_id: linear_evidence_ranking(
                hits,
                evidence_feature=feature,
                evidence_weight=chosen.weight,
            )
            for query_id, hits in validation_groups.items()
        }
        experiment_resources[experiment_id] = {
            "selection_and_inference_seconds": time.perf_counter() - experiment_started,
            "fit_seconds": 0.0,
        }
    experiment_started = time.perf_counter()
    aggregation_trials: dict[str, Any] = {}
    aggregation_selections = {}
    for feature in (
        ANALOG_FEATURE,
        *MULTISPECTRUM_FEATURE_NAMES,
        *ANALOG_ABLATION_FEATURE_NAMES,
    ):
        chosen = tune_evidence_weight(
            selection_truths,
            selection_groups,
            evidence_feature=feature,
        )
        aggregation_selections[feature] = chosen
        aggregation_trials[feature] = asdict(chosen)
    selected_aggregation = max(
        aggregation_selections,
        key=lambda feature: (
            aggregation_selections[feature].mrr_at_25,
            -list(
                (
                    ANALOG_FEATURE,
                    *MULTISPECTRUM_FEATURE_NAMES,
                    *ANALOG_ABLATION_FEATURE_NAMES,
                )
            ).index(feature),
        ),
    )
    selected_analog = aggregation_selections[selected_aggregation]
    selection["E3"] = {
        "selected_aggregation_feature": selected_aggregation,
        "selected_weight": selected_analog.weight,
        "model_selection_mrr_at_25": selected_analog.mrr_at_25,
        "aggregation_trials": aggregation_trials,
    }
    rankings["E3"] = {
        query_id: linear_evidence_ranking(
            hits,
            evidence_feature=selected_aggregation,
            evidence_weight=selected_analog.weight,
        )
        for query_id, hits in validation_groups.items()
    }
    experiment_resources["E3"] = {
        "selection_and_inference_seconds": time.perf_counter() - experiment_started,
        "fit_seconds": 0.0,
    }
    experiment_started = time.perf_counter()
    rankings["E4"] = {
        query_id: reciprocal_rank_fusion(
            [
                rankings["E0"][query_id],
                rankings["E1"][query_id],
                rankings["E2"][query_id],
                rankings["E3"][query_id],
            ]
        )
        for query_id in truths
    }
    experiment_resources["E4"] = {
        "inference_seconds": time.perf_counter() - experiment_started,
        "fit_seconds": 0.0,
    }
    fit_started = time.perf_counter()
    ranker = IsomerAwareRanker(
        RANKER_FEATURE_NAMES,
        backend=config.ranker_backend,
        random_state=config.seed,
    )
    ranker_summary = ranker.fit(train_groups, {key: key for key in train_groups})
    fit_seconds = time.perf_counter() - fit_started
    inference_started = time.perf_counter()
    rankings["E5"] = {
        query_id: [item.candidate_id for item in ranker.rank(hits)]
        for query_id, hits in validation_groups.items()
    }
    experiment_resources["E5"] = {
        "fit_seconds": fit_seconds,
        "inference_seconds": time.perf_counter() - inference_started,
    }
    formula_by_candidate = {
        candidate.candidate_id: candidate.formula or "" for candidate in catalog
    }
    experiment_started = time.perf_counter()
    rankings["E6"] = {
        query_id: same_anchor_formula_reranking(
            rankings["E0"][query_id],
            rankings["E3"][query_id],
            formula_by_candidate,
        )
        for query_id in truths
    }
    experiment_resources["E6"] = {
        "inference_seconds": time.perf_counter() - experiment_started,
        "fit_seconds": 0.0,
    }
    confidence = {
        query_id: float(report["analog_confidence"])
        for query_id, report in validation_analog_report.items()
    }
    experiment_started = time.perf_counter()
    gate = tune_confidence_gate(
        selection_truths,
        {key: rankings["E0"][key] for key in model_selection_keys},
        {key: rankings["E3"][key] for key in model_selection_keys},
        {key: confidence[key] for key in model_selection_keys},
    )
    selection["E7"] = asdict(gate)
    rankings["E7"] = {
        query_id: confidence_aware_ranking(
            rankings["E0"][query_id],
            rankings["E3"][query_id],
            confidence=confidence[query_id],
            threshold=gate.threshold,
        )
        for query_id in truths
    }
    experiment_resources["E7"] = {
        "selection_and_inference_seconds": time.perf_counter() - experiment_started,
        "fit_seconds": 0.0,
    }
    pools = {
        query_id: [hit.candidate_id for hit in hits]
        for query_id, hits in validation_mass_groups.items()
    }
    truth_formula = {
        query_id: validation_queries[query_id][0].molecular_formula or ""
        for query_id in truths
    }
    diagnostic_metadata = {
        query_id: {
            "neutral_mass": _query_mass(spectra_for_query),
            "formula": truth_formula[query_id],
            "adduct": spectra_for_query[0].adduct,
            "instrument_type": spectra_for_query[0].instrument,
            "source": spectra_for_query[0].ingest_lib,
            "spectrum_count": len(spectra_for_query),
        }
        for query_id, spectra_for_query in validation_queries.items()
    }
    evaluations = _evaluate_experiments(
        truths,
        pools,
        rankings,
        model_selection_keys=model_selection_keys,
        final_keys=final_keys,
        formula_by_candidate=formula_by_candidate,
        truth_formula=truth_formula,
        query_metadata=diagnostic_metadata,
        config=config,
    )
    descriptors = {
        candidate.candidate_id: CandidateDescriptor(
            candidate_id=candidate.candidate_id,
            identity_key=candidate.candidate_id,
            exact_mass=candidate.exact_mass,
            formula=candidate.formula,
            source_set=(candidate.source,),
        )
        for candidate in catalog
    }
    provenance = ConstructionProvenance(
        mode="realistic",
        catalog_selection_policy="target_blind_seeded_hash_order_train_metadata_only",
        catalog_source_count=len(dataset.source_candidate_ids),
        catalog_selected_count=len(catalog),
        pool_target_consulted={key: False for key in truths},
        pool_target_injected={key: False for key in truths},
    )
    audit = audit_realistic_benchmark(
        truth_keys=truths,
        catalog_candidate_ids=[candidate.candidate_id for candidate in catalog],
        candidate_pools=pools,
        rankings=rankings["E0"],
        candidates=descriptors,
        query_metadata={
            query_id: QueryMetadata(
                neutral_mass=_query_mass(values),
                formula=truth_formula[query_id],
                adduct=values[0].adduct,
                instrument=values[0].instrument or "<missing>",
                spectrum_count=len(values),
                source=values[0].ingest_lib or "<missing>",
            )
            for query_id, values in validation_queries.items()
        },
        provenance=provenance,
    )
    development_scores = {
        experiment_id: values["metrics"]["mrr_at_25"]
        for experiment_id, values in evaluations["model_selection"].items()
    }
    selected_experiment = max(
        development_scores,
        key=lambda experiment_id: (
            development_scores[experiment_id],
            -int(experiment_id[1:]),
        ),
    )
    results = {
        "experiment_id": "goal4_spectral_ranking_v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "dataset": dataset.metadata,
        "canonical_catalog": {
            "selected_before_validation": len(selected_catalog),
            "valid_structure_count": len(catalog),
            "identity_mismatch_count": canonical_mismatch_count,
            "rule": "rdkit_2026_03_3_tautomer_canonical_inchikey14_matches_provided_key",
        },
        "manifest_hash": manifest.manifest_hash,
        "leakage_audit": leakage_report.to_dict(),
        "benchmark_audit": audit.to_dict(),
        "recall_at_100_explanation": explain_recall_at_100(audit),
        "fixed_candidate_pool": {
            "size": config.candidate_pool_size,
            "generator": "nearest_neutral_mass_target_blind_catalog",
            "same_for_all_experiments": True,
        },
        "feature_contract": {
            "spectrum_only_not_used_for_candidate_ranking": True,
            "candidate_specific_features": list(RANKER_FEATURE_NAMES),
            "ranker_feature_names": list(RANKER_FEATURE_NAMES),
        },
        "experiment_descriptions": descriptions,
        "model_selection": selection,
        "ranker_training": ranker_summary,
        "resources": {
            "stages": stage_resources,
            "experiments": experiment_resources,
            "final_snapshot": _resource_snapshot(),
        },
        "analog_oof": train_analog_report,
        "analog_validation": validation_analog_report,
        "evaluations": evaluations,
        "selected_by_model_selection": selected_experiment,
        "selected_final_evaluation": evaluations["final_evaluation"][selected_experiment],
        "elapsed_seconds": time.perf_counter() - started,
    }
    (output / "goal4_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results
