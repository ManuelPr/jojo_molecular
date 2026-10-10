"""Private offline Goal 4 experiment and inference rehearsal; never submits."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
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
    identities = sorted(Path("/kaggle/input").glob("**/goal3_frozen_identities.txt"))
    if len(identities) != 1:
        raise RuntimeError(f"Expected one frozen identity file, found: {identities}")
    return identities[0]


def find_competition_root() -> Path:
    roots = [
        path.parent
        for path in sorted(Path("/kaggle/input").glob("**/train.parquet"))
        if (path.parent / "test.parquet").is_file()
        and (path.parent / "sample_submission.csv").is_file()
    ]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one CASMI competition dataset, found: {roots}")
    return roots[0]


frozen_identity_path = install_offline_assets()

import lightgbm

from casmi26.chemistry import rdkit_version
from casmi26.goal4_inference import run_goal4_selected_inference
from casmi26.goal4_pipeline import Goal4ExperimentConfig, run_goal4_experiment


if rdkit_version() != "2026.03.3":
    raise RuntimeError(f"Unexpected RDKit version: {rdkit_version()}")

root = find_competition_root()
experiment = run_goal4_experiment(
    root / "train.parquet",
    frozen_identity_path,
    Path("/kaggle/working/goal4"),
    config=Goal4ExperimentConfig(
        seed=int(os.environ.get("CASMI_SEED", "2026")),
        max_scan_rows=int(os.environ.get("CASMI_MAX_SCAN_ROWS", "300000")),
        realistic_catalog_size=int(os.environ.get("CASMI_REALISTIC_CATALOG", "50000")),
        candidate_pool_size=int(os.environ.get("CASMI_POOL_SIZE", "100")),
        analog_top_k=int(os.environ.get("CASMI_ANALOG_TOP_K", "5")),
        bootstrap_samples=int(os.environ.get("CASMI_BOOTSTRAP_SAMPLES", "500")),
        ranker_backend="lightgbm",
    ),
)
selected_experiment = experiment["selected_by_model_selection"]
if selected_experiment not in {"E0", "E3", "E6", "E7"}:
    selected_experiment = "E3"
e3_selection = experiment["model_selection"]["E3"]
selected_feature = e3_selection.get("selected_aggregation_feature", "analog_score")
selected_weight = float(
    e3_selection.get("selected_weight", e3_selection.get("weight", 0.0))
)
gate_threshold = float(experiment["model_selection"].get("E7", {}).get("threshold", 0.0))
inference = run_goal4_selected_inference(
    root / "train.parquet",
    root / "test.parquet",
    root / "sample_submission.csv",
    frozen_identity_path,
    Path("/kaggle/working/goal4_inference"),
    selected_experiment=selected_experiment,
    selected_feature=selected_feature,
    evidence_weight=selected_weight,
    gate_threshold=gate_threshold,
    config=Goal4ExperimentConfig(
        seed=int(os.environ.get("CASMI_SEED", "2026")),
        max_scan_rows=int(os.environ.get("CASMI_MAX_SCAN_ROWS", "300000")),
        realistic_catalog_size=int(os.environ.get("CASMI_REALISTIC_CATALOG", "50000")),
        candidate_pool_size=int(os.environ.get("CASMI_POOL_SIZE", "100")),
        analog_top_k=int(os.environ.get("CASMI_ANALOG_TOP_K", "5")),
        bootstrap_samples=1,
        ranker_backend="hist_gbdt",
    ),
)
shutil.copy2(
    Path(inference["submission_path"]),
    Path("/kaggle/working/submission.csv"),
)
print(
    json.dumps(
        {
            "lightgbm_version": lightgbm.__version__,
            "experiment_selected": experiment["selected_by_model_selection"],
            "experiment_final": experiment["selected_final_evaluation"],
            "experiment_elapsed_seconds": experiment["elapsed_seconds"],
            "inference": inference,
        },
        indent=2,
        sort_keys=True,
    )
)
