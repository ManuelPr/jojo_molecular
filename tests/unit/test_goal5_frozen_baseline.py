from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FROZEN_CONFIG = ROOT / "configs" / "goal5_e6_frozen.yaml"


def test_goal5_frozen_baseline_records_immutable_goal4_contract() -> None:
    text = FROZEN_CONFIG.read_text(encoding="utf-8")
    required = (
        "git_commit: 04a6a89ae7fc6c32d4a65f6f63450864f5a00abc",
        "selected_experiment: E6",
        "selected_feature: analog_score",
        "evidence_weight: 0.5",
        "candidate_recall_at_100: 1.0",
        "submission_performed: false",
    )
    for value in required:
        assert value in text


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    (
        (
            "artifacts/goal4_kaggle_v4/goal4/goal4_results.json",
            "9605d8d98ddd0e1a20fe33b1a52c562fc39aa95b0f199ca1b876198fbb04374a",
        ),
        (
            "artifacts/goal4_kaggle_v4/submission.csv",
            "52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f",
        ),
    ),
)
def test_goal4_artifact_hashes_remain_frozen(
    relative_path: str, expected: str
) -> None:
    path = ROOT / relative_path
    if not path.is_file():
        pytest.skip("Large ignored Goal 4 artifact is not present in this checkout")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
