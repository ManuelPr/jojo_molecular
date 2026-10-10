from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import time

import numpy as np

from .chemistry import canonical_inchikey14, rdkit_version
from .data import ParquetSpectrumReader, PreprocessConfig, preprocess_spectrum
from .metrics import evaluate_rankings
from .ranking import SupervisedRanker
from .retrieval import SpectralLibraryIndex
from .schemas import LibraryEntry, ProcessedSpectrum
from .submission import write_submission


@dataclass(frozen=True, slots=True)
class MiniTrainConfig:
    seed: int = 2026
    max_molecules: int = 128
    max_scan_rows: int = 300_000
    top_k: int = 25
    validation_fraction: float = 0.25
    mass_tolerance_ppm: float = 20.0
    peak_tolerance_da: float = 0.02
    intensity_floor: float = 0.001
    max_peaks: int = 256


def collect_library_holdout(
    train_path: str | Path,
    config: MiniTrainConfig,
) -> tuple[list[LibraryEntry], dict[str, ProcessedSpectrum]]:
    preprocessing = PreprocessConfig(
        intensity_floor=config.intensity_floor,
        max_peaks=config.max_peaks,
    )
    grouped: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    completed: set[str] = set()
    reader = ParquetSpectrumReader(train_path)
    for record in reader.iter_records(max_rows=config.max_scan_rows):
        key = record.inchikey14
        if key is None or record.normalized_smiles is None or len(grouped[key]) >= 2:
            continue
        try:
            processed = preprocess_spectrum(record, preprocessing)
        except ValueError:
            continue
        if processed.mz.size == 0:
            continue
        grouped[key].append(processed)
        if len(grouped[key]) == 2:
            completed.add(key)
        if len(completed) >= config.max_molecules:
            break

    eligible = sorted(key for key, spectra in grouped.items() if len(spectra) >= 2)
    if len(eligible) < 8:
        raise RuntimeError(
            f"Only {len(eligible)} structures with >=2 spectra found in {config.max_scan_rows} rows"
        )
    eligible = eligible[: config.max_molecules]
    library: list[LibraryEntry] = []
    queries: dict[str, ProcessedSpectrum] = {}
    for key in eligible:
        reference, query = grouped[key][0], grouped[key][1]
        library.append(
            LibraryEntry(
                candidate_id=key,
                smiles=reference.normalized_smiles or "",
                spectrum=reference,
                formula=reference.molecular_formula,
                source=reference.ingest_lib,
            )
        )
        queries[key] = query
    return library, queries


def run_mini_training(
    train_path: str | Path,
    test_path: str | Path,
    output_dir: str | Path,
    *,
    config: MiniTrainConfig = MiniTrainConfig(),
    submission_path: str | Path | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    library, queries = collect_library_holdout(train_path, config)
    index = SpectralLibraryIndex(
        library,
        mass_tolerance_ppm=config.mass_tolerance_ppm,
        peak_tolerance_da=config.peak_tolerance_da,
    )

    candidate_groups = {
        query_id: index.retrieve(query, top_k=config.top_k)
        for query_id, query in queries.items()
    }
    query_ids = sorted(queries)
    random.Random(config.seed).shuffle(query_ids)
    validation_size = max(1, int(round(len(query_ids) * config.validation_fraction)))
    validation_ids = set(query_ids[:validation_size])
    training_ids = [query_id for query_id in query_ids if query_id not in validation_ids]

    train_groups = {query_id: candidate_groups[query_id] for query_id in training_ids}
    truths = {query_id: query_id for query_id in query_ids}
    ranker = SupervisedRanker(random_state=config.seed)
    training_summary = ranker.fit(train_groups, truths)
    ranker_path = output / "ranker.joblib"
    ranker.save(ranker_path)

    retrieval_rankings = {
        query_id: [hit.candidate_id for hit in candidate_groups[query_id]]
        for query_id in validation_ids
    }
    ranked = {
        query_id: [item.candidate_id for item in ranker.rank(candidate_groups[query_id])]
        for query_id in validation_ids
    }
    validation_truths = {query_id: query_id for query_id in validation_ids}
    retrieval_metrics = evaluate_rankings(validation_truths, retrieval_rankings)
    ranker_metrics = evaluate_rankings(validation_truths, ranked)

    test_reader = ParquetSpectrumReader(test_path)
    preprocessing = PreprocessConfig(
        intensity_floor=config.intensity_floor,
        max_peaks=config.max_peaks,
    )
    test_groups: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    test_ids: set[str] = set()
    for record in test_reader.iter_records():
        test_ids.add(record.molecule_id)
        try:
            spectrum = preprocess_spectrum(record, preprocessing)
        except ValueError:
            continue
        if spectrum.mz.size:
            test_groups[spectrum.molecule_id].append(spectrum)

    fallback_smiles = [entry.smiles for entry in library]
    predictions: dict[str, list[str]] = {}
    for molecule_id in sorted(test_ids):
        hits = index.retrieve_many(test_groups[molecule_id], top_k=max(config.top_k, 25))
        ranked_candidates = ranker.rank(hits)
        smiles = [candidate.smiles for candidate in ranked_candidates]
        if len(smiles) < 25:
            smiles.extend(fallback_smiles)
        predictions[molecule_id] = smiles

    expected_ids = sorted(test_ids)
    submission_destination = Path(submission_path) if submission_path else output / "submission.csv"
    submission_validation = write_submission(predictions, expected_ids, submission_destination)

    elapsed = time.perf_counter() - started
    metrics: dict[str, object] = {
        "run_type": "mini_training",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "rdkit_version": rdkit_version(),
        "train_first_mib_sha256": _sha256_head(Path(train_path)),
        "test_first_mib_sha256": _sha256_head(Path(test_path)),
        "library_molecules": len(library),
        "training": training_summary.to_dict(),
        "validation_queries": len(validation_ids),
        "retrieval": retrieval_metrics.to_dict(),
        "ranker": ranker_metrics.to_dict(),
        "submission": submission_validation.to_dict(),
        "elapsed_seconds": elapsed,
    }
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    (output / "config.json").write_text(
        json.dumps(asdict(config), indent=2, sort_keys=True), encoding="utf-8"
    )
    return metrics


def _sha256_head(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(chunk_size))
    return digest.hexdigest()
