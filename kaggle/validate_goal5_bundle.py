"""Read-only preflight for the private Goal 5 Kaggle bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import py_compile
import zipfile


REQUIRED_WHEEL_MODULES = {
    "casmi26/domain_validation.py",
    "casmi26/goal5_pipeline.py",
    "casmi26/goal5_run.py",
    "casmi26/scalable_analog.py",
    "casmi26/scalable_retrieval.py",
}


def validate(bundle: Path, assets: Path) -> dict[str, object]:
    errors: list[str] = []
    metadata_path = bundle / "kernel-metadata.json"
    if not metadata_path.is_file():
        return {"passed": False, "errors": ["missing kernel-metadata.json"]}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("is_private") is not True:
        errors.append("kernel must remain private")
    if metadata.get("enable_internet") is not False:
        errors.append("kernel must run offline")
    if metadata.get("id") != "mperni/casmi26-goal5-scalable-retrieval":
        errors.append("unexpected kernel id")
    code_file = bundle / str(metadata.get("code_file", ""))
    for path in (code_file,):
        if not path.is_file():
            errors.append(f"missing bundle source: {path.name}")
            continue
        py_compile.compile(str(path), doraise=True)
        lowered = path.read_text(encoding="utf-8").lower()
        if "competitions submit" in lowered or ".submit(" in lowered:
            errors.append(f"submission API found in {path.name}")

    wheels = sorted(assets.glob("casmi26_baseline-*.whl"))
    if len(wheels) != 1:
        errors.append(f"expected one project wheel, found {len(wheels)}")
    else:
        with zipfile.ZipFile(wheels[0]) as archive:
            missing = REQUIRED_WHEEL_MODULES - set(archive.namelist())
        if missing:
            errors.append(f"project wheel missing modules: {sorted(missing)}")
    prior = assets / "goal5_prior_final_identities.txt"
    if not prior.is_file() or len(prior.read_text().splitlines()) != 16:
        errors.append("prior final identity asset must contain exactly 16 rows")
    rdkit = list(assets.glob("rdkit-2026.3.3-cp313-*.whl"))
    if len(rdkit) != 1:
        errors.append("expected one CPython 3.13 RDKit wheel")
    return {
        "passed": not errors,
        "errors": errors,
        "kernel_id": metadata.get("id"),
        "offline": metadata.get("enable_internet") is False,
        "private": metadata.get("is_private") is True,
        "gpu": metadata.get("enable_gpu"),
        "project_wheel": wheels[0].name if len(wheels) == 1 else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.bundle, args.assets)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
