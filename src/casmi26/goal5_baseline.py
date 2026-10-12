from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class FrozenE6Contract:
    git_commit: str = "04a6a89ae7fc6c32d4a65f6f63450864f5a00abc"
    manifest_hash: str = (
        "138055fca36fb37bd29bf27e970a6f8ee853bdd955546a17cb815cf49f1390d0"
    )
    source_catalog_size: int = 49_620
    canonical_catalog_size: int = 49_195
    selected_experiment: str = "E6"
    selected_feature: str = "analog_score"
    evidence_weight: float = 0.5


def sha256_file(path: str | Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    if chunk_bytes <= 0:
        raise ValueError("chunk_bytes must be positive")
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


def _metric_signature(results: Mapping[str, Any]) -> dict[str, Any]:
    signature: dict[str, Any] = {}
    evaluations = results["evaluations"]
    for split in ("all_validation", "model_selection", "final_evaluation"):
        split_values = evaluations[split]
        signature[split] = {
            experiment: {
                "mrr_at_25": values["metrics"]["mrr_at_25"],
                "hit_at_1": values["metrics"]["hit_at_1"],
                "hit_at_5": values["metrics"]["hit_at_5"],
                "hit_at_10": values["metrics"]["hit_at_10"],
                "candidate_recall_at": values["metrics"]["candidate_recall_at"],
            }
            for experiment, values in sorted(split_values.items())
        }
    return signature


def frozen_e6_signature(results: Mapping[str, Any]) -> dict[str, Any]:
    """Extract every selection-critical value from a Goal 4 result artifact."""

    e3 = results["model_selection"]["E3"]
    return {
        "manifest_hash": results["manifest_hash"],
        "canonical_catalog": results["canonical_catalog"],
        "selected_by_model_selection": results["selected_by_model_selection"],
        "selected_aggregation_feature": e3["selected_aggregation_feature"],
        "selected_weight": e3["selected_weight"],
        "metrics": _metric_signature(results),
    }


def assert_e6_replication(
    reference: Mapping[str, Any],
    replicate: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail if a purported E6 regression run changes the frozen contract."""

    left = frozen_e6_signature(reference)
    right = frozen_e6_signature(replicate)
    if left != right:
        changed = sorted(key for key in left if left[key] != right.get(key))
        raise AssertionError(f"Frozen E6 replication mismatch: {changed}")
    return {
        "replicated": True,
        "manifest_hash": left["manifest_hash"],
        "selected_experiment": left["selected_by_model_selection"],
        "selected_feature": left["selected_aggregation_feature"],
        "selected_weight": left["selected_weight"],
        "all_validation_e6_mrr_at_25": left["metrics"]["all_validation"]["E6"][
            "mrr_at_25"
        ],
    }


def verify_goal4_v3_v4_replication(repository_root: str | Path) -> dict[str, Any]:
    root = Path(repository_root)
    reference_path = root / "artifacts/goal4_kaggle_v3/goal4/goal4_results.json"
    replicate_path = root / "artifacts/goal4_kaggle_v4/goal4/goal4_results.json"
    if not reference_path.is_file() or not replicate_path.is_file():
        raise FileNotFoundError("Goal 4 v3/v4 result artifacts are required")
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    replicate = json.loads(replicate_path.read_text(encoding="utf-8"))
    report = assert_e6_replication(reference, replicate)
    report["reference_sha256"] = sha256_file(reference_path)
    report["replicate_sha256"] = sha256_file(replicate_path)
    return report
