"""Fail-fast recovery inference for the first zero-score submission.

The Goal 4 E6 ranking rule and its frozen 127-spectrum reference library are
kept unchanged.  The only model-facing change is replacing the truncated C0
candidate catalog with the verified full-train C1 mass/formula index.
"""

from __future__ import annotations

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

from .analog_propagation import LeakagePolicy, spectrum_content_hash
from .chemistry import canonical_inchikey14, rdkit_version
from .data import PreprocessConfig, read_processed
from .goal3_contracts import FingerprintSpec
from .goal3_pipeline import Goal3ExperimentConfig, collect_goal3_dataset
from .goal4_inference import (
    _representative_reference_ids,
    exclude_query_duplicate_references,
    group_query_spectra,
)
from .goal4_pipeline import Goal4ExperimentConfig, _reference_library
from .goal5_pipeline import _e6_rank, _query_mass
from .mass_retrieval import StructureCandidate
from .scalable_analog import ScalableAnalogIndex
from .scalable_retrieval import ScalableMassFormulaIndex
from .schemas import CandidateHit, ProcessedSpectrum
from .submission import clean_candidates, write_submission


@dataclass(frozen=True, slots=True)
class RecoveryInferenceConfig:
    seed: int = 2026
    max_scan_rows: int = 300_000
    realistic_catalog_size: int = 50_000
    spectra_per_identity: int = 3
    retrieval_pool_size: int = 100
    output_size: int = 25
    analog_top_k: int = 5
    analog_mass_window_da: float = 200.0
    peak_tolerance_da: float = 0.02
    fingerprint_bits: int = 512
    evidence_weight: float = 0.5
    max_peaks: int = 256
    intensity_floor: float = 0.001
    expected_c1_structure_count: int = 271_439

    def validate(self) -> None:
        if self.retrieval_pool_size < self.output_size:
            raise ValueError("retrieval_pool_size must cover output_size")
        if self.output_size <= 0 or self.output_size > 25:
            raise ValueError("output_size must be between 1 and 25")
        if self.evidence_weight != 0.5:
            raise ValueError("Frozen E6 evidence_weight must remain 0.5")
        if self.expected_c1_structure_count <= self.realistic_catalog_size:
            raise ValueError("C1 must be larger than the rejected C0 catalog")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_from_hit(hit: CandidateHit) -> StructureCandidate:
    mass = float(hit.metadata.get("exact_mass", math.nan))
    if not math.isfinite(mass) or mass <= 0:
        raise RuntimeError(f"C1 hit has invalid exact mass: {hit.candidate_id}")
    return StructureCandidate(
        candidate_id=hit.candidate_id,
        smiles=hit.smiles,
        exact_mass=mass,
        formula=hit.metadata.get("formula"),
        source=hit.source,
    )


def predict_frozen_e6_on_c1(
    query_groups: Mapping[str, Sequence[ProcessedSpectrum]],
    c1_index: ScalableMassFormulaIndex,
    references: Sequence[Any],
    *,
    config: RecoveryInferenceConfig,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Rank C1 candidates with the unchanged Goal 4 E6 rule."""

    config.validate()
    if len(c1_index) != config.expected_c1_structure_count:
        raise RuntimeError(
            "Unexpected C1 structure count: "
            f"expected={config.expected_c1_structure_count}, actual={len(c1_index)}"
        )
    if not references:
        raise RuntimeError("Frozen E6 reference library is empty")
    analog_index = ScalableAnalogIndex(references)
    forbidden_hashes = frozenset(
        spectrum_content_hash(spectrum)
        for spectra in query_groups.values()
        for spectrum in spectra
    )
    fingerprint_cache: dict[str, np.ndarray] = {}
    fingerprint_spec = FingerprintSpec(n_bits=config.fingerprint_bits)
    predictions: dict[str, list[str]] = {}
    per_query: dict[str, Any] = {}
    total_retrieval_seconds = 0.0
    total_ranking_seconds = 0.0
    for molecule_id in sorted(query_groups):
        spectra = query_groups[molecule_id]
        query_mass = _query_mass(spectra)
        started = time.perf_counter()
        hits = c1_index.retrieve(query_mass, top_k=config.retrieval_pool_size)
        total_retrieval_seconds += time.perf_counter() - started
        if len(hits) < config.output_size:
            raise RuntimeError(
                f"C1 returned only {len(hits)} candidates for {molecule_id}"
            )
        candidate_by_id = {
            hit.candidate_id: _candidate_from_hit(hit) for hit in hits
        }
        analog_hits, analog_report = analog_index.retrieve(
            spectra,
            query_neutral_mass=query_mass,
            policy=LeakagePolicy(
                forbidden_spectrum_hashes=forbidden_hashes,
                allow_same_identity=True,
            ),
            mass_window_da=config.analog_mass_window_da,
            top_k=config.analog_top_k,
            tolerance_da=config.peak_tolerance_da,
        )
        started = time.perf_counter()
        ranking = _e6_rank(
            hits,
            candidate_by_id=candidate_by_id,
            analog_hits=analog_hits,
            query_mass=query_mass,
            fingerprint_cache=fingerprint_cache,
            spec=fingerprint_spec,
            evidence_weight=config.evidence_weight,
            expensive_limit=config.retrieval_pool_size,
        )
        total_ranking_seconds += time.perf_counter() - started
        ranked_smiles = [candidate_by_id[key].smiles for key in ranking]
        cleaned = clean_candidates(ranked_smiles, limit=config.output_size)
        if len(cleaned) != config.output_size:
            raise RuntimeError(
                f"Official canonicalization left {len(cleaned)} candidates for {molecule_id}"
            )
        predictions[molecule_id] = cleaned
        per_query[molecule_id] = {
            "neutral_mass": query_mass,
            "spectrum_count": len(spectra),
            "retrieved_candidates": len(hits),
            "output_candidates": len(cleaned),
            "best_mass_error_ppm": float(hits[0].features["mass_error_ppm"]),
            "worst_pool_mass_error_ppm": float(hits[-1].features["mass_error_ppm"]),
            "analog": analog_report.to_dict(),
        }
    return predictions, {
        "query_count": len(predictions),
        "reference_spectra": len(analog_index),
        "reference_identities": analog_index.identity_count,
        "retrieval_seconds": total_retrieval_seconds,
        "ranking_seconds": total_ranking_seconds,
        "per_query": per_query,
    }


def run_recovery_c1_inference(
    train_path: str | Path,
    test_path: str | Path,
    sample_submission_path: str | Path,
    frozen_identity_path: str | Path,
    c1_index_path: str | Path,
    output_dir: str | Path,
    *,
    config: RecoveryInferenceConfig = RecoveryInferenceConfig(),
) -> dict[str, Any]:
    """Generate the C1+frozen-E6 recovery CSV; never invoke Kaggle submit."""

    config.validate()
    if config.output_size != 25:
        raise ValueError("Official recovery inference requires exactly 25 outputs")
    started = time.perf_counter()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    index_directory = Path(c1_index_path)
    manifest_path = index_directory / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing C1 manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("tier_name") != "C1_train_unique":
        raise RuntimeError(f"Unexpected C1 tier: {manifest.get('tier_name')!r}")
    if manifest.get("structure_count") != config.expected_c1_structure_count:
        raise RuntimeError(
            "C1 manifest structure count mismatch: "
            f"{manifest.get('structure_count')!r}"
        )
    if manifest.get("rdkit_version") != rdkit_version():
        raise RuntimeError("C1 index RDKit version differs from inference RDKit")
    c1_index = ScalableMassFormulaIndex.load(
        index_directory, mmap=True, verify_hashes=True
    )

    # Recreate exactly the reference side of the frozen Goal 4 E6 pipeline.
    goal4_config = Goal4ExperimentConfig(
        seed=config.seed,
        max_scan_rows=config.max_scan_rows,
        spectra_per_identity=config.spectra_per_identity,
        realistic_catalog_size=config.realistic_catalog_size,
        candidate_pool_size=config.retrieval_pool_size,
        analog_top_k=config.analog_top_k,
        peak_tolerance_da=config.peak_tolerance_da,
        fingerprint_bits=config.fingerprint_bits,
        max_peaks=config.max_peaks,
        intensity_floor=config.intensity_floor,
        bootstrap_samples=1,
        ranker_backend="hist_gbdt",
    )
    collection = collect_goal3_dataset(
        train_path,
        frozen_identity_path,
        Goal3ExperimentConfig(
            seed=config.seed,
            max_scan_rows=config.max_scan_rows,
            spectra_per_identity=config.spectra_per_identity,
            realistic_catalog_size=config.realistic_catalog_size,
            candidate_pool_size=config.retrieval_pool_size,
            max_peaks=config.max_peaks,
            intensity_floor=config.intensity_floor,
            peak_tolerance_da=config.peak_tolerance_da,
            fingerprint_bits=config.fingerprint_bits,
        ),
    )
    selected_catalog = list(collection.source_catalog[: config.realistic_catalog_size])
    frozen_catalog = [
        candidate
        for candidate in selected_catalog
        if canonical_inchikey14(candidate.smiles) == candidate.candidate_id
    ]
    frozen_candidate_by_id = {
        candidate.candidate_id: candidate for candidate in frozen_catalog
    }
    spectra_by_id = {spectrum.spectrum_id: spectrum for spectrum in collection.spectra}
    fingerprint_cache: dict[str, np.ndarray] = {}
    references = _reference_library(
        _representative_reference_ids(collection.spectra),
        spectra_by_id,
        frozen_candidate_by_id,
        fingerprint_cache,
        FingerprintSpec(n_bits=config.fingerprint_bits),
    )

    test_spectra = list(
        read_processed(
            test_path,
            config=PreprocessConfig(
                intensity_floor=config.intensity_floor,
                max_peaks=config.max_peaks,
            ),
        )
    )
    query_groups = group_query_spectra(test_spectra)
    expected_ids = pd.read_csv(sample_submission_path, usecols=["molecule_id"])[
        "molecule_id"
    ].astype(str).tolist()
    if len(expected_ids) != len(set(expected_ids)):
        raise RuntimeError("Sample submission contains duplicate molecule IDs")
    if set(query_groups) != set(expected_ids):
        raise RuntimeError(
            "Test/query molecule IDs differ from sample submission: "
            f"missing={len(set(expected_ids) - set(query_groups))}, "
            f"extra={len(set(query_groups) - set(expected_ids))}"
        )
    references_before_filter = len(references)
    references, excluded_reference_ids = exclude_query_duplicate_references(
        references, test_spectra
    )
    predictions, inference_diagnostics = predict_frozen_e6_on_c1(
        query_groups,
        c1_index,
        references,
        config=config,
    )
    submission_path = destination / "submission.csv"
    validation = write_submission(predictions, expected_ids, submission_path)
    if validation.min_candidates != 25 or validation.max_candidates != 25:
        raise RuntimeError("Recovery submission must contain exactly 25 candidates per row")
    result = {
        "experiment_id": "recovery_c1_frozen_e6_v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cause_fixed": "C0_truncated_49k_catalog_replaced_by_verified_C1_full_train_index",
        "ranking_contract": "Goal4_E6_frozen_analog_score_weight_0.5_same_formula",
        "config": asdict(config),
        "rdkit_version": rdkit_version(),
        "c1_manifest_sha256": _sha256_file(manifest_path),
        "c1_structure_count": len(c1_index),
        "reference_count_before_query_filter": references_before_filter,
        "excluded_query_duplicate_reference_count": len(excluded_reference_ids),
        "excluded_query_duplicate_reference_ids": list(excluded_reference_ids),
        "test_spectrum_count": len(test_spectra),
        "test_molecule_count": len(query_groups),
        "inference": inference_diagnostics,
        "submission_validation": validation.to_dict(),
        "submission_performed": False,
        "elapsed_seconds": time.perf_counter() - started,
        "submission_path": str(submission_path),
    }
    (destination / "recovery_inference_report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result
