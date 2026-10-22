"""Verify terminal control outputs and summarize the diagnostic submission gate."""
import argparse
import csv
from hashlib import sha256
import json
import math
from pathlib import Path

from casmi26.chemistry import canonical_inchikey14


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["molecule_id", "smiles"]:
            raise ValueError(f"Invalid columns in {path}")
        return list(reader)


def audit(root: Path, output: Path) -> dict:
    load = lambda name: json.loads((output / name).read_text(encoding="utf-8"))
    complete = load("public_control_complete.json")
    inference = load("public_inference_report.json")
    validation = load("public_validation_report.json")
    manifest = load("public_baseline_manifest.json")
    pinned = json.loads((root / "configs/public_baseline_manifest.json").read_text())
    if manifest != pinned or complete.get("complete") is not True:
        raise ValueError("Incomplete or unpinned control")
    rows = read_csv(output / "submission.csv")
    raw = read_csv(output / "public_raw_predictions.csv")
    raw_by_id = {r["molecule_id"]: r["smiles"] for r in raw}
    with (root / "data/sample_submission.csv").open(newline="", encoding="utf-8") as stream:
        expected = [r["molecule_id"] for r in csv.DictReader(stream)]
    if [r["molecule_id"] for r in rows] != expected or len(set(expected)) != len(expected):
        raise ValueError("Rehearsal sample ID order mismatch")
    if len(raw_by_id) != len(raw) or set(raw_by_id) != set(expected):
        raise ValueError("Raw predictions have incorrect IDs")
    counts, deduplicated_rows = [], 0
    for row in rows:
        guesses = row["smiles"].split(";")
        keys = [canonical_inchikey14(smi) for smi in guesses]
        if not 1 <= len(keys) <= 25 or None in keys or len(set(keys)) != len(keys):
            raise ValueError(f"Invalid scorer identities for {row['molecule_id']}")
        seen, first = set(), []
        for smi in raw_by_id[row["molecule_id"]].split(";"):
            key = canonical_inchikey14(smi)
            if key is None:
                raise ValueError("Invalid raw candidate")
            if key not in seen:
                first.append(smi)
                seen.add(key)
        if guesses != first:
            raise ValueError("Writer changed upstream candidate ordering")
        counts.append(len(keys))
        deduplicated_rows += row["smiles"] != raw_by_id[row["molecule_id"]]
    digest = sha256((output / "submission.csv").read_bytes()).hexdigest()
    if digest != complete["submission_sha256"] or digest != inference["submission_sha256"]:
        raise ValueError("Submission checksum mismatch")
    if inference["reference_spectra"] != 2_539_608 or inference["fingerprint_models"] != 2 or inference["ranker_count"] != 8:
        raise ValueError("Incomplete public evidence channels")
    if not math.isfinite(complete["elapsed_seconds"]) or complete["elapsed_seconds"] >= 10800:
        raise ValueError("Control runtime exceeded its budget")
    plan = json.loads((root / "configs/public_baseline_development.json").read_text())
    per_query = validation["per_query"]
    if len(per_query) != 188 or {r["identity"] for r in per_query} != set(plan["identity_keys"]):
        raise ValueError("Incorrect development cohort")
    reciprocal = []
    for item in per_query:
        rank = item["rank"]
        if rank is not None and (not isinstance(rank, int) or not 1 <= rank <= 25):
            raise ValueError("Invalid measured rank")
        value = 0.0 if rank is None else 1.0 / rank
        if not math.isclose(value, item["reciprocal_rank"], abs_tol=1e-12):
            raise ValueError("Invalid reciprocal rank")
        reciprocal.append(value)
    mrr = sum(reciprocal) / len(reciprocal)
    if not math.isfinite(mrr) or not math.isclose(mrr, validation["mrr_at_25"], abs_tol=1e-12):
        raise ValueError("Invalid validation MRR")
    for name, measured in {
        "hit_at_1": sum(r["rank"] == 1 for r in per_query) / len(per_query),
        "recall_at_25": sum(r["rank"] is not None for r in per_query) / len(per_query),
        "truth_in_mass_window": sum(bool(r["truth_in_window"]) for r in per_query) / len(per_query),
    }.items():
        if not math.isclose(measured, validation[name], abs_tol=1e-12):
            raise ValueError(f"Invalid validation {name}")
    fallback_rows = inference["raw_fallback_rows"]
    if not isinstance(fallback_rows, int) or not 0 <= fallback_rows <= len(rows):
        raise ValueError("Invalid fallback count")
    result = {"technical_gate_passed": True, "submission_sha256": digest, "rehearsal_queries": len(rows), "min_candidates": min(counts), "max_candidates": max(counts), "deduplicated_rows": deduplicated_rows,
              "candidate_pool_count": inference["candidate_pool_count"], "reference_spectra": inference["reference_spectra"], "analog_representatives": inference["analog_representatives"], "raw_fallback_rows": inference["raw_fallback_rows"], "total_runtime_seconds": complete["elapsed_seconds"], "development_mrr_at_25": mrr, "development_hit_at_1": validation["hit_at_1"], "development_recall_at_25": validation["recall_at_25"], "truth_in_mass_window": validation["truth_in_mass_window"], "limitations": validation["limitations"], "submission_performed_by_audit": False}
    (output / "public_submission_gate.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(Path(__file__).resolve().parents[1], args.output), indent=2))
