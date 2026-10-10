"""Kaggle entrypoint for the bounded baseline mini-training.

The notebook or script must attach the competition dataset and this source
bundle. It performs no network access and never submits automatically.
"""

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
        inputs = sorted(str(path) for path in Path("/kaggle/input").iterdir())
        raise RuntimeError(
            f"Expected one {python_tag} RDKit wheel and one project wheel; "
            f"wheels={wheels}, input_roots={inputs}"
        )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", "--force-reinstall", str(rdkit_wheels[0])],
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", "--force-reinstall", str(package_wheels[0])],
        check=True,
    )


install_offline_assets()

from casmi26.chemistry import rdkit_version
from casmi26.pipeline import MiniTrainConfig, run_mini_training


def find_competition_root() -> Path:
    configured = os.environ.get("CASMI_INPUT_ROOT")
    if configured:
        root = Path(configured)
        if not root.is_dir():
            raise RuntimeError(f"CASMI_INPUT_ROOT does not exist: {root}")
        return root
    train_files = sorted(Path("/kaggle/input").glob("**/train.parquet"))
    roots = [path.parent for path in train_files if (path.parent / "test.parquet").is_file()]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one attached CASMI competition dataset, found: {roots}")
    return roots[0]


INPUT_ROOT = find_competition_root()
OUTPUT_ROOT = Path(os.environ.get("CASMI_OUTPUT_ROOT", "/kaggle/working/mini_baseline"))

if rdkit_version() != "2026.03.3":
    raise RuntimeError(f"Unexpected RDKit version: {rdkit_version()}")

metrics = run_mini_training(
    INPUT_ROOT / "train.parquet",
    INPUT_ROOT / "test.parquet",
    OUTPUT_ROOT,
    config=MiniTrainConfig(
        max_molecules=int(os.environ.get("CASMI_MAX_MOLECULES", "128")),
        max_scan_rows=int(os.environ.get("CASMI_MAX_SCAN_ROWS", "300000")),
        top_k=int(os.environ.get("CASMI_TOP_K", "25")),
    ),
    submission_path=Path("/kaggle/working/submission.csv"),
)
print(metrics)
