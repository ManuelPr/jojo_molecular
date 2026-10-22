"""Audit saved rehearsal outputs and reproduce frozen E6 ranking limitations.

No hidden labels, training, network calls, or submission. Synthetic examples
demonstrate algorithmic constraints, not their frequency in the hidden test.
"""
from collections import Counter
import csv
import json
from pathlib import Path

import numpy as np

from casmi26.goal4_ranking import linear_evidence_ranking, same_anchor_formula_reranking
from casmi26.schemas import CandidateHit


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = root / "artifacts/recovery_kaggle_v2/recovery_inference/recovery_inference_report.json"
    report = json.loads(report_path.read_text())
    queries = list(report["inference"]["per_query"].values())

    def rows(path: Path) -> dict[str, list[str]]:
        with path.open(newline="", encoding="utf-8") as stream:
            return {row["molecule_id"]: row["smiles"].split(";") for row in csv.DictReader(stream)}

    first = rows(root / "artifacts/goal4_kaggle_v4/submission.csv")
    second = rows(root / "artifacts/recovery_kaggle_v2/submission.csv")
    if first.keys() != second.keys():
        raise ValueError("Rehearsal molecule IDs differ")
    # Deliberately string-level comparison: no identity or accuracy claim.
    mass = [f"c{i:03}" for i in range(100)]
    truth = mass[29]
    evidence = [truth] + [key for key in mass if key != truth]
    formulas = {key: "C20H20O4" for key in mass}
    formulas[truth] = "C19H16O5"
    constrained = same_anchor_formula_reranking(mass, evidence, formulas)
    hits = [CandidateHit(key, "C", "synthetic", i + 1, 0.0,
                         {"mass_error_ppm": 1.0, "analog_score": float(i == 99)})
            for i, key in enumerate(mass)]
    fused = linear_evidence_ranking(hits, evidence_feature="analog_score", evidence_weight=0.5)
    result = {
        "scope": "Saved placeholder rehearsals and synthetic constraints; no hidden accuracy measured",
        "recovery_reference_spectra": report["inference"]["reference_spectra"],
        "recovery_returned_analog_counts": dict(Counter(q["analog"]["returned_analogs"] for q in queries)),
        "recovery_pool_worst_ppm": {name: float(np.percentile([q["worst_pool_mass_error_ppm"] for q in queries], p))
                                    for name, p in [("median", 50), ("p90", 90), ("max", 100)]},
        "rehearsal_changed_smiles_rows": sum(first[key] != second[key] for key in first),
        "rehearsal_changed_rank1_smiles": sum(first[key][0] != second[key][0] for key in first),
        "synthetic_wrong_anchor_formula": {"mass_rank": 30, "evidence_rank": 1,
                                            "final_rank": constrained.index(truth) + 1},
        "synthetic_equal_mass_isomers": {"mass_rank": 100, "evidence_rank": 1,
                                          "final_rank": fused.index(mass[-1]) + 1,
                                          "note": "Mass ties broken by candidate ID; other evidence scores tied at zero"},
    }
    destination = root / "artifacts/zero_score_recovery/ranking_limits.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
