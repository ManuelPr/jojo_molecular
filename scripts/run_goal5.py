from __future__ import annotations

import argparse
import json
from pathlib import Path

from casmi26.goal5_pipeline import Goal5ExperimentConfig
from casmi26.goal5_run import run_goal5_full


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run CASMI Goal 5 private experiments; never submits"
    )
    parser.add_argument("--train", type=Path, default=Path("data/train.parquet"))
    parser.add_argument("--test", type=Path, default=Path("data/test.parquet"))
    parser.add_argument(
        "--frozen-identities",
        type=Path,
        default=Path("configs/goal3_frozen_identities.txt"),
    )
    parser.add_argument(
        "--prior-final-identities",
        type=Path,
        default=Path("configs/goal5_prior_final_identities.txt"),
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/goal5"))
    parser.add_argument("--background-identities", type=int, default=2_000)
    parser.add_argument("--dynamic-pool-size", type=int, default=1_000)
    parser.add_argument("--bootstrap", type=int, default=500)
    args = parser.parse_args()
    results = run_goal5_full(
        args.train,
        args.test,
        args.frozen_identities,
        args.prior_final_identities,
        args.output,
        config=Goal5ExperimentConfig(
            background_reference_identities=args.background_identities,
            dynamic_pool_size=args.dynamic_pool_size,
            bootstrap_samples=args.bootstrap,
        ),
    )
    print(
        json.dumps(
            {
                "experiment_id": results["experiment_id"],
                "domain_plan_hash": results["domain_plan_hash"],
                "official_submission": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
