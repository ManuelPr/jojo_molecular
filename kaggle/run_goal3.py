"""Offline Kaggle T4 entrypoint for Goal 3; this script never submits."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def install_offline_assets() -> Path:
    wheels = sorted(Path("/kaggle/input").glob("**/*.whl"))
    python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    rdkit_wheels = [
        path for path in wheels if path.name.startswith("rdkit-") and python_tag in path.name
    ]
    project_wheels = [path for path in wheels if path.name.startswith("casmi26_baseline-")]
    if len(rdkit_wheels) != 1 or len(project_wheels) != 1:
        raise RuntimeError(
            f"Expected one {python_tag} RDKit wheel and one project wheel; found {wheels}"
        )
    for wheel in (rdkit_wheels[0], project_wheels[0]):
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
    identity_files = sorted(Path("/kaggle/input").glob("**/goal3_frozen_identities.txt"))
    if len(identity_files) != 1:
        raise RuntimeError(f"Expected one frozen identity file, found: {identity_files}")
    return identity_files[0]


def find_competition_root() -> Path:
    roots = [
        path.parent
        for path in sorted(Path("/kaggle/input").glob("**/train.parquet"))
        if (path.parent / "test.parquet").is_file()
    ]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one CASMI competition dataset, found: {roots}")
    return roots[0]


frozen_identity_path = install_offline_assets()

import lightgbm
import torch

from casmi26.chemistry import rdkit_version
from casmi26.fingerprint_model import compact_tiny_overfit_smoke
from casmi26.goal3_pipeline import Goal3ExperimentConfig, run_goal3_experiment


if rdkit_version() != "2026.03.3":
    raise RuntimeError(f"Unexpected RDKit version: {rdkit_version()}")
if not torch.cuda.is_available():
    raise RuntimeError("Goal 3 Kaggle smoke requires a CUDA GPU")

root = find_competition_root()
output_dir = Path("/kaggle/working/goal3")
output_dir.mkdir(parents=True, exist_ok=True)
tiny_overfit = compact_tiny_overfit_smoke(device="cuda")
(output_dir / "goal3_runtime_smoke.json").write_text(
    json.dumps(tiny_overfit, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
results = run_goal3_experiment(
    root / "train.parquet",
    frozen_identity_path,
    output_dir,
    config=Goal3ExperimentConfig(
        seed=int(os.environ.get("CASMI_SEED", "2026")),
        max_scan_rows=int(os.environ.get("CASMI_MAX_SCAN_ROWS", "300000")),
        controlled_catalog_size=int(os.environ.get("CASMI_CONTROLLED_CATALOG", "4096")),
        realistic_catalog_size=int(os.environ.get("CASMI_REALISTIC_CATALOG", "50000")),
        candidate_pool_size=int(os.environ.get("CASMI_POOL_SIZE", "1000")),
        fingerprint_bits=int(os.environ.get("CASMI_FP_BITS", "512")),
        fingerprint_epochs=int(os.environ.get("CASMI_FP_EPOCHS", "12")),
        fingerprint_batch_size=int(os.environ.get("CASMI_FP_BATCH", "16")),
        bootstrap_samples=int(os.environ.get("CASMI_BOOTSTRAP_SAMPLES", "500")),
        device="cuda",
    ),
)
summary = {
    "experiment_id": results["experiment_id"],
    "torch_version": torch.__version__,
    "lightgbm_version": lightgbm.__version__,
    "gpu": torch.cuda.get_device_name(0),
    "tiny_overfit": tiny_overfit,
    "elapsed_seconds": results["elapsed_seconds"],
    "final": {
        mode: value["evaluations"]["final_evaluation"]
        for mode, value in results["modes"].items()
    },
}
print(json.dumps(summary, indent=2, sort_keys=True))
