"""Offline Code Competition inference for the C1 + frozen E6 recovery."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


EXPECTED_C1_COUNT = 271_439
EXPECTED_REFERENCE_COUNT = 127


def install_offline_assets() -> tuple[Path, Path]:
    wheels = sorted(Path("/kaggle/input").glob("**/*.whl"))
    python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    rdkit_wheels = [
        path for path in wheels if path.name.startswith("rdkit-") and python_tag in path.name
    ]
    project_wheels = [path for path in wheels if path.name.startswith("casmi26_baseline-")]
    if len(rdkit_wheels) != 1 or len(project_wheels) != 1:
        raise RuntimeError(
            f"Expected exactly one {python_tag} RDKit wheel and one project wheel; "
            f"found rdkit={rdkit_wheels}, project={project_wheels}"
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
    manifests = sorted(Path("/kaggle/input").glob("**/goal5_c1_index/manifest.json"))
    archives = sorted(Path("/kaggle/input").glob("**/goal5_c1_index.zip"))
    if not manifests and len(archives) == 1:
        extracted = Path("/kaggle/working/recovery_c1_index")
        with zipfile.ZipFile(archives[0]) as archive:
            if any(
                Path(name).is_absolute() or ".." in Path(name).parts
                for name in archive.namelist()
            ):
                raise RuntimeError("Unsafe path in C1 index archive")
            archive.extractall(extracted)
        manifests = sorted(extracted.glob("**/manifest.json"))
    if len(frozen) != 1 or len(manifests) != 1:
        raise RuntimeError(
            "Recovery assets are ambiguous or incomplete: "
            f"frozen={frozen}, c1_manifests={manifests}, c1_archives={archives}"
        )
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    if manifest.get("structure_count") != EXPECTED_C1_COUNT:
        raise RuntimeError(f"Unexpected C1 manifest: {manifest}")
    return frozen[0], manifests[0].parent


def find_competition_root() -> Path:
    roots = [
        path.parent
        for path in sorted(Path("/kaggle/input").glob("**/train.parquet"))
        if (path.parent / "test.parquet").is_file()
        and (path.parent / "sample_submission.csv").is_file()
    ]
    if len(roots) != 1:
        raise RuntimeError(f"Expected exactly one CASMI competition dataset; found {roots}")
    return roots[0]


frozen_identity_path, c1_index_path = install_offline_assets()

from casmi26.chemistry import rdkit_version
from casmi26.recovery_inference import RecoveryInferenceConfig, run_recovery_c1_inference


if rdkit_version() != "2026.03.3":
    raise RuntimeError(f"Unexpected RDKit version: {rdkit_version()}")

competition_root = find_competition_root()
report = run_recovery_c1_inference(
    competition_root / "train.parquet",
    competition_root / "test.parquet",
    competition_root / "sample_submission.csv",
    frozen_identity_path,
    c1_index_path,
    Path("/kaggle/working/recovery_inference"),
    config=RecoveryInferenceConfig(),
)
if report["inference"]["reference_spectra"] != EXPECTED_REFERENCE_COUNT:
    raise RuntimeError(
        "Frozen E6 reference library drifted: "
        f"expected={EXPECTED_REFERENCE_COUNT}, "
        f"actual={report['inference']['reference_spectra']}"
    )
shutil.copy2(report["submission_path"], "/kaggle/working/submission.csv")
kernel_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
summary = {
    "pipeline": "C1 full-train candidate index + frozen Goal 4 E6 ranking",
    "cause_fixed": report["cause_fixed"],
    "kernel_sha256": kernel_sha256,
    "report": report,
    "submission_path": "/kaggle/working/submission.csv",
    "official_submission_performed_by_kernel": False,
    "python": sys.version,
    "rdkit": rdkit_version(),
}
Path("/kaggle/working/recovery_kernel_summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, indent=2, sort_keys=True))
