"""Read-only preflight for a CASMI Goal 4 Kaggle bundle.

The validator never pushes a kernel and never submits to a competition.  It
checks metadata, offline assets, source code, optional catalog/checkpoint files
and an optional generated submission.  Run it before every Kaggle kernel push.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


COMPETITION = "enveda-CASMI26-molecule-id-mass-spectra"
FORBIDDEN_NETWORK_IMPORTS = {"requests", "httpx", "urllib", "socket"}
FORBIDDEN_SUBMISSION_TEXT = (
    "kaggle competitions submit",
    "competitions.submit(",
    "competition_submit(",
)


@dataclass(frozen=True, slots=True)
class BundleValidation:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    checks: dict[str, Any]
    file_sha256: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checks": self.checks,
            "file_sha256": self.file_sha256,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _network_imports(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots = {node.module.split(".", 1)[0]}
        else:
            continue
        found.update(roots & FORBIDDEN_NETWORK_IMPORTS)
    return found


def _asset_inventory(asset_dir: Path | None) -> tuple[list[Path], dict[str, Any]]:
    if asset_dir is None:
        return [], {"checked": False}
    if not asset_dir.is_dir():
        return [], {"checked": True, "exists": False, "file_count": 0}
    files = sorted(path for path in asset_dir.rglob("*") if path.is_file())
    return files, {
        "checked": True,
        "exists": True,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
    }


def validate_bundle(
    bundle_dir: str | Path,
    *,
    assets_dir: str | Path | None = None,
    submission_path: str | Path | None = None,
    expected_ids_path: str | Path | None = None,
    require_candidate_catalog: bool = False,
    require_checkpoint: bool = False,
) -> BundleValidation:
    """Validate a bundle without changing local or Kaggle state."""

    root = Path(bundle_dir)
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    metadata_path = root / "kernel-metadata.json"
    if not root.is_dir():
        return BundleValidation(
            False, (f"Bundle directory does not exist: {root}",), (), {}, {}
        )
    if not metadata_path.is_file():
        return BundleValidation(False, ("Missing kernel-metadata.json",), (), {}, {})
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return BundleValidation(False, (f"Invalid kernel metadata: {exc}",), (), {}, {})
    hashes["kernel-metadata.json"] = _sha256(metadata_path)

    required_metadata = {
        "id",
        "title",
        "code_file",
        "language",
        "kernel_type",
        "is_private",
        "enable_gpu",
        "enable_internet",
        "dataset_sources",
        "competition_sources",
    }
    missing = sorted(required_metadata - set(metadata))
    if missing:
        errors.append(f"Missing kernel metadata fields: {missing}")
    if metadata.get("enable_internet") is not False:
        errors.append("Kaggle kernel must set enable_internet=false")
    if metadata.get("is_private") is not True:
        errors.append("Pre-submission kernel must remain private")
    if COMPETITION not in metadata.get("competition_sources", []):
        errors.append(f"Missing competition source {COMPETITION!r}")
    if not metadata.get("dataset_sources"):
        errors.append("At least one offline asset dataset must be attached")
    if metadata.get("enable_gpu") is not True:
        warnings.append("GPU is disabled; verify the selected inference path is CPU-safe")
    if metadata.get("machine_shape") not in (None, "NvidiaTeslaT4"):
        warnings.append(
            f"Machine shape is {metadata.get('machine_shape')!r}, not NvidiaTeslaT4"
        )
    if metadata.get("machine_shape") is None:
        warnings.append("machine_shape is not pinned in metadata; verify the runtime reports T4")

    code_file = root / str(metadata.get("code_file", ""))
    if not code_file.is_file():
        errors.append(f"Missing code file: {code_file.name}")
    else:
        hashes[code_file.name] = _sha256(code_file)
        source = code_file.read_text(encoding="utf-8")
        try:
            compile(source, str(code_file), "exec")
        except SyntaxError as exc:
            errors.append(f"Code file does not compile: {exc}")
        imports = sorted(_network_imports(source))
        if imports:
            errors.append(f"Offline kernel imports network clients: {imports}")
        lowered = source.lower()
        forbidden = [text for text in FORBIDDEN_SUBMISSION_TEXT if text in lowered]
        if forbidden:
            errors.append("Kernel source contains an official submission call")
        checks["code"] = {
            "path": code_file.name,
            "bytes": code_file.stat().st_size,
            "network_imports": imports,
            "submission_call_detected": bool(forbidden),
        }

    asset_root = Path(assets_dir) if assets_dir is not None else None
    asset_files, asset_check = _asset_inventory(asset_root)
    checks["assets"] = asset_check
    if asset_root is None:
        warnings.append("Offline asset directory was not supplied; attachment contents are unverified")
    elif not asset_check.get("exists"):
        errors.append(f"Asset directory does not exist: {asset_root}")
    else:
        names = [path.name.lower() for path in asset_files]
        if not any(name.startswith("casmi26_baseline-") and name.endswith(".whl") for name in names):
            errors.append("Missing project wheel in offline assets")
        rdkit_wheels = [name for name in names if name.startswith("rdkit-") and name.endswith(".whl")]
        if not rdkit_wheels:
            errors.append("Missing RDKit wheel in offline assets")
        if rdkit_wheels and not any("2026.3.3" in name for name in rdkit_wheels):
            errors.append("Offline assets do not contain the required RDKit 2026.3.3 wheel")
        if require_candidate_catalog and not any(
            "catalog" in name and path.suffix.lower() in {".parquet", ".npz", ".npy", ".zip"}
            for name, path in zip(names, asset_files)
        ):
            errors.append("Required candidate catalog artifact is missing")
        if require_checkpoint and not any(
            path.suffix.lower() in {".pt", ".pth", ".safetensors", ".joblib"}
            for path in asset_files
        ):
            errors.append("Required checkpoint artifact is missing")
        for path in asset_files:
            relative = f"assets/{path.relative_to(asset_root).as_posix()}"
            hashes[relative] = _sha256(path)

    if submission_path is not None:
        submission = Path(submission_path)
        if not submission.is_file():
            errors.append(f"Submission does not exist: {submission}")
        else:
            try:
                import pandas as pd

                from casmi26.submission import validate_submission

                expected = None
                if expected_ids_path is not None:
                    expected_frame = pd.read_csv(expected_ids_path)
                    if "molecule_id" not in expected_frame:
                        raise ValueError("Expected-ID file lacks molecule_id")
                    expected = expected_frame["molecule_id"].astype(str).tolist()
                validation = validate_submission(
                    submission, expected_molecule_ids=expected
                )
                checks["submission"] = validation.to_dict()
                hashes["submission.csv"] = _sha256(submission)
                if not validation.valid:
                    errors.extend(
                        f"Submission: {message}" for message in validation.errors
                    )
            except Exception as exc:  # diagnostic boundary for optional validation
                errors.append(f"Submission validation failed: {exc}")
    else:
        warnings.append("No generated submission was supplied for row-level validation")

    checks["metadata"] = {
        "kernel_id": metadata.get("id"),
        "private": metadata.get("is_private"),
        "internet_disabled": metadata.get("enable_internet") is False,
        "gpu_enabled": metadata.get("enable_gpu") is True,
        "competition_attached": COMPETITION in metadata.get("competition_sources", []),
        "dataset_sources": metadata.get("dataset_sources", []),
    }
    return BundleValidation(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        checks=checks,
        file_sha256=dict(sorted(hashes.items())),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--expected-ids", type=Path)
    parser.add_argument("--require-candidate-catalog", action="store_true")
    parser.add_argument("--require-checkpoint", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = validate_bundle(
        args.bundle_dir,
        assets_dir=args.assets_dir,
        submission_path=args.submission,
        expected_ids_path=args.expected_ids,
        require_candidate_catalog=args.require_candidate_catalog,
        require_checkpoint=args.require_checkpoint,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
