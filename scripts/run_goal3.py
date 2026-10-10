from __future__ import annotations

import argparse
import json
from pathlib import Path

from casmi26.goal3_pipeline import Goal3ExperimentConfig, run_goal3_experiment


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Goal 3 controlled/realistic fingerprint ranking experiments"
    )
    parser.add_argument("--train", type=Path, default=Path("data/train.parquet"))
    parser.add_argument(
        "--frozen-identities",
        type=Path,
        default=Path("configs/goal3_frozen_identities.txt"),
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/goal3"))
    parser.add_argument("--max-scan-rows", type=int, default=300_000)
    parser.add_argument("--controlled-catalog-size", type=int, default=4096)
    parser.add_argument("--realistic-catalog-size", type=int, default=50_000)
    parser.add_argument("--pool-size", type=int, default=1000)
    parser.add_argument("--fingerprint-bits", type=int, default=512)
    parser.add_argument("--fingerprint-epochs", type=int, default=12)
    parser.add_argument("--fingerprint-batch-size", type=int, default=16)
    parser.add_argument("--bootstrap-samples", type=int, default=500)
    parser.add_argument("--device", default=None)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    results = run_goal3_experiment(
        args.train,
        args.frozen_identities,
        args.output,
        config=Goal3ExperimentConfig(
            seed=args.seed,
            max_scan_rows=args.max_scan_rows,
            controlled_catalog_size=args.controlled_catalog_size,
            realistic_catalog_size=args.realistic_catalog_size,
            candidate_pool_size=args.pool_size,
            fingerprint_bits=args.fingerprint_bits,
            fingerprint_epochs=args.fingerprint_epochs,
            fingerprint_batch_size=args.fingerprint_batch_size,
            bootstrap_samples=args.bootstrap_samples,
            device=args.device,
        ),
    )
    print(
        json.dumps(
            {
                "experiment_id": results["experiment_id"],
                "elapsed_seconds": results["elapsed_seconds"],
                "manifest_hash": results["manifest_hash"],
                "modes": {
                    mode: value["evaluations"]["final_evaluation"]
                    for mode, value in results["modes"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
