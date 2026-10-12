"""Private offline Goal 5 experiment and E6 submission rehearsal; never submits."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def install_offline_assets() -> tuple[Path, Path, Path]:
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
    frozen = sorted(Path("/kaggle/input").glob("**/goal3_frozen_identities.txt"))
    prior = sorted(Path("/kaggle/input").glob("**/goal5_prior_final_identities.txt"))
    if len(frozen) != 1 or len(prior) != 1:
        raise RuntimeError(f"Expected frozen identity assets; found frozen={frozen}, prior={prior}")
    c1_manifests = sorted(Path("/kaggle/input").glob("**/goal5_c1_index/manifest.json"))
    c1_archives = sorted(Path("/kaggle/input").glob("**/goal5_c1_index.zip"))
    if not c1_manifests and len(c1_archives) == 1:
        extracted = Path("/kaggle/working/prebuilt_c1_index")
        with zipfile.ZipFile(c1_archives[0]) as archive:
            if any(
                Path(name).is_absolute() or ".." in Path(name).parts
                for name in archive.namelist()
            ):
                raise RuntimeError("Unsafe path in the prebuilt C1 index archive")
            archive.extractall(extracted)
        c1_manifests = sorted(extracted.glob("**/manifest.json"))
    if len(c1_manifests) != 1:
        raise RuntimeError(
            "Expected one prebuilt Goal 5 C1 index manifest; "
            f"found manifests={c1_manifests}, archives={c1_archives}"
        )
    return frozen[0], prior[0], c1_manifests[0].parent


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


frozen_identity_path, prior_final_path, prebuilt_c1_index_path = install_offline_assets()

from casmi26.chemistry import rdkit_version
from casmi26.goal4_inference import run_goal4_selected_inference
from casmi26.goal4_pipeline import Goal4ExperimentConfig
from casmi26.goal5_pipeline import Goal5ExperimentConfig
from casmi26.goal5_run import run_goal5_full


if rdkit_version() != "2026.03.3":
    raise RuntimeError(f"Unexpected RDKit version: {rdkit_version()}")

root = find_competition_root()
goal5_results = run_goal5_full(
    root / "train.parquet",
    root / "test.parquet",
    frozen_identity_path,
    prior_final_path,
    Path("/kaggle/working/goal5"),
    config=Goal5ExperimentConfig(
        background_reference_identities=int(
            os.environ.get("CASMI_BACKGROUND_IDENTITIES", "2000")
        ),
        reference_spectra_per_domain_identity=int(
            os.environ.get("CASMI_DOMAIN_REFERENCE_SPECTRA", "4")
        ),
        dynamic_pool_size=int(os.environ.get("CASMI_DYNAMIC_POOL_SIZE", "1000")),
        bootstrap_samples=int(os.environ.get("CASMI_BOOTSTRAP_SAMPLES", "500")),
    ),
    prebuilt_c1_index_path=prebuilt_c1_index_path,
)

# The official-submission candidate stays the frozen, already validated E6.
# Goal 5 challengers are not used on hidden test until their sealed evidence is
# reviewed.  This creates a ready CSV but never invokes the Kaggle submit API.
inference = run_goal4_selected_inference(
    root / "train.parquet",
    root / "test.parquet",
    root / "sample_submission.csv",
    frozen_identity_path,
    Path("/kaggle/working/goal5_inference"),
    selected_experiment="E6",
    selected_feature="analog_score",
    evidence_weight=0.5,
    gate_threshold=0.0,
    config=Goal4ExperimentConfig(
        seed=2026,
        max_scan_rows=300_000,
        realistic_catalog_size=50_000,
        candidate_pool_size=100,
        analog_top_k=5,
        bootstrap_samples=1,
        ranker_backend="hist_gbdt",
    ),
)
shutil.copy2(inference["submission_path"], "/kaggle/working/submission.csv")
summary = {
    "goal5_results": "/kaggle/working/goal5/goal5_results.json",
    "goal5_experiment_id": goal5_results["experiment_id"],
    "inference": inference,
    "submission_path": "/kaggle/working/submission.csv",
    "official_submission_performed": False,
    "python": sys.version,
    "rdkit": rdkit_version(),
}
Path("/kaggle/working/goal5_kernel_summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, indent=2, sort_keys=True))
