from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .chemistry import canonical_inchikey14, canonical_smiles


@dataclass(frozen=True, slots=True)
class SubmissionValidation:
    valid: bool
    row_count: int
    molecule_count: int
    min_candidates: int
    max_candidates: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "row_count": self.row_count,
            "molecule_count": self.molecule_count,
            "min_candidates": self.min_candidates,
            "max_candidates": self.max_candidates,
            "errors": list(self.errors),
        }


def clean_candidates(smiles_values: Sequence[str], *, limit: int = 25) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for smiles in smiles_values:
        key = canonical_inchikey14(smiles)
        normalized = canonical_smiles(smiles)
        if key is None or normalized is None or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
        if len(output) == limit:
            break
    return output


def write_submission(
    predictions: Mapping[str, Sequence[str]],
    expected_molecule_ids: Sequence[str],
    path: str | Path,
) -> SubmissionValidation:
    expected = list(dict.fromkeys(str(mid) for mid in expected_molecule_ids))
    missing = [mid for mid in expected if mid not in predictions]
    if missing:
        raise ValueError(f"Missing predictions for {len(missing)} molecule(s)")
    rows: list[dict[str, str]] = []
    for molecule_id in expected:
        cleaned = clean_candidates(predictions[molecule_id])
        if not cleaned:
            raise ValueError(f"No valid candidates for {molecule_id}")
        rows.append({"molecule_id": molecule_id, "smiles": ";".join(cleaned)})
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["molecule_id", "smiles"]).to_csv(destination, index=False)
    validation = validate_submission(destination, expected_molecule_ids=expected)
    if not validation.valid:
        raise ValueError(f"Generated invalid submission: {validation.errors}")
    return validation


def validate_submission(
    path: str | Path,
    *,
    expected_molecule_ids: Sequence[str] | None = None,
) -> SubmissionValidation:
    errors: list[str] = []
    frame = pd.read_csv(path)
    if list(frame.columns) != ["molecule_id", "smiles"]:
        errors.append("Columns must be exactly molecule_id,smiles")
    if frame.empty:
        errors.append("Submission is empty")
    if frame.isna().any().any():
        errors.append("Submission contains null values")
    if "molecule_id" in frame and frame["molecule_id"].duplicated().any():
        errors.append("Duplicate molecule_id values")

    counts: list[int] = []
    if "smiles" in frame:
        for row_number, value in enumerate(frame["smiles"].astype(str), start=2):
            candidates = value.split(";") if value else []
            counts.append(len(candidates))
            if not 1 <= len(candidates) <= 25:
                errors.append(f"Row {row_number} has {len(candidates)} candidates")
            keys = [canonical_inchikey14(smiles) for smiles in candidates]
            if any(key is None for key in keys):
                errors.append(f"Row {row_number} contains invalid SMILES")
            valid_keys = [key for key in keys if key is not None]
            if len(valid_keys) != len(set(valid_keys)):
                errors.append(f"Row {row_number} contains duplicate canonical structures")

    if expected_molecule_ids is not None and "molecule_id" in frame:
        expected = set(str(mid) for mid in expected_molecule_ids)
        actual = set(frame["molecule_id"].astype(str))
        if expected != actual:
            errors.append(
                f"Molecule ID mismatch: missing={len(expected - actual)}, extra={len(actual - expected)}"
            )

    return SubmissionValidation(
        valid=not errors,
        row_count=len(frame),
        molecule_count=int(frame["molecule_id"].nunique()) if "molecule_id" in frame else 0,
        min_candidates=min(counts) if counts else 0,
        max_candidates=max(counts) if counts else 0,
        errors=tuple(errors),
    )

