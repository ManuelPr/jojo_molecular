from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

from .chemistry import canonical_inchikey14, exact_mass_from_smiles, rdkit_version
from .data import ParquetSpectrumReader, PreprocessConfig, preprocess_spectrum
from .diagnostics import (
    bootstrap_paired_ranking_differences,
    bootstrap_retrieval_confidence_intervals,
    evaluate_retrieval_diagnostics,
)
from .leakage import assert_leakage_free
from .mass_retrieval import MassCandidateIndex, StructureCandidate, merge_candidate_hits
from .ranking import SupervisedRanker
from .retrieval import FEATURE_NAMES, SpectralLibraryIndex
from .schemas import CandidateHit, LibraryEntry, ProcessedSpectrum
from .splits import (
    generate_split,
    spectrum_hash_mapping,
    spectrum_identity_mapping,
)
from .validation_contracts import SplitManifest, ValidationProtocol


PROTOCOLS: tuple[ValidationProtocol, ...] = (
    "library_holdout",
    "molecule_disjoint",
    "novelty_holdout",
)


@dataclass(frozen=True, slots=True)
class ValidationExperimentConfig:
    seed: int = 2026
    max_identities: int = 128
    max_scan_rows: int = 300_000
    max_catalog_structures: int = 4096
    spectra_per_identity: int = 3
    validation_fraction: float = 0.25
    candidate_pool_size: int = 1000
    mass_tolerance_ppm: float = 20.0
    peak_tolerance_da: float = 0.02
    intensity_floor: float = 0.001
    max_peaks: int = 256
    bootstrap_samples: int = 500


def collect_validation_cohort(
    train_path: str | Path,
    config: ValidationExperimentConfig,
) -> list[ProcessedSpectrum]:
    """Select a deterministic, bounded cohort without materializing the train file."""

    spectra, _ = collect_validation_dataset(train_path, config)
    return spectra


def collect_validation_dataset(
    train_path: str | Path,
    config: ValidationExperimentConfig,
) -> tuple[list[ProcessedSpectrum], list[StructureCandidate]]:
    """Collect labeled spectra plus a larger structure-only distractor catalog."""

    if config.spectra_per_identity < 3:
        raise ValueError("Validation requires at least three spectra per identity")
    reader = ParquetSpectrumReader(train_path)
    metadata_columns = [
        name
        for name in (
            "spectrum_id",
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
        if len(key) != 14:
            continue
        counts[key] += 1
        structure_metadata.setdefault(
            key,
            (
                record.normalized_smiles,
                record.molecular_formula,
                record.ingest_lib,
            ),
        )

    eligible = [
        key
        for key, count in counts.items()
        if count >= config.spectra_per_identity
        and canonical_inchikey14(structure_metadata[key][0]) == key
    ]
    ordered = sorted(
        eligible,
        key=lambda key: (
            hashlib.sha256(f"cohort\0{config.seed}\0{key}".encode()).digest(),
            key,
        ),
    )
    selected = set(ordered[: config.max_identities])
    if len(selected) < 8:
        raise RuntimeError(
            f"Only {len(selected)} identities have >= {config.spectra_per_identity} spectra "
            f"within {config.max_scan_rows} rows"
        )

    catalog_order = sorted(
        structure_metadata,
        key=lambda key: (
            0 if key in selected else 1,
            hashlib.sha256(f"catalog\0{config.seed}\0{key}".encode()).digest(),
            key,
        ),
    )
    catalog: list[StructureCandidate] = []
    for key in catalog_order:
        smiles, formula, source = structure_metadata[key]
        if canonical_inchikey14(smiles) != key:
            continue
        exact_mass = exact_mass_from_smiles(smiles)
        if exact_mass is None:
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
        if len(catalog) >= max(config.max_catalog_structures, len(selected)):
            break
    catalog_keys = {candidate.candidate_id for candidate in catalog}
    if not selected <= catalog_keys:
        missing = sorted(selected - catalog_keys)
        raise RuntimeError(f"Selected validation structures missing from catalog: {missing[:5]}")

    preprocessing = PreprocessConfig(
        intensity_floor=config.intensity_floor,
        max_peaks=config.max_peaks,
    )
    spectra: list[ProcessedSpectrum] = []
    retained_counts: Counter[str] = Counter()
    for record in reader.iter_records(max_rows=config.max_scan_rows):
        key = None if record.inchikey14 is None else str(record.inchikey14).strip().upper()
        if key not in selected or retained_counts[key] >= config.spectra_per_identity:
            continue
        if canonical_inchikey14(record.normalized_smiles or "") != key:
            raise ValueError(f"Provided/canonical InChIKey14 mismatch for {record.spectrum_id}")
        try:
            spectrum = preprocess_spectrum(record, preprocessing)
        except ValueError:
            continue
        if not spectrum.mz.size:
            continue
        spectra.append(spectrum)
        retained_counts[key] += 1
        if all(retained_counts[item] >= config.spectra_per_identity for item in selected):
            break

    complete = {
        key for key in selected if retained_counts[key] >= config.spectra_per_identity
    }
    spectra = [spectrum for spectrum in spectra if _identity_key(spectrum) in complete]
    if len(complete) < 8:
        raise RuntimeError(f"Only {len(complete)} selected identities survived preprocessing")
    return sorted(spectra, key=lambda spectrum: spectrum.spectrum_id), catalog


def run_validation_experiment(
    train_path: str | Path,
    output_dir: str | Path,
    *,
    config: ValidationExperimentConfig = ValidationExperimentConfig(),
) -> dict[str, Any]:
    spectra, catalog = collect_validation_dataset(train_path, config)
    return evaluate_validation_spectra(
        spectra,
        output_dir,
        config=config,
        structure_catalog=catalog,
    )


def evaluate_validation_spectra(
    spectra: list[ProcessedSpectrum],
    output_dir: str | Path,
    *,
    config: ValidationExperimentConfig = ValidationExperimentConfig(),
    structure_catalog: list[StructureCandidate] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    output = Path(output_dir)
    manifest_dir = output / "split_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    structures = structure_catalog if structure_catalog is not None else _structure_catalog(spectra)
    structure_by_key = {candidate.candidate_id: candidate for candidate in structures}
    spectra_by_id = {spectrum.spectrum_id: spectrum for spectrum in spectra}
    identity_mapping = spectrum_identity_mapping(spectra)
    hash_mapping = spectrum_hash_mapping(spectra)
    candidate_formula = {
        candidate.candidate_id: candidate.formula or "" for candidate in structures
    }

    protocol_results: dict[str, Any] = {}
    manifests: dict[str, SplitManifest] = {}
    for protocol in PROTOCOLS:
        protocol_started = time.perf_counter()
        manifest = generate_split(
            protocol,
            spectra,
            validation_fraction=config.validation_fraction,
            seed=config.seed,
            candidate_identity_keys=structure_by_key,
        )
        manifests[protocol] = manifest
        manifest.save(manifest_dir / f"{protocol}.json")
        audit = assert_leakage_free(
            manifest,
            spectrum_identity_keys=identity_mapping,
            spectrum_hashes=hash_mapping,
            ranker_train_spectrum_ids=manifest.train_spectrum_ids,
            feature_provenance=_feature_provenance(),
        )

        reference_entries = [
            LibraryEntry(
                candidate_id=_identity_key(spectra_by_id[spectrum_id]),
                smiles=spectra_by_id[spectrum_id].normalized_smiles or "",
                spectrum=spectra_by_id[spectrum_id],
                formula=spectra_by_id[spectrum_id].molecular_formula,
                source=spectra_by_id[spectrum_id].ingest_lib,
            )
            for spectrum_id in manifest.reference_spectrum_ids
        ]
        spectral_index = SpectralLibraryIndex(
            reference_entries,
            mass_tolerance_ppm=config.mass_tolerance_ppm,
            peak_tolerance_da=config.peak_tolerance_da,
        )
        candidate_structures = [
            structure_by_key[key]
            for key in manifest.candidate_identity_keys
            if key in structure_by_key
        ]
        mass_index = MassCandidateIndex(candidate_structures)

        train_queries = _group_queries(
            manifest.train_spectrum_ids, spectra_by_id
        )
        validation_queries = _group_queries(
            manifest.validation_spectrum_ids, spectra_by_id
        )
        train_groups = {
            query_id: _retrieve_union(
                query_spectra,
                mass_index,
                spectral_index,
                pool_size=config.candidate_pool_size,
            )[1]
            for query_id, query_spectra in train_queries.items()
        }
        ranker = SupervisedRanker(random_state=config.seed)
        training_summary = ranker.fit(
            train_groups,
            {query_id: query_id for query_id in train_groups},
        )

        mass_rankings: dict[str, list[str]] = {}
        union_pools: dict[str, list[str]] = {}
        union_rankings: dict[str, list[str]] = {}
        ranker_rankings: dict[str, list[str]] = {}
        query_metadata: dict[str, dict[str, Any]] = {}
        truth_formula: dict[str, str] = {}
        for query_id, query_spectra in validation_queries.items():
            mass_hits, union_hits = _retrieve_union(
                query_spectra,
                mass_index,
                spectral_index,
                pool_size=config.candidate_pool_size,
            )
            mass_rankings[query_id] = [hit.candidate_id for hit in mass_hits]
            union_pools[query_id] = [hit.candidate_id for hit in union_hits]
            union_rankings[query_id] = list(union_pools[query_id])
            ranker_rankings[query_id] = [
                item.candidate_id for item in ranker.rank(union_hits)
            ]
            query_metadata[query_id] = _query_metadata(query_spectra)
            truth_formula[query_id] = query_spectra[0].molecular_formula or ""

        truths = {query_id: query_id for query_id in validation_queries}
        stages = {
            "all_validation": set(truths),
            "model_selection": set(manifest.metadata["model_selection_identity_keys"]),
            "final_evaluation": set(manifest.metadata["final_evaluation_identity_keys"]),
        }
        evaluations: dict[str, Any] = {}
        for stage_name, stage_ids in stages.items():
            stage_truths = {key: truths[key] for key in sorted(stage_ids) if key in truths}
            stage_pools = _select(union_pools, set(stage_truths))
            stage_mass = _select(mass_rankings, set(stage_truths))
            stage_union = _select(union_rankings, set(stage_truths))
            stage_ranker = _select(ranker_rankings, set(stage_truths))
            paired_pools = {
                query_id: _ordered_union(stage_pools[query_id], stage_mass[query_id])
                for query_id in stage_truths
            }
            evaluations[stage_name] = {
                "nearest_mass": _evaluate_method(
                    stage_truths,
                    mass_rankings,
                    mass_rankings,
                    candidate_formula,
                    truth_formula,
                    query_metadata,
                    config,
                ),
                "retrieval_union": _evaluate_method(
                    stage_truths,
                    union_pools,
                    union_rankings,
                    candidate_formula,
                    truth_formula,
                    query_metadata,
                    config,
                ),
                "supervised_ranker": _evaluate_method(
                    stage_truths,
                    union_pools,
                    ranker_rankings,
                    candidate_formula,
                    truth_formula,
                    query_metadata,
                    config,
                ),
                "paired_comparisons": {
                    "retrieval_union_minus_nearest_mass": bootstrap_paired_ranking_differences(
                        stage_truths,
                        paired_pools,
                        stage_mass,
                        stage_union,
                        n_bootstrap=config.bootstrap_samples,
                        seed=config.seed,
                    ),
                    "supervised_ranker_minus_retrieval_union": bootstrap_paired_ranking_differences(
                        stage_truths,
                        stage_pools,
                        stage_union,
                        stage_ranker,
                        n_bootstrap=config.bootstrap_samples,
                        seed=config.seed,
                    ),
                },
            }

        protocol_results[protocol] = {
            "manifest_hash": manifest.manifest_hash,
            "manifest_path": str(Path("split_manifests") / f"{protocol}.json"),
            "audit": audit.to_dict(),
            "training": training_summary.to_dict(),
            "reference_spectra": len(reference_entries),
            "candidate_structures": len(candidate_structures),
            "validation_queries": len(validation_queries),
            "evaluations": evaluations,
            "elapsed_seconds": time.perf_counter() - protocol_started,
        }

    if (
        manifests["molecule_disjoint"].validation_spectrum_ids
        != manifests["novelty_holdout"].validation_spectrum_ids
    ):
        raise AssertionError("Molecule-disjoint and novelty evaluations must be paired")

    results: dict[str, Any] = {
        "experiment_id": "leakage_free_validation_v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "rdkit_version": rdkit_version(),
        "cohort": {
            "spectrum_count": len(spectra),
            "identity_count": len({_identity_key(spectrum) for spectrum in spectra}),
            "structure_catalog_count": len(structures),
        },
        "protocols": protocol_results,
        "elapsed_seconds": time.perf_counter() - started,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "validation_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "config.json").write_text(
        json.dumps(asdict(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results


def _structure_catalog(spectra: list[ProcessedSpectrum]) -> list[StructureCandidate]:
    structures: dict[str, StructureCandidate] = {}
    for spectrum in spectra:
        key = _identity_key(spectrum)
        smiles = spectrum.normalized_smiles or ""
        exact_mass = exact_mass_from_smiles(smiles)
        if exact_mass is None:
            continue
        candidate = StructureCandidate(
            candidate_id=key,
            smiles=smiles,
            exact_mass=exact_mass,
            formula=spectrum.molecular_formula,
            source="train_structure_catalog",
        )
        previous = structures.setdefault(key, candidate)
        if previous.smiles != candidate.smiles:
            raise ValueError(f"Identity {key} maps to multiple normalized SMILES")
    if len(structures) < 8:
        raise RuntimeError("At least eight valid structures are required")
    return [structures[key] for key in sorted(structures)]


def _identity_key(spectrum: ProcessedSpectrum) -> str:
    key = canonical_inchikey14(spectrum.normalized_smiles or "")
    if key is None:
        key = spectrum.inchikey14
    if key is None:
        raise ValueError(f"Missing identity for {spectrum.spectrum_id}")
    return str(key).upper()


def _group_queries(
    spectrum_ids: tuple[str, ...],
    spectra_by_id: dict[str, ProcessedSpectrum],
) -> dict[str, list[ProcessedSpectrum]]:
    grouped: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    for spectrum_id in spectrum_ids:
        spectrum = spectra_by_id[spectrum_id]
        grouped[_identity_key(spectrum)].append(spectrum)
    return {key: sorted(values, key=lambda item: item.spectrum_id) for key, values in grouped.items()}


def _retrieve_union(
    spectra: list[ProcessedSpectrum],
    mass_index: MassCandidateIndex,
    spectral_index: SpectralLibraryIndex,
    *,
    pool_size: int,
) -> tuple[list[CandidateHit], list[CandidateHit]]:
    masses = [
        spectrum.neutral_mass
        for spectrum in spectra
        if spectrum.neutral_mass is not None and math.isfinite(spectrum.neutral_mass)
    ]
    query_mass = float(np.median(masses)) if masses else None
    mass_hits = mass_index.retrieve(query_mass, top_k=pool_size)
    spectral_hits = spectral_index.retrieve_many(spectra, top_k=pool_size)
    return mass_hits, merge_candidate_hits(mass_hits, spectral_hits, top_k=pool_size)


def _query_metadata(spectra: list[ProcessedSpectrum]) -> dict[str, Any]:
    first = spectra[0]
    masses = [spectrum.neutral_mass for spectrum in spectra if spectrum.neutral_mass is not None]
    return {
        "neutral_mass": float(np.median(masses)) if masses else None,
        "formula": first.molecular_formula,
        "adduct": first.adduct,
        "instrument_type": first.instrument,
        "source": first.ingest_lib,
        "acquisition_count": len(spectra),
    }


def _feature_provenance() -> dict[str, tuple[str, ...]]:
    return {
        name: (
            "query_spectrum",
            "reference_spectrum_or_candidate_structure",
        )
        for name in FEATURE_NAMES
    }


def _select(mapping: dict[str, list[str]], keys: set[str]) -> dict[str, list[str]]:
    return {key: mapping[key] for key in sorted(keys) if key in mapping}


def _ordered_union(first: list[str], second: list[str]) -> list[str]:
    return list(dict.fromkeys([*first, *second]))


def _evaluate_method(
    truths: dict[str, str],
    pools: dict[str, list[str]],
    rankings: dict[str, list[str]],
    candidate_formula: dict[str, str],
    truth_formula: dict[str, str],
    query_metadata: dict[str, dict[str, Any]],
    config: ValidationExperimentConfig,
) -> dict[str, Any]:
    keys = set(truths)
    selected_pools = _select(pools, keys)
    selected_rankings = _select(rankings, keys)
    diagnostics = evaluate_retrieval_diagnostics(
        truths,
        selected_pools,
        selected_rankings,
        candidate_formula_by_id=candidate_formula,
        truth_formula_by_query={key: truth_formula[key] for key in keys},
        query_metadata={key: query_metadata[key] for key in keys},
    )
    confidence_intervals = bootstrap_retrieval_confidence_intervals(
        truths,
        selected_pools,
        selected_rankings,
        candidate_formula_by_id=candidate_formula,
        truth_formula_by_query={key: truth_formula[key] for key in keys},
        n_bootstrap=config.bootstrap_samples,
        seed=config.seed,
    )
    return {
        "metrics": diagnostics.to_dict(),
        "confidence_intervals": confidence_intervals,
    }
