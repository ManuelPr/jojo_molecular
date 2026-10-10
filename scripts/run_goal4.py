from __future__ import annotations

import argparse
import json
from pathlib import Path

from casmi26.goal4_pipeline import Goal4ExperimentConfig, run_goal4_experiment


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CASMI 2026 Goal 4 bounded experiments")
    parser.add_argument("--train", type=Path, default=Path("data/train.parquet"))
    parser.add_argument(
        "--frozen-identities",
        type=Path,
        default=Path("configs/goal3_frozen_identities.txt"),
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/goal4"))
    parser.add_argument("--catalog-size", type=int, default=50_000)
    parser.add_argument("--pool-size", type=int, default=100)
    parser.add_argument("--analog-top-k", type=int, default=5)
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument(
        "--ranker-backend",
        choices=("hist_gbdt", "lightgbm"),
        default="lightgbm",
    )
    args = parser.parse_args()
    result = run_goal4_experiment(
        args.train,
        args.frozen_identities,
        args.output,
        config=Goal4ExperimentConfig(
            realistic_catalog_size=args.catalog_size,
            candidate_pool_size=args.pool_size,
            analog_top_k=args.analog_top_k,
            bootstrap_samples=args.bootstrap,
            ranker_backend=args.ranker_backend,
        ),
    )
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "selected": result["selected_by_model_selection"],
                "final": result["selected_final_evaluation"],
                "elapsed_seconds": result["elapsed_seconds"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

