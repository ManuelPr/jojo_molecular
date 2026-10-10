from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

import numpy as np

from .benchmark_audit import (
    assert_realistic_candidate_integrity,
    audit_candidate_pools,
    calibration_diagnostics,
    candidate_prior_diagnostics,
    construct_candidate_catalog,
    construct_candidate_pool,
    feature_drift_diagnostics,
    model_importance_diagnostics,
    rank_shift_diagnostics,
    ranking_breakdowns,
)
from .chemistry import (
    canonical_inchikey14,
    exact_mass_from_formula,
    exact_mass_from_smiles,
    rdkit_version,
)
from .data import ParquetSpectrumReader, PreprocessConfig, preprocess_spectrum
from .diagnostics import (
    bootstrap_paired_ranking_differences,
    bootstrap_retrieval_confidence_intervals,
    evaluate_retrieval_diagnostics,
)
from .fingerprints import (
    FingerprintKNNBaseline,
    fingerprint_batch,
    fingerprint_metrics,
    molecular_fingerprint,
)
from .goal3_contracts import CandidatePoolMode, FingerprintSpec
from .goal3_training import (
    FingerprintTrainingConfig,
    deterministic_group_folds,
    oof_fingerprint_predictions,
)
from .isomer_ranking import (
    CHEMISTRY_CONTEXT_FEATURE_NAMES,
    FP_FEATURE_NAMES,
    IsomerAwareRanker,
    annotate_fingerprint_features,
    mine_hard_negatives,
)
from .leakage import assert_leakage_free
from .mass_retrieval import MassCandidateIndex, StructureCandidate, merge_candidate_hits
from .ranking import SupervisedRanker
from .retrieval import FEATURE_NAMES, SpectralLibraryIndex
from .schemas import CandidateHit, LibraryEntry, ProcessedSpectrum
from .splits import generate_split, spectrum_hash_mapping, spectrum_identity_mapping


@dataclass(frozen=True, slots=True)
class Goal3ExperimentConfig:
    seed: int = 2026
    max_scan_rows: int = 300_000
    spectra_per_identity: int = 3
    validation_fraction: float = 0.25
    controlled_catalog_size: int = 4096
    realistic_catalog_size: int = 50_000
    candidate_pool_size: int = 1000
    max_peaks: int = 256
    intensity_floor: float = 0.001
    mass_tolerance_ppm: float = 20.0
    peak_tolerance_da: float = 0.02
    bootstrap_samples: int = 500
    fingerprint_bits: int = 512
    fingerprint_folds: int = 3
    fingerprint_epochs: int = 12
    fingerprint_batch_size: int = 16
    hard_negatives_per_query: int = 64
    device: str | None = None


@dataclass(frozen=True, slots=True)
class Goal3Dataset:
    spectra: tuple[ProcessedSpectrum, ...]
    source_catalog: tuple[StructureCandidate, ...]
    source_candidate_ids: tuple[str, ...]
    frozen_identity_keys: tuple[str, ...]
    metadata: dict[str, Any]


def _identity_key(spectrum: ProcessedSpectrum) -> str:
    key = spectrum.inchikey14 or canonical_inchikey14(spectrum.normalized_smiles or "")
    if key is None:
        raise ValueError(f"Missing identity for {spectrum.spectrum_id}")
    return str(key).strip().upper()


def _read_frozen_identities(path: str | Path) -> tuple[str, ...]:
    values = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        value = line.strip().upper()
        if len(value) == 14 and value.isalpha():
            values.append(value)
    result = tuple(sorted(set(values)))
    if len(result) < 8:
        raise ValueError("Frozen cohort must contain at least eight InChIKey14 identities")
    return result


def collect_goal3_dataset(
    train_path: str | Path,
    frozen_identity_path: str | Path,
    config: Goal3ExperimentConfig,
) -> Goal3Dataset:
    """Collect the frozen cohort and a target-blind structure database.

    Only the frozen cohort is canonicalized with the expensive official
    tautomer procedure. The candidate database uses the competition-provided
    normalized SMILES/InChIKey14 pair and records this provenance explicitly.
    """

    frozen = _read_frozen_identities(frozen_identity_path)
    reader = ParquetSpectrumReader(train_path)
    metadata_columns = [
        name
        for name in (
            "inchikey14",
            "normalized_smiles",
            "molecular_formula",
            "ingest_lib",
        )
        if name in reader.schema.names
    ]
    counts: Counter[str] = Counter()
    structure_metadata: dict[str, tuple[str, str | None, str | None]] = {}
    for record in reader.iter_records(
        max_rows=config.max_scan_rows,
        columns=metadata_columns,
    ):
        if record.inchikey14 is None or record.normalized_smiles is None:
            continue
        key = str(record.inchikey14).strip().upper()
        if len(key) != 14 or not key.isalpha():
            continue
        counts[key] += 1
        structure_metadata.setdefault(
            key,
            (record.normalized_smiles, record.molecular_formula, record.ingest_lib),
        )

    missing = [key for key in frozen if key not in structure_metadata]
    insufficient = [key for key in frozen if counts[key] < config.spectra_per_identity]
    if missing or insufficient:
        raise RuntimeError(
            f"Frozen cohort unavailable within scan: missing={missing[:5]}, "
            f"insufficient={insufficient[:5]}"
        )
    for key in frozen:
        if canonical_inchikey14(structure_metadata[key][0]) != key:
            raise ValueError(f"Frozen identity/SMILES mismatch: {key}")

    # The order is target-blind and stable. Controlled selection may later
    # reorder this source through an explicit, audited trace.
    source_ids = tuple(
        sorted(
            structure_metadata,
            key=lambda key: (
                hashlib.sha256(f"goal3-catalog\0{config.seed}\0{key}".encode()).digest(),
                key,
            ),
        )
    )
    catalog: list[StructureCandidate] = []
    invalid_mass_count = 0
    for key in source_ids:
        smiles, formula, source = structure_metadata[key]
        exact_mass = exact_mass_from_formula(formula or "")
        if exact_mass is None:
            exact_mass = exact_mass_from_smiles(smiles)
        if exact_mass is None:
            invalid_mass_count += 1
            continue
        catalog.append(
            StructureCandidate(
                candidate_id=key,
                smiles=smiles,
                exact_mass=exact_mass,
                formula=formula,
                source=source or "train_structure_catalog",
            )
        )
    available_keys = {candidate.candidate_id for candidate in catalog}
    if not set(frozen) <= available_keys:
        raise RuntimeError("Frozen targets are missing valid exact masses")

    preprocessing = PreprocessConfig(
        intensity_floor=config.intensity_floor,
        max_peaks=config.max_peaks,
    )
    spectra: list[ProcessedSpectrum] = []
    retained: Counter[str] = Counter()
    frozen_set = set(frozen)
    for record in reader.iter_records(max_rows=config.max_scan_rows):
        key = "" if record.inchikey14 is None else str(record.inchikey14).strip().upper()
        if key not in frozen_set or retained[key] >= config.spectra_per_identity:
            continue
        spectrum = preprocess_spectrum(record, preprocessing)
        if not spectrum.mz.size:
            continue
        spectra.append(spectrum)
        retained[key] += 1
        if all(retained[key] >= config.spectra_per_identity for key in frozen):
            break
    if any(retained[key] < config.spectra_per_identity for key in frozen):
        raise RuntimeError("Frozen cohort did not survive preprocessing")
    return Goal3Dataset(
        spectra=tuple(sorted(spectra, key=lambda item: item.spectrum_id)),
        source_catalog=tuple(catalog),
        source_candidate_ids=tuple(candidate.candidate_id for candidate in catalog),
        frozen_identity_keys=frozen,
        metadata={
            "scan_rows": config.max_scan_rows,
            "source_unique_structure_count": len(structure_metadata),
            "valid_mass_structure_count": len(catalog),
            "invalid_mass_structure_count": invalid_mass_count,
            "identity_provenance": "competition_provided_normalized_smiles_and_inchikey14",
            "frozen_identity_count": len(frozen),
            "spectrum_count": len(spectra),
        },
    )


def _group_queries(
    spectrum_ids: Sequence[str],
    spectra_by_id: Mapping[str, ProcessedSpectrum],
) -> dict[str, list[ProcessedSpectrum]]:
    grouped: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    for spectrum_id in spectrum_ids:
        spectrum = spectra_by_id[spectrum_id]
        grouped[_identity_key(spectrum)].append(spectrum)
    return {
        key: sorted(values, key=lambda item: item.spectrum_id)
        for key, values in grouped.items()
    }


def _query_mass(spectra: Sequence[ProcessedSpectrum]) -> float | None:
    masses = [
        float(spectrum.neutral_mass)
        for spectrum in spectra
        if spectrum.neutral_mass is not None and math.isfinite(float(spectrum.neutral_mass))
    ]
    return float(np.median(masses)) if masses else None


def _target_hit(
    target: StructureCandidate,
    query_spectra: Sequence[ProcessedSpectrum],
) -> CandidateHit:
    query_mass = _query_mass(query_spectra)
    error = (
        abs(target.exact_mass - query_mass) / query_mass * 1e6
        if query_mass is not None and query_mass > 0
        else 1_000_000.0
    )
    features = {name: 0.0 for name in FEATURE_NAMES}
    features.update(
        {
            "mass_error_ppm": float(error),
            "abs_precursor_delta": abs((query_mass or target.exact_mass) - target.exact_mass),
            "retrieval_score": float(1.0 / (1.0 + error)),
        }
    )
    return CandidateHit(
        candidate_id=target.candidate_id,
        smiles=target.smiles,
        source="controlled_oracle_backstop",
        source_rank=0,
        retrieval_score=features["retrieval_score"],
        features=features,
        metadata={
            "formula": target.formula,
            "exact_mass": target.exact_mass,
            "candidate_channel": "controlled_oracle_backstop",
            "oracle_injected": True,
        },
    )


def _retrieve_group(
    query_id: str,
    query_spectra: Sequence[ProcessedSpectrum],
    mass_index: MassCandidateIndex,
    spectral_index: SpectralLibraryIndex,
    candidate_by_id: Mapping[str, StructureCandidate],
    *,
    mode: CandidatePoolMode,
    pool_size: int,
) -> tuple[list[CandidateHit], list[CandidateHit], Any]:
    mass_hits = mass_index.retrieve(_query_mass(query_spectra), top_k=pool_size)
    spectral_hits = spectral_index.retrieve_many(list(query_spectra), top_k=pool_size)
    union_hits = merge_candidate_hits(mass_hits, spectral_hits, top_k=pool_size)
    trace = construct_candidate_pool(
        query_id,
        [hit.candidate_id for hit in union_hits],
        mode=mode,
        max_size=pool_size,
        controlled_target_id=query_id,
    )
    if trace.target_was_injected:
        target = candidate_by_id.get(query_id)
        if target is None:
            raise RuntimeError(f"Controlled target {query_id} missing from catalog")
        union_hits = [hit for hit in union_hits if hit.candidate_id != query_id]
        if len(union_hits) >= pool_size:
            union_hits = union_hits[: pool_size - 1]
        union_hits.append(_target_hit(target, query_spectra))
    final_ids = tuple(hit.candidate_id for hit in union_hits)
    if final_ids != trace.final_candidate_ids:
        raise AssertionError("Candidate-hit construction diverged from audited pool trace")
    return mass_hits, union_hits, trace


def _catalog_for_mode(
    dataset: Goal3Dataset,
    mode: CandidatePoolMode,
    config: Goal3ExperimentConfig,
) -> tuple[list[StructureCandidate], Any]:
    max_size = (
        config.controlled_catalog_size
        if mode == "controlled"
        else config.realistic_catalog_size
    )
    trace = construct_candidate_catalog(
        dataset.source_candidate_ids,
        mode=mode,
        max_size=max_size,
        controlled_target_ids=dataset.frozen_identity_keys,
    )
    by_id = {candidate.candidate_id: candidate for candidate in dataset.source_catalog}
    return [by_id[key] for key in trace.candidate_ids], trace


def _library_entries(
    spectrum_ids: Sequence[str],
    spectra_by_id: Mapping[str, ProcessedSpectrum],
) -> list[LibraryEntry]:
    return [
        LibraryEntry(
            candidate_id=_identity_key(spectra_by_id[spectrum_id]),
            smiles=spectra_by_id[spectrum_id].normalized_smiles or "",
            spectrum=spectra_by_id[spectrum_id],
            formula=spectra_by_id[spectrum_id].molecular_formula,
            source=spectra_by_id[spectrum_id].ingest_lib,
        )
        for spectrum_id in spectrum_ids
    ]


def _spectral_index(
    entries: Sequence[LibraryEntry],
    config: Goal3ExperimentConfig,
) -> SpectralLibraryIndex:
    return SpectralLibraryIndex(
        list(entries),
        mass_tolerance_ppm=config.mass_tolerance_ppm,
        peak_tolerance_da=config.peak_tolerance_da,
    )


def _build_candidate_groups(
    queries: Mapping[str, Sequence[ProcessedSpectrum]],
    mass_index: MassCandidateIndex,
    spectral_index: SpectralLibraryIndex,
    candidate_by_id: Mapping[str, StructureCandidate],
    *,
    mode: CandidatePoolMode,
    pool_size: int,
) -> tuple[
    dict[str, list[CandidateHit]],
    dict[str, list[CandidateHit]],
    dict[str, Any],
]:
    mass_groups: dict[str, list[CandidateHit]] = {}
    union_groups: dict[str, list[CandidateHit]] = {}
    traces: dict[str, Any] = {}
    for query_id, spectra in queries.items():
        mass, union, trace = _retrieve_group(
            query_id,
            spectra,
            mass_index,
            spectral_index,
            candidate_by_id,
            mode=mode,
            pool_size=pool_size,
        )
        mass_groups[query_id] = mass
        union_groups[query_id] = union
        traces[query_id] = trace
    return mass_groups, union_groups, traces


def _build_identity_oof_groups(
    queries: Mapping[str, Sequence[ProcessedSpectrum]],
    reference_entries: Sequence[LibraryEntry],
    mass_index: MassCandidateIndex,
    candidate_by_id: Mapping[str, StructureCandidate],
    *,
    mode: CandidatePoolMode,
    config: Goal3ExperimentConfig,
    n_folds: int = 3,
) -> tuple[dict[str, list[CandidateHit]], dict[str, Any], dict[str, int]]:
    """Build ranker training features without a same-identity reference spectrum."""

    fold_by_identity = deterministic_group_folds(
        list(queries), n_folds=n_folds, seed=config.seed
    )
    groups: dict[str, list[CandidateHit]] = {}
    traces: dict[str, Any] = {}
    for fold in range(n_folds):
        fold_queries = {
            key: values for key, values in queries.items() if fold_by_identity[key] == fold
        }
        fold_entries = [
            entry
            for entry in reference_entries
            if fold_by_identity.get(entry.candidate_id) != fold
        ]
        if not fold_entries:
            raise RuntimeError(f"No spectral references remain for OOF fold {fold}")
        spectral_index = _spectral_index(fold_entries, config)
        _, fold_groups, fold_traces = _build_candidate_groups(
            fold_queries,
            mass_index,
            spectral_index,
            candidate_by_id,
            mode=mode,
            pool_size=config.candidate_pool_size,
        )
        groups.update(fold_groups)
        traces.update(fold_traces)
    if set(groups) != set(queries):
        raise AssertionError("Every train identity must have one OOF candidate group")
    return groups, traces, fold_by_identity


def _spectrum_targets(
    spectra: Sequence[ProcessedSpectrum],
    spec: FingerprintSpec,
) -> np.ndarray:
    cache: dict[str, np.ndarray] = {}
    rows: list[np.ndarray] = []
    for spectrum in spectra:
        key = _identity_key(spectrum)
        if key not in cache:
            cache[key] = molecular_fingerprint(spectrum.normalized_smiles or "", spec)
        rows.append(cache[key])
    return np.stack(rows).astype(np.float32, copy=False)


def _aggregate_probabilities(
    spectra: Sequence[ProcessedSpectrum],
    probabilities: np.ndarray,
) -> dict[str, np.ndarray]:
    grouped: dict[str, list[np.ndarray]] = defaultdict(list)
    for spectrum, probability in zip(spectra, probabilities, strict=True):
        grouped[_identity_key(spectrum)].append(np.asarray(probability, dtype=np.float32))
    return {
        key: np.mean(np.stack(values), axis=0, dtype=np.float64).astype(np.float32)
        for key, values in grouped.items()
    }


def _knn_oof_predictions(
    train_spectra: Sequence[ProcessedSpectrum],
    train_targets: np.ndarray,
    validation_spectra: Sequence[ProcessedSpectrum],
    *,
    n_folds: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    groups = [_identity_key(spectrum) for spectrum in train_spectra]
    fold_by_group = deterministic_group_folds(groups, n_folds=n_folds, seed=seed)
    oof = np.zeros_like(train_targets, dtype=np.float32)
    started = time.perf_counter()
    for fold in range(n_folds):
        train_indices = [
            index for index, key in enumerate(groups) if fold_by_group[key] != fold
        ]
        held_indices = [
            index for index, key in enumerate(groups) if fold_by_group[key] == fold
        ]
        model = FingerprintKNNBaseline(n_neighbors=5).fit(
            [train_spectra[index] for index in train_indices],
            train_targets[train_indices],
        )
        oof[held_indices] = model.predict_proba(
            [train_spectra[index] for index in held_indices]
        )
    final = FingerprintKNNBaseline(n_neighbors=5).fit(train_spectra, train_targets)
    validation = final.predict_proba(validation_spectra)
    return oof, validation, {
        "model": "FingerprintKNNBaseline",
        "n_neighbors": 5,
        "elapsed_seconds": time.perf_counter() - started,
        "oof_metrics": fingerprint_metrics(oof, train_targets),
    }


def _candidate_fingerprints(
    groups: Sequence[Mapping[str, Sequence[CandidateHit]]],
    candidate_by_id: Mapping[str, StructureCandidate],
    spec: FingerprintSpec,
) -> dict[str, np.ndarray]:
    ids = sorted(
        {
            hit.candidate_id
            for mapping in groups
            for hits in mapping.values()
            for hit in hits
        }
    )
    result: dict[str, np.ndarray] = {}
    for candidate_id in ids:
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            continue
        try:
            result[candidate_id] = molecular_fingerprint(candidate.smiles, spec)
        except ValueError:
            continue
    return result


def _annotate_groups(
    groups: Mapping[str, Sequence[CandidateHit]],
    predictions: Mapping[str, np.ndarray],
    candidate_fingerprints: Mapping[str, np.ndarray],
) -> dict[str, list[CandidateHit]]:
    return {
        query_id: annotate_fingerprint_features(
            hits, predictions[query_id], candidate_fingerprints
        )
        for query_id, hits in groups.items()
    }


def _rank_ids(ranked: Sequence[Any]) -> list[str]:
    return [item.candidate_id for item in ranked]


def _linear_fingerprint_ranking(
    groups: Mapping[str, Sequence[CandidateHit]],
    *,
    base_feature: str,
    fingerprint_weight: float,
) -> dict[str, list[str]]:
    rankings: dict[str, list[str]] = {}
    for query_id, hits in groups.items():
        scored = []
        for hit in hits:
            base = float(hit.features[base_feature])
            fp_score = float(hit.features["fingerprint_soft_jaccard"])
            scored.append((base + fingerprint_weight * fp_score, hit.candidate_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        rankings[query_id] = [candidate_id for _, candidate_id in scored]
    return rankings


def _mrr_at_25(truths: Mapping[str, str], rankings: Mapping[str, Sequence[str]]) -> float:
    values = []
    for query_id, truth in truths.items():
        try:
            rank = list(rankings[query_id])[:25].index(truth) + 1
        except ValueError:
            rank = None
        values.append(0.0 if rank is None else 1.0 / rank)
    return float(np.mean(values)) if values else 0.0


def _tune_fingerprint_weight(
    truths: Mapping[str, str],
    groups: Mapping[str, Sequence[CandidateHit]],
    *,
    base_feature: str,
) -> tuple[float, list[dict[str, float]]]:
    trials = []
    for weight in (0.0, 0.25, 0.5, 1.0, 2.0, 4.0):
        rankings = _linear_fingerprint_ranking(
            groups, base_feature=base_feature, fingerprint_weight=weight
        )
        score = _mrr_at_25(truths, rankings)
        trials.append({"weight": weight, "model_selection_mrr_at_25": score})
    best = max(trials, key=lambda item: (item["model_selection_mrr_at_25"], -item["weight"]))
    return float(best["weight"]), trials


def _hard_negative_groups(
    groups: Mapping[str, Sequence[CandidateHit]],
    candidate_by_id: Mapping[str, StructureCandidate],
    *,
    max_negatives: int,
) -> tuple[dict[str, list[CandidateHit]], dict[str, Any]]:
    selected_groups: dict[str, list[CandidateHit]] = {}
    summaries: dict[str, Any] = {}
    for query_id, hits in groups.items():
        target = candidate_by_id[query_id]
        candidates = [candidate_by_id[hit.candidate_id] for hit in hits if hit.candidate_id in candidate_by_id]
        ranks = {hit.candidate_id: index for index, hit in enumerate(hits, start=1)}
        negatives, summary = mine_hard_negatives(
            target,
            candidates,
            baseline_ranks=ranks,
            max_negatives=max_negatives,
        )
        keep = {query_id, *(item.candidate_id for item in negatives)}
        selected = [hit for hit in hits if hit.candidate_id in keep]
        if not any(hit.candidate_id == query_id for hit in selected):
            raise RuntimeError(f"Hard-negative group lost positive target {query_id}")
        selected_groups[query_id] = selected
        summaries[query_id] = asdict(summary)
    return selected_groups, summaries


def _query_metadata(spectra: Sequence[ProcessedSpectrum]) -> dict[str, Any]:
    first = spectra[0]
    return {
        "neutral_mass": _query_mass(spectra),
        "formula": first.molecular_formula,
        "adduct": first.adduct,
        "instrument_type": first.instrument,
        "source": first.ingest_lib,
        "peak_count": int(np.median([len(item.mz) for item in spectra])),
    }


def _ordered_union(first: Sequence[str], second: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in (*first, *second):
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _select_mapping(
    values: Mapping[str, Sequence[str]], keys: set[str]
) -> dict[str, list[str]]:
    return {key: list(values[key]) for key in sorted(keys) if key in values}


def _evaluate_rankings(
    truths: Mapping[str, str],
    pools: Mapping[str, Sequence[str]],
    rankings: Mapping[str, Sequence[str]],
    *,
    candidate_formula: Mapping[str, str],
    truth_formula: Mapping[str, str],
    query_metadata: Mapping[str, Mapping[str, Any]],
    config: Goal3ExperimentConfig,
) -> dict[str, Any]:
    diagnostics = evaluate_retrieval_diagnostics(
        truths,
        pools,
        rankings,
        candidate_formula_by_id=candidate_formula,
        truth_formula_by_query=truth_formula,
        query_metadata=query_metadata,
    )
    intervals = bootstrap_retrieval_confidence_intervals(
        truths,
        pools,
        rankings,
        candidate_formula_by_id=candidate_formula,
        truth_formula_by_query=truth_formula,
        n_bootstrap=config.bootstrap_samples,
        seed=config.seed,
    )
    breakdown = ranking_breakdowns(
        truths,
        pools,
        rankings,
        candidate_formula_by_id=candidate_formula,
        truth_formula_by_query=truth_formula,
    )
    return {
        "metrics": diagnostics.to_dict(),
        "confidence_intervals": intervals,
        "same_formula_breakdown": breakdown["isomer_count"],
    }


def _evaluate_experiments(
    truths: Mapping[str, str],
    experiment_pools: Mapping[str, Mapping[str, Sequence[str]]],
    experiment_rankings: Mapping[str, Mapping[str, Sequence[str]]],
    *,
    model_selection_keys: set[str],
    final_keys: set[str],
    candidate_formula: Mapping[str, str],
    truth_formula: Mapping[str, str],
    query_metadata: Mapping[str, Mapping[str, Any]],
    config: Goal3ExperimentConfig,
) -> dict[str, Any]:
    stage_keys = {
        "all_validation": set(truths),
        "model_selection": model_selection_keys,
        "final_evaluation": final_keys,
    }
    results: dict[str, Any] = {}
    for stage, keys in stage_keys.items():
        stage_truths = {key: truths[key] for key in sorted(keys) if key in truths}
        stage_results: dict[str, Any] = {}
        mass_pool = _select_mapping(experiment_pools["E0"], set(stage_truths))
        mass_ranking = _select_mapping(experiment_rankings["E0"], set(stage_truths))
        for experiment_id, rankings in experiment_rankings.items():
            pools = _select_mapping(experiment_pools[experiment_id], set(stage_truths))
            selected_rankings = _select_mapping(rankings, set(stage_truths))
            evaluation = _evaluate_rankings(
                stage_truths,
                pools,
                selected_rankings,
                candidate_formula=candidate_formula,
                truth_formula={key: truth_formula[key] for key in stage_truths},
                query_metadata={key: query_metadata[key] for key in stage_truths},
                config=config,
            )
            if experiment_id != "E0":
                paired_pools = {
                    key: _ordered_union(mass_pool[key], pools[key]) for key in stage_truths
                }
                evaluation["paired_delta_vs_E0"] = bootstrap_paired_ranking_differences(
                    stage_truths,
                    paired_pools,
                    mass_ranking,
                    selected_rankings,
                    n_bootstrap=config.bootstrap_samples,
                    seed=config.seed,
                )
            stage_results[experiment_id] = evaluation
        results[stage] = stage_results
    return results


def _feature_matrix(
    groups: Mapping[str, Sequence[CandidateHit]],
    feature_names: Sequence[str],
    truths: Mapping[str, str],
    *,
    query_filter: set[str] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    rows: list[list[float]] = []
    labels: list[int] = []
    for query_id in sorted(groups):
        if query_filter is not None and query_id not in query_filter:
            continue
        for hit in groups[query_id]:
            rows.append([float(hit.features[name]) for name in feature_names])
            labels.append(int(hit.candidate_id == truths[query_id]))
    return np.asarray(rows, dtype=np.float64), np.asarray(labels, dtype=np.int8)


def _predict_original_probabilities(
    ranker: SupervisedRanker,
    groups: Mapping[str, Sequence[CandidateHit]],
    truths: Mapping[str, str],
    keys: set[str],
) -> tuple[np.ndarray, np.ndarray]:
    features, labels = _feature_matrix(groups, FEATURE_NAMES, truths, query_filter=keys)
    return np.asarray(ranker.model.predict_proba(features)[:, 1]), labels


def _process_rss_bytes() -> int | None:
    try:
        import psutil
    except ImportError:
        return None
    return int(psutil.Process().memory_info().rss)


def _resource_snapshot() -> dict[str, int | None]:
    """Return comparable process/GPU memory counters without requiring CUDA locally."""

    allocated: int | None = None
    peak: int | None = None
    try:
        import torch

        if torch.cuda.is_available():
            allocated = int(torch.cuda.memory_allocated())
            peak = int(torch.cuda.max_memory_allocated())
    except ImportError:
        pass
    return {
        "rss_bytes": _process_rss_bytes(),
        "vram_allocated_bytes": allocated,
        "peak_vram_bytes_since_process_start": peak,
    }


def _resource_record(
    started: float,
    before: Mapping[str, int | None],
) -> dict[str, Any]:
    after = _resource_snapshot()
    rss_values = [
        value
        for value in (before["rss_bytes"], after["rss_bytes"])
        if value is not None
    ]
    return {
        "elapsed_seconds": time.perf_counter() - started,
        "rss_bytes_before": before["rss_bytes"],
        "rss_bytes_after": after["rss_bytes"],
        "max_observed_rss_bytes": max(rss_values) if rss_values else None,
        "vram_allocated_bytes_before": before["vram_allocated_bytes"],
        "vram_allocated_bytes_after": after["vram_allocated_bytes"],
        "peak_vram_bytes_since_process_start": after[
            "peak_vram_bytes_since_process_start"
        ],
    }


def run_goal3_experiment(
    train_path: str | Path,
    frozen_identity_path: str | Path,
    output_dir: str | Path,
    *,
    config: Goal3ExperimentConfig = Goal3ExperimentConfig(),
) -> dict[str, Any]:
    """Run E0-E6 on controlled and target-blind realistic benchmarks."""

    started = time.perf_counter()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    dataset = collect_goal3_dataset(train_path, frozen_identity_path, config)
    spectra = list(dataset.spectra)
    spectra_by_id = {spectrum.spectrum_id: spectrum for spectrum in spectra}
    source_by_id = {candidate.candidate_id: candidate for candidate in dataset.source_catalog}
    manifest = generate_split(
        "molecule_disjoint",
        spectra,
        validation_fraction=config.validation_fraction,
        seed=config.seed,
        candidate_identity_keys=dataset.source_candidate_ids,
    )
    manifest_path = output / "goal3_molecule_disjoint_manifest.json"
    manifest.save(manifest_path)
    leakage_report = assert_leakage_free(
        manifest,
        spectrum_identity_keys=spectrum_identity_mapping(spectra),
        spectrum_hashes=spectrum_hash_mapping(spectra),
        ranker_train_spectrum_ids=manifest.train_spectrum_ids,
        feature_provenance={
            **{name: "spectrum_and_candidate_only" for name in FEATURE_NAMES},
            **{name: "oof_spectrum_prediction_and_candidate_only" for name in FP_FEATURE_NAMES},
            **{name: "candidate_pool_context_only" for name in CHEMISTRY_CONTEXT_FEATURE_NAMES},
        },
    )
    train_queries = _group_queries(manifest.train_spectrum_ids, spectra_by_id)
    validation_queries = _group_queries(manifest.validation_spectrum_ids, spectra_by_id)
    train_spectra = [item for key in sorted(train_queries) for item in train_queries[key]]
    validation_spectra = [
        item for key in sorted(validation_queries) for item in validation_queries[key]
    ]
    fp_spec = FingerprintSpec(n_bits=config.fingerprint_bits)
    train_targets = _spectrum_targets(train_spectra, fp_spec)
    validation_targets = _spectrum_targets(validation_spectra, fp_spec)

    training_config = FingerprintTrainingConfig(
        model_kind="compact",
        n_bits=config.fingerprint_bits,
        max_peaks=config.max_peaks,
        batch_size=config.fingerprint_batch_size,
        epochs=config.fingerprint_epochs,
        seed=config.seed,
    )
    neural = oof_fingerprint_predictions(
        train_spectra,
        train_targets,
        [_identity_key(spectrum) for spectrum in train_spectra],
        validation_spectra,
        config=training_config,
        n_folds=config.fingerprint_folds,
        device=config.device,
        checkpoint_dir=output / "checkpoints",
    )
    knn_oof, knn_validation, knn_report = _knn_oof_predictions(
        train_spectra,
        train_targets,
        validation_spectra,
        n_folds=config.fingerprint_folds,
        seed=config.seed,
    )
    train_prediction = _aggregate_probabilities(train_spectra, neural.oof_probabilities)
    validation_prediction = _aggregate_probabilities(
        validation_spectra, neural.validation_probabilities
    )
    model_selection_keys = set(manifest.metadata["model_selection_identity_keys"])
    final_keys = set(manifest.metadata["final_evaluation_identity_keys"])
    truths = {key: key for key in validation_queries}
    truth_formula = {
        key: validation_queries[key][0].molecular_formula or "" for key in validation_queries
    }
    query_metadata = {
        key: _query_metadata(values) for key, values in validation_queries.items()
    }

    mode_results: dict[str, Any] = {}
    for mode in ("controlled", "realistic"):
        mode_started = time.perf_counter()
        shared_started = time.perf_counter()
        shared_before = _resource_snapshot()
        catalog, catalog_trace = _catalog_for_mode(dataset, mode, config)
        candidate_by_id = {candidate.candidate_id: candidate for candidate in catalog}
        mass_index = MassCandidateIndex(catalog)
        reference_entries = _library_entries(manifest.reference_spectrum_ids, spectra_by_id)
        full_spectral_index = _spectral_index(reference_entries, config)

        train_mass, train_original, train_original_traces = _build_candidate_groups(
            train_queries,
            mass_index,
            full_spectral_index,
            candidate_by_id,
            mode=mode,
            pool_size=config.candidate_pool_size,
        )
        train_oof, train_oof_traces, spectral_fold_by_identity = _build_identity_oof_groups(
            train_queries,
            reference_entries,
            mass_index,
            candidate_by_id,
            mode=mode,
            config=config,
            n_folds=config.fingerprint_folds,
        )
        validation_mass, validation_union, validation_traces = _build_candidate_groups(
            validation_queries,
            mass_index,
            full_spectral_index,
            candidate_by_id,
            mode=mode,
            pool_size=config.candidate_pool_size,
        )
        candidate_fingerprints = _candidate_fingerprints(
            [train_oof, validation_union, validation_mass], candidate_by_id, fp_spec
        )
        annotated_train = _annotate_groups(
            train_oof, train_prediction, candidate_fingerprints
        )
        annotated_validation = _annotate_groups(
            validation_union, validation_prediction, candidate_fingerprints
        )
        annotated_validation_mass = _annotate_groups(
            validation_mass, validation_prediction, candidate_fingerprints
        )
        shared_resources = _resource_record(shared_started, shared_before)

        catalog_formula = {
            candidate.candidate_id: candidate.formula or "" for candidate in catalog
        }
        catalog_mass = {
            candidate.candidate_id: candidate.exact_mass for candidate in catalog
        }
        benchmark_audit = audit_candidate_pools(
            truths,
            catalog_trace.candidate_ids,
            {key: [hit.candidate_id for hit in hits] for key, hits in validation_union.items()},
            mode=mode,
            ranked_candidates={
                key: [hit.candidate_id for hit in hits]
                for key, hits in validation_union.items()
            },
            pool_traces=validation_traces,
            catalog_trace=catalog_trace,
            candidate_formula_by_id=catalog_formula,
            truth_formula_by_query=truth_formula,
            candidate_exact_mass_by_id=catalog_mass,
            truth_exact_mass_by_query={
                key: source_by_id[key].exact_mass for key in truths
            },
        )
        if mode == "realistic":
            assert_realistic_candidate_integrity(benchmark_audit)

        experiment_rankings: dict[str, dict[str, list[str]]] = {}
        experiment_pools: dict[str, dict[str, list[str]]] = {}
        experiment_resources: dict[str, Any] = {}
        e0_started = time.perf_counter()
        e0_before = _resource_snapshot()
        experiment_rankings["E0"] = {
            key: [hit.candidate_id for hit in hits] for key, hits in validation_mass.items()
        }
        experiment_pools["E0"] = dict(experiment_rankings["E0"])
        experiment_resources["E0"] = {
            "description": "nearest_mass",
            "fit_seconds": 0.0,
            **_resource_record(e0_started, e0_before),
        }

        e1_started = time.perf_counter()
        e1_before = _resource_snapshot()
        original_ranker = SupervisedRanker(random_state=config.seed)
        e1_summary = original_ranker.fit(
            train_original, {key: key for key in train_original}
        )
        experiment_rankings["E1"] = {
            key: _rank_ids(original_ranker.rank(hits))
            for key, hits in validation_union.items()
        }
        experiment_pools["E1"] = {
            key: [hit.candidate_id for hit in hits] for key, hits in validation_union.items()
        }
        experiment_resources["E1"] = {
            "description": "original_same_identity_reference_ranker",
            "training": e1_summary.to_dict(),
            **_resource_record(e1_started, e1_before),
        }

        e2_started = time.perf_counter()
        e2_before = _resource_snapshot()
        selection_truths = {key: key for key in model_selection_keys}
        e2_weight, e2_trials = _tune_fingerprint_weight(
            selection_truths,
            {key: annotated_validation_mass[key] for key in model_selection_keys},
            base_feature="retrieval_score",
        )
        experiment_rankings["E2"] = _linear_fingerprint_ranking(
            annotated_validation_mass,
            base_feature="retrieval_score",
            fingerprint_weight=e2_weight,
        )
        experiment_pools["E2"] = {
            key: [hit.candidate_id for hit in hits]
            for key, hits in annotated_validation_mass.items()
        }
        experiment_resources["E2"] = {
            "description": "nearest_mass_plus_neural_fingerprint",
            "selected_weight": e2_weight,
            "model_selection_trials": e2_trials,
            **_resource_record(e2_started, e2_before),
        }

        e3_started = time.perf_counter()
        e3_before = _resource_snapshot()
        e3_weight, e3_trials = _tune_fingerprint_weight(
            selection_truths,
            {key: annotated_validation[key] for key in model_selection_keys},
            base_feature="retrieval_score",
        )
        experiment_rankings["E3"] = _linear_fingerprint_ranking(
            annotated_validation,
            base_feature="retrieval_score",
            fingerprint_weight=e3_weight,
        )
        experiment_pools["E3"] = {
            key: [hit.candidate_id for hit in hits]
            for key, hits in annotated_validation.items()
        }
        experiment_resources["E3"] = {
            "description": "retrieval_union_plus_neural_fingerprint",
            "selected_weight": e3_weight,
            "model_selection_trials": e3_trials,
            **_resource_record(e3_started, e3_before),
        }

        all_features = (*FEATURE_NAMES, *FP_FEATURE_NAMES, *CHEMISTRY_CONTEXT_FEATURE_NAMES)
        e4_started = time.perf_counter()
        e4_before = _resource_snapshot()
        e4_ranker = IsomerAwareRanker(all_features, backend="lightgbm", random_state=config.seed)
        e4_summary = e4_ranker.fit(annotated_train, {key: key for key in annotated_train})
        experiment_rankings["E4"] = {
            key: _rank_ids(e4_ranker.rank(hits))
            for key, hits in annotated_validation.items()
        }
        experiment_pools["E4"] = dict(experiment_pools["E3"])
        experiment_resources["E4"] = {
            "description": "lightgbm_spectral_and_fingerprint_oof",
            "training": e4_summary,
            **_resource_record(e4_started, e4_before),
        }

        hard_groups, hard_summaries = _hard_negative_groups(
            annotated_train,
            candidate_by_id,
            max_negatives=config.hard_negatives_per_query,
        )
        e5_started = time.perf_counter()
        e5_before = _resource_snapshot()
        e5_ranker = IsomerAwareRanker(all_features, backend="lightgbm", random_state=config.seed)
        e5_summary = e5_ranker.fit(hard_groups, {key: key for key in hard_groups})
        experiment_rankings["E5"] = {
            key: _rank_ids(e5_ranker.rank(hits))
            for key, hits in annotated_validation.items()
        }
        experiment_pools["E5"] = dict(experiment_pools["E3"])
        experiment_resources["E5"] = {
            "description": "isomer_aware_same_formula_hard_negatives",
            "training": e5_summary,
            "hard_negative_totals": {
                "selected": sum(value["selected_count"] for value in hard_summaries.values()),
                "same_formula": sum(value["same_formula_count"] for value in hard_summaries.values()),
                "same_scaffold": sum(value["same_scaffold_count"] for value in hard_summaries.values()),
            },
            **_resource_record(e5_started, e5_before),
        }

        ablation_features = {
            "E6_mass_only": (
                "mass_error_ppm",
                "abs_precursor_delta",
                "retrieval_score",
                *CHEMISTRY_CONTEXT_FEATURE_NAMES,
            ),
            "E6_spectral_only": tuple(
                name
                for name in FEATURE_NAMES
                if name not in {"mass_error_ppm", "abs_precursor_delta"}
            ),
            "E6_fingerprint_only": FP_FEATURE_NAMES,
        }
        for experiment_id, feature_names in ablation_features.items():
            ablation_started = time.perf_counter()
            ablation_before = _resource_snapshot()
            ranker = IsomerAwareRanker(
                feature_names, backend="lightgbm", random_state=config.seed
            )
            summary = ranker.fit(annotated_train, {key: key for key in annotated_train})
            experiment_rankings[experiment_id] = {
                key: _rank_ids(ranker.rank(hits))
                for key, hits in annotated_validation.items()
            }
            experiment_pools[experiment_id] = dict(experiment_pools["E3"])
            experiment_resources[experiment_id] = {
                "description": "E6_feature_group_ablation",
                "features": list(feature_names),
                "training": summary,
                **_resource_record(ablation_started, ablation_before),
            }

        evaluations = _evaluate_experiments(
            truths,
            experiment_pools,
            experiment_rankings,
            model_selection_keys=model_selection_keys,
            final_keys=final_keys,
            candidate_formula=catalog_formula,
            truth_formula=truth_formula,
            query_metadata=query_metadata,
            config=config,
        )
        train_matrix, _ = _feature_matrix(
            annotated_train, all_features, {key: key for key in annotated_train}
        )
        validation_matrix, validation_labels = _feature_matrix(
            annotated_validation,
            all_features,
            truths,
            query_filter=model_selection_keys,
        )
        sample_rng = np.random.default_rng(config.seed)
        if len(validation_matrix) > 5000:
            sample_indices = sample_rng.choice(len(validation_matrix), 5000, replace=False)
            importance_matrix = validation_matrix[sample_indices]
            importance_labels = validation_labels[sample_indices]
        else:
            importance_matrix = validation_matrix
            importance_labels = validation_labels
        e1_probabilities, e1_labels = _predict_original_probabilities(
            original_ranker, validation_union, truths, model_selection_keys
        )
        mode_results[mode] = {
            "catalog_trace": catalog_trace.to_dict(),
            "benchmark_audit": benchmark_audit.to_dict(),
            "spectral_oof_fold_by_identity": spectral_fold_by_identity,
            "train_reference_identity_overlap_original": len(
                set(train_queries) & {entry.candidate_id for entry in reference_entries}
            ),
            "train_reference_identity_overlap_oof": 0,
            "shared_candidate_generation_resources": shared_resources,
            "experiment_resources": experiment_resources,
            "evaluations": evaluations,
            "diagnostics": {
                "rank_shifts_vs_E0": rank_shift_diagnostics(
                    truths,
                    experiment_rankings,
                    baseline_method="E0",
                ),
                "feature_drift_oof_train_vs_model_selection": feature_drift_diagnostics(
                    train_matrix,
                    validation_matrix,
                    feature_names=all_features,
                ),
                "E4_importance": model_importance_diagnostics(
                    e4_ranker.model,
                    all_features,
                    validation_features=importance_matrix,
                    validation_labels=importance_labels,
                    n_repeats=3,
                    seed=config.seed,
                ),
                "E1_calibration_model_selection": calibration_diagnostics(
                    e1_labels, e1_probabilities
                ),
                "candidate_priors_model_selection": candidate_prior_diagnostics(
                    {
                        key: validation_union[key]
                        for key in sorted(model_selection_keys)
                    },
                    truths,
                ),
            },
            "elapsed_seconds": time.perf_counter() - mode_started,
            "rss_bytes_at_end": _process_rss_bytes(),
        }

    neural_validation_metrics = fingerprint_metrics(
        neural.validation_probabilities, validation_targets
    )
    knn_validation_metrics = fingerprint_metrics(knn_validation, validation_targets)
    results: dict[str, Any] = {
        "experiment_id": "goal3_neural_fingerprint_isomer_ranking_v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "rdkit_version": rdkit_version(),
        "dataset": dataset.metadata,
        "manifest_hash": manifest.manifest_hash,
        "leakage_audit": leakage_report.to_dict(),
        "fingerprint_models": {
            "non_neural_knn": {
                **knn_report,
                "validation_metrics": knn_validation_metrics,
            },
            "compact_peak_encoder": {
                "oof_metrics": fingerprint_metrics(neural.oof_probabilities, train_targets),
                "validation_metrics": neural_validation_metrics,
                "fold_reports": list(neural.fold_reports),
                "final_report": neural.final_report,
            },
        },
        "modes": mode_results,
        "elapsed_seconds": time.perf_counter() - started,
    }
    (output / "goal3_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "goal3_config.json").write_text(
        json.dumps(asdict(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results
