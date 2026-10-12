"""Build and benchmark a Goal 5 C1 mass/formula index on Kaggle.

This script performs no training and never reads target structures.  It is
intended for a private, Internet-disabled Kaggle run against the competition
train/test Parquet files.  The resulting JSON is the evidence needed before
integrating C1 into E6.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
from itertools import islice
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from casmi26.chemistry import neutral_mass_from_mz
from casmi26.scalable_retrieval import (
    DynamicPoolConfig,
    RetrievalCache,
    RetrievalRequest,
    ScalableMassFormulaIndex,
    batch_retrieve_dynamic_pools,
    build_streaming_structure_catalog,
    iter_parquet_structure_rows,
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _test_requests(path: Path, batch_size: int) -> tuple[RetrievalRequest, ...]:
    parquet = pq.ParquetFile(path)
    required = {"molecule_id", "precursor_mz", "adduct"}
    missing = sorted(required - set(parquet.schema_arrow.names))
    if missing:
        raise ValueError(f"Test Parquet is missing columns: {missing}")
    masses: dict[str, list[float]] = defaultdict(list)
    for batch in parquet.iter_batches(batch_size=batch_size, columns=sorted(required)):
        for row in batch.to_pylist():
            mass = neutral_mass_from_mz(float(row["precursor_mz"]), str(row["adduct"]))
            if mass is not None and np.isfinite(mass) and mass > 0:
                masses[str(row["molecule_id"])].append(float(mass))
    return tuple(
        RetrievalRequest(query_id, float(np.median(values)))
        for query_id, values in sorted(masses.items())
        if values
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-parquet", type=Path, required=True)
    parser.add_argument("--test-parquet", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tier-name", default="C1_train_unique")
    parser.add_argument("--batch-size", type=int, default=65_536)
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--hash-inputs", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.batch_size <= 0 or args.max_rows < 0:
        raise ValueError("batch-size must be positive and max-rows non-negative")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    rows = iter_parquet_structure_rows(args.train_parquet, batch_size=args.batch_size)
    if args.max_rows:
        rows = islice(rows, args.max_rows)
    build_started = time.perf_counter()
    catalog, catalog_report = build_streaming_structure_catalog(rows)
    catalog_seconds = time.perf_counter() - build_started

    index_started = time.perf_counter()
    index = ScalableMassFormulaIndex.build(catalog, tier_name=args.tier_name)
    index_manifest = index.save(args.output_dir / "index")
    index_seconds = time.perf_counter() - index_started

    benchmark: dict[str, Any] | None = None
    if args.test_parquet is not None:
        requests = _test_requests(args.test_parquet, args.batch_size)
        config = DynamicPoolConfig()
        cache = RetrievalCache()
        _, cold = batch_retrieve_dynamic_pools(
            index, requests, config=config, cache=cache
        )
        _, warm = batch_retrieve_dynamic_pools(
            index, requests, config=config, cache=cache
        )
        benchmark = {
            "request_count": len(requests),
            "config": {
                "ppm_schedule": list(config.ppm_schedule),
                "target_pool_size": config.target_pool_size,
                "maximum_pool_size": config.maximum_pool_size,
                "cheap_stage_size": config.cheap_stage_size,
                "expensive_stage_size": config.expensive_stage_size,
            },
            "cold": cold.to_dict(),
            "warm": warm.to_dict(),
        }

    input_hashes: dict[str, str] = {}
    if args.hash_inputs:
        input_hashes["train_parquet"] = _sha256_file(args.train_parquet)
        if args.test_parquet is not None:
            input_hashes["test_parquet"] = _sha256_file(args.test_parquet)
    report = {
        "experiment_id": "goal5_c1_index_benchmark_v1",
        "train_parquet": str(args.train_parquet),
        "test_parquet": str(args.test_parquet) if args.test_parquet else None,
        "input_sha256": input_hashes,
        "max_rows": args.max_rows or None,
        "catalog": catalog_report.to_dict(),
        "index_manifest": index_manifest.to_dict(),
        "catalog_build_seconds": catalog_seconds,
        "index_build_and_save_seconds": index_seconds,
        "retrieval_benchmark": benchmark,
        "elapsed_seconds": time.perf_counter() - started,
        "target_consulted": False,
        "submission_performed": False,
    }
    (args.output_dir / "goal5_retrieval_benchmark.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
