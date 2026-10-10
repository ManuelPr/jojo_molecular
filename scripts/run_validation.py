from __future__ import annotations

import argparse
import json

from casmi26.validation_pipeline import ValidationExperimentConfig, run_validation_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run leakage-free CASMI validation protocols")
    parser.add_argument("--train", default="data/train.parquet")
    parser.add_argument("--output", default="artifacts/validation")
    parser.add_argument("--max-identities", type=int, default=128)
    parser.add_argument("--max-scan-rows", type=int, default=300_000)
    parser.add_argument("--max-catalog-structures", type=int, default=4096)
    parser.add_argument("--pool-size", type=int, default=1000)
    parser.add_argument("--bootstrap-samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    config = ValidationExperimentConfig(
        seed=args.seed,
        max_identities=args.max_identities,
        max_scan_rows=args.max_scan_rows,
        max_catalog_structures=args.max_catalog_structures,
        candidate_pool_size=args.pool_size,
        bootstrap_samples=args.bootstrap_samples,
    )
    results = run_validation_experiment(args.train, args.output, config=config)
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
