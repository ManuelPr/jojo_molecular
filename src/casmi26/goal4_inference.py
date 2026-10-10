from __future__ import annotations

from collections import defaultdict
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
import pandas as pd

from .analog_propagation import AnalogReference, spectrum_content_hash
from .chemistry import (
    canonical_inchikey14,
    exact_mass_from_formula,
    exact_mass_from_smiles,
    rdkit_version,
)
from .data import ParquetSpectrumReader, PreprocessConfig, read_processed
from .goal3_contracts import FingerprintSpec
from .goal3_pipeline import Goal3ExperimentConfig, _identity_key, collect_goal3_dataset
from .goal4_pipeline import (
    Goal4ExperimentConfig,
    _annotate_groups,
    _mass_groups,
    _reference_library,
)
from .goal4_ranking import (
    confidence_aware_ranking,
    linear_evidence_ranking,
    same_anchor_formula_reranking,
)
from .mass_retrieval import MassCandidateIndex, StructureCandidate
from .schemas import ProcessedSpectrum
from .submission import clean_candidates, write_submission


@dataclass(frozen=True, slots=True)
class Goal4InferenceConfig:
    seed: int = 2026
    max_scan_rows: int = 300_000
    catalog_size: int = 50_000
    retrieval_pool_size: int = 100
    output_size: int = 25
    max_peaks: int = 256
    intensity_floor: float = 0.001
    verify_canonical_identity: bool = True


def _catalog_order(identity: str, *, seed: int) -> tuple[bytes, str]:
    payload = f"goal3-catalog\0{seed}\0{identity}".encode()
    return hashlib.sha256(payload).digest(), identity


def build_target_blind_catalog(
    train_path: str | Path,
    config: Goal4InferenceConfig = Goal4InferenceConfig(),
) -> tuple[list[StructureCandidate], dict[str, Any]]:
    """Build a deterministic catalog without consulting test or holdout truth."""

    reader = ParquetSpectrumReader(train_path)
    columns = [
        name
        for name in ("inchikey14", "normalized_smiles", "molecular_formula", "ingest_lib")
        if name in reader.schema.names
    ]
    structures: dict[str, tuple[str, str | None, str | None]] = {}
    rows_seen = 0
    for record in reader.iter_records(max_rows=config.max_scan_rows, columns=columns):
        rows_seen += 1
        if record.inchikey14 is None or record.normalized_smiles is None:
            continue
        identity = str(record.inchikey14).strip().upper()
        if len(identity) != 14 or not identity.isalpha():
            continue
        structures.setdefault(
            identity,
            (record.normalized_smiles, record.molecular_formula, record.ingest_lib),
        )
    selected_ids = sorted(structures, key=lambda key: _catalog_order(key, seed=config.seed))[
        : config.catalog_size
    ]
    catalog: list[StructureCandidate] = []
    invalid_mass = 0
    identity_mismatch = 0
    for identity in selected_ids:
        smiles, formula, source = structures[identity]
        if config.verify_canonical_identity and canonical_inchikey14(smiles) != identity:
            identity_mismatch += 1
            continue
        exact_mass = exact_mass_from_formula(formula or "")
        if exact_mass is None:
            exact_mass = exact_mass_from_smiles(smiles)
        if exact_mass is None:
            invalid_mass += 1
            continue
        catalog.append(
            StructureCandidate(
                candidate_id=identity,
                smiles=smiles,
                exact_mass=exact_mass,
                formula=formula,
                source=source or "train_structure_catalog",
            )
        )
    if not catalog:
        raise RuntimeError("Target-blind catalog contains no usable structures")
    digest = hashlib.sha256()
    for candidate in catalog:
        digest.update(
            f"{candidate.candidate_id}\t{candidate.exact_mass:.9f}\t{candidate.smiles}\n".encode()
        )
    return catalog, {
        "selection_policy": "seeded_hash_order_from_train_metadata_only",
        "target_or_test_identities_consulted": 0,
        "rows_seen": rows_seen,
        "unique_source_structures": len(structures),
        "selected_before_validation": len(selected_ids),
        "valid_catalog_structures": len(catalog),
        "invalid_mass_count": invalid_mass,
        "canonical_identity_mismatch_count": identity_mismatch,
        "catalog_sha256": digest.hexdigest(),
    }


def group_query_spectra(
    spectra: Sequence[ProcessedSpectrum],
) -> dict[str, list[ProcessedSpectrum]]:
    grouped: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    for spectrum in spectra:
        grouped[str(spectrum.molecule_id)].append(spectrum)
    return {
        molecule_id: sorted(values, key=lambda item: item.spectrum_id)
        for molecule_id, values in sorted(grouped.items())
    }


def aggregate_neutral_mass(spectra: Sequence[ProcessedSpectrum]) -> float | None:
    values = [
        float(spectrum.neutral_mass)
        for spectrum in spectra
        if spectrum.neutral_mass is not None and math.isfinite(float(spectrum.neutral_mass))
    ]
    return float(np.median(values)) if values else None


def predict_nearest_mass(
    query_groups: Mapping[str, Sequence[ProcessedSpectrum]],
    catalog: Sequence[StructureCandidate],
    *,
    retrieval_pool_size: int = 100,
    output_size: int = 25,
) -> dict[str, list[str]]:
    if retrieval_pool_size < output_size:
        raise ValueError("retrieval_pool_size must be at least output_size")
    index = MassCandidateIndex(list(catalog))
    predictions: dict[str, list[str]] = {}
    for molecule_id, spectra in query_groups.items():
        hits = index.retrieve(
            aggregate_neutral_mass(spectra),
            top_k=retrieval_pool_size,
        )
        cleaned = clean_candidates([hit.smiles for hit in hits], limit=output_size)
        if not cleaned:
            raise RuntimeError(f"No valid mass candidates for {molecule_id}")
        predictions[molecule_id] = cleaned
    return predictions


def run_goal4_inference(
    train_path: str | Path,
    test_path: str | Path,
    sample_submission_path: str | Path,
    output_dir: str | Path,
    *,
    config: Goal4InferenceConfig = Goal4InferenceConfig(),
) -> dict[str, Any]:
    """Create and validate a ready-to-submit CSV; never call the Kaggle API."""

    started = time.perf_counter()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    catalog, catalog_report = build_target_blind_catalog(train_path, config)
    preprocessing = PreprocessConfig(
        intensity_floor=config.intensity_floor,
        max_peaks=config.max_peaks,
    )
    test_spectra = list(read_processed(test_path, config=preprocessing))
    query_groups = group_query_spectra(test_spectra)
    expected_ids = pd.read_csv(sample_submission_path, usecols=["molecule_id"])[
        "molecule_id"
    ].astype(str).tolist()
    if set(query_groups) != set(expected_ids):
        raise RuntimeError(
            "Test/query molecule IDs differ from sample submission: "
            f"missing={len(set(expected_ids) - set(query_groups))}, "
            f"extra={len(set(query_groups) - set(expected_ids))}"
        )
    predictions = predict_nearest_mass(
        query_groups,
        catalog,
        retrieval_pool_size=config.retrieval_pool_size,
        output_size=config.output_size,
    )
    submission_path = destination / "submission.csv"
    validation = write_submission(predictions, expected_ids, submission_path)
    result = {
        "experiment_id": "goal4_submission_ready_nearest_mass_v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "submission_performed": False,
        "submission_requires_explicit_human_approval": True,
        "config": asdict(config),
        "rdkit_version": rdkit_version(),
        "catalog": catalog_report,
        "test_spectrum_count": len(test_spectra),
        "test_molecule_count": len(query_groups),
        "submission_validation": validation.to_dict(),
        "elapsed_seconds": time.perf_counter() - started,
        "submission_path": str(submission_path),
    }
    (destination / "goal4_inference_report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _representative_reference_ids(
    spectra: Sequence[ProcessedSpectrum],
) -> tuple[str, ...]:
    grouped: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    for spectrum in spectra:
        grouped[_identity_key(spectrum)].append(spectrum)
    selected = []
    for identity in sorted(grouped):
        best = max(
            grouped[identity],
            key=lambda item: (
                float(item.quality.get("retained_fraction", 0.0)),
                len(item.mz),
                item.spectrum_id,
            ),
        )
        selected.append(best.spectrum_id)
    return tuple(selected)


def exclude_query_duplicate_references(
    references: Sequence[AnalogReference],
    query_spectra: Sequence[ProcessedSpectrum],
) -> tuple[list[AnalogReference], tuple[str, ...]]:
    """Remove reference spectra whose content is present in the inference query set.

    Hidden identities are neither known nor consulted.  Filtering by normalized
    spectral content is therefore the inference-safe equivalent of the stricter
    identity-and-content separation used by validation protocols.
    """

    query_hashes = {spectrum_content_hash(spectrum) for spectrum in query_spectra}
    kept: list[AnalogReference] = []
    excluded: list[str] = []
    for reference in references:
        if spectrum_content_hash(reference.spectrum) in query_hashes:
            excluded.append(reference.reference_id)
        else:
            kept.append(reference)
    return kept, tuple(sorted(excluded))


def run_goal4_selected_inference(
    train_path: str | Path,
    test_path: str | Path,
    sample_submission_path: str | Path,
    frozen_identity_path: str | Path,
    output_dir: str | Path,
    *,
    selected_experiment: str,
    selected_feature: str,
    evidence_weight: float,
    gate_threshold: float = 0.0,
    config: Goal4ExperimentConfig = Goal4ExperimentConfig(),
) -> dict[str, Any]:
    """Refit the selected non-neural analog baseline and generate a CSV.

    Model-selection values are supplied from the frozen validation artifact.
    Hidden test identities are never inspected; the reference library uses one
    deterministic representative acquisition for each frozen train identity.
    """

    if selected_experiment not in {"E0", "E3", "E6", "E7"}:
        raise ValueError("Selected inference currently supports E0/E3/E6/E7")
    started = time.perf_counter()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    collection = collect_goal3_dataset(
        train_path,
        frozen_identity_path,
        Goal3ExperimentConfig(
            seed=config.seed,
            max_scan_rows=config.max_scan_rows,
            spectra_per_identity=config.spectra_per_identity,
            realistic_catalog_size=config.realistic_catalog_size,
            candidate_pool_size=config.candidate_pool_size,
            max_peaks=config.max_peaks,
            intensity_floor=config.intensity_floor,
            peak_tolerance_da=config.peak_tolerance_da,
            fingerprint_bits=config.fingerprint_bits,
        ),
    )
    selected_catalog = list(collection.source_catalog[: config.realistic_catalog_size])
    catalog = [
        candidate
        for candidate in selected_catalog
        if canonical_inchikey14(candidate.smiles) == candidate.candidate_id
    ]
    canonical_mismatch_count = len(selected_catalog) - len(catalog)
    candidate_by_id = {candidate.candidate_id: candidate for candidate in catalog}
    mass_index = MassCandidateIndex(catalog)
    spectra_by_id = {spectrum.spectrum_id: spectrum for spectrum in collection.spectra}
    reference_ids = _representative_reference_ids(collection.spectra)
    fingerprint_cache: dict[str, np.ndarray] = {}
    fingerprint_spec = FingerprintSpec(n_bits=config.fingerprint_bits)
    references = _reference_library(
        reference_ids,
        spectra_by_id,
        candidate_by_id,
        fingerprint_cache,
        fingerprint_spec,
    )
    preprocessing = PreprocessConfig(
        intensity_floor=config.intensity_floor,
        max_peaks=config.max_peaks,
    )
    test_spectra = list(read_processed(test_path, config=preprocessing))
    query_groups = group_query_spectra(test_spectra)
    references_before_query_content_filter = len(references)
    references, excluded_reference_ids = exclude_query_duplicate_references(
        references,
        test_spectra,
    )
    if not references:
        raise RuntimeError(
            "All analog references duplicate hidden-query spectral content"
        )
    mass_groups = _mass_groups(
        query_groups,
        mass_index,
        pool_size=config.candidate_pool_size,
    )
    annotated, analog_report = _annotate_groups(
        query_groups,
        mass_groups,
        references,
        candidate_by_id,
        fingerprint_cache,
        fingerprint_spec,
        forbidden_identities=frozenset(),
        config=config,
    )
    formula_by_candidate = {
        candidate.candidate_id: candidate.formula or "" for candidate in catalog
    }
    predictions: dict[str, list[str]] = {}
    for molecule_id, hits in annotated.items():
        mass_ranking = [hit.candidate_id for hit in mass_groups[molecule_id]]
        if selected_experiment == "E0":
            ranking = mass_ranking
        else:
            proposed = linear_evidence_ranking(
                hits,
                evidence_feature=selected_feature,
                evidence_weight=evidence_weight,
            )
            if selected_experiment == "E6":
                ranking = same_anchor_formula_reranking(
                    mass_ranking, proposed, formula_by_candidate
                )
            elif selected_experiment == "E7":
                ranking = confidence_aware_ranking(
                    mass_ranking,
                    proposed,
                    confidence=float(analog_report[molecule_id]["analog_confidence"]),
                    threshold=gate_threshold,
                )
            else:
                ranking = proposed
        predictions[molecule_id] = [candidate_by_id[key].smiles for key in ranking]
    expected_ids = pd.read_csv(sample_submission_path, usecols=["molecule_id"])[
        "molecule_id"
    ].astype(str).tolist()
    submission_path = destination / "submission.csv"
    validation = write_submission(predictions, expected_ids, submission_path)
    result = {
        "experiment_id": "goal4_selected_analog_inference_v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selected_experiment": selected_experiment,
        "selected_feature": selected_feature,
        "evidence_weight": evidence_weight,
        "gate_threshold": gate_threshold,
        "reference_policy": "one_best_quality_acquisition_per_frozen_identity",
        "reference_count": len(references),
        "reference_count_before_query_content_filter": (
            references_before_query_content_filter
        ),
        "excluded_query_duplicate_reference_count": len(excluded_reference_ids),
        "excluded_query_duplicate_reference_ids": list(excluded_reference_ids),
        "catalog_size": len(catalog),
        "catalog_selected_before_validation": len(selected_catalog),
        "canonical_identity_mismatch_count": canonical_mismatch_count,
        "test_spectrum_count": len(test_spectra),
        "test_molecule_count": len(query_groups),
        "submission_validation": validation.to_dict(),
        "submission_performed": False,
        "submission_requires_explicit_human_approval": True,
        "elapsed_seconds": time.perf_counter() - started,
        "submission_path": str(submission_path),
    }
    (destination / "goal4_selected_inference_report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result
