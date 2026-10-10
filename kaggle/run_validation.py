"""Offline Kaggle entrypoint for leakage-free validation; never submits."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def install_offline_assets() -> None:
    wheels = sorted(Path("/kaggle/input").glob("**/*.whl"))
    python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    rdkit_wheels = [
        path for path in wheels if path.name.startswith("rdkit-") and python_tag in path.name
    ]
    package_wheels = [path for path in wheels if path.name.startswith("casmi26_baseline-")]
    if len(rdkit_wheels) != 1 or len(package_wheels) != 1:
        raise RuntimeError(
            f"Expected one {python_tag} RDKit wheel and one project wheel; found {wheels}"
        )
    for wheel in (rdkit_wheels[0], package_wheels[0]):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(wheel),
            ],
            check=True,
        )


def find_competition_root() -> Path:
    configured = os.environ.get("CASMI_INPUT_ROOT")
    if configured:
        root = Path(configured)
        if not root.is_dir():
            raise RuntimeError(f"CASMI_INPUT_ROOT does not exist: {root}")
        return root
    roots = [
        path.parent
        for path in sorted(Path("/kaggle/input").glob("**/train.parquet"))
        if (path.parent / "test.parquet").is_file()
    ]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one attached CASMI competition dataset, found: {roots}")
    return roots[0]


install_offline_assets()

from casmi26.chemistry import rdkit_version
from casmi26.validation_pipeline import ValidationExperimentConfig, run_validation_experiment


if rdkit_version() != "2026.03.3":
    raise RuntimeError(f"Unexpected RDKit version: {rdkit_version()}")

root = find_competition_root()
results = run_validation_experiment(
    root / "train.parquet",
    Path("/kaggle/working/validation"),
    config=ValidationExperimentConfig(
        seed=int(os.environ.get("CASMI_SEED", "2026")),
        max_identities=int(os.environ.get("CASMI_MAX_IDENTITIES", "128")),
        max_scan_rows=int(os.environ.get("CASMI_MAX_SCAN_ROWS", "300000")),
        max_catalog_structures=int(os.environ.get("CASMI_MAX_CATALOG_STRUCTURES", "4096")),
        candidate_pool_size=int(os.environ.get("CASMI_POOL_SIZE", "1000")),
        bootstrap_samples=int(os.environ.get("CASMI_BOOTSTRAP_SAMPLES", "500")),
    ),
)
summary = {
    "experiment_id": results["experiment_id"],
    "cohort": results["cohort"],
    "elapsed_seconds": results["elapsed_seconds"],
    "protocols": {
        name: {
            "audit_passed": value["audit"]["passed"],
            "final": value["evaluations"]["final_evaluation"],
        }
        for name, value in results["protocols"].items()
    },
}
print(json.dumps(summary, indent=2, sort_keys=True))
