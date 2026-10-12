"""Run bounded, read-only forensics for the first zero-score submission.

The script rebuilds the exact Goal 4 C0 catalog, reuses the persisted Goal 5
C1 index, and evaluates mass-only retrieval on the development part of the
domain-matched split.  It never submits, trains, or opens the sealed holdout.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from casmi26.chemistry import canonical_inchikey14, neutral_mass_from_mz, rdkit_version
from casmi26.goal4_inference import Goal4InferenceConfig, build_target_blind_catalog
from casmi26.mass_retrieval import MassCandidateIndex
from casmi26.recovery_audit import (
    audit_prediction_identities,
    summarize_candidate_tier,
    summarize_neutral_mass_residuals,
)
from casmi26.scalable_retrieval import ScalableMassFormulaIndex


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_selected_spectra(
    path: Path,
    wanted_spectrum_ids: set[str],
) -> tuple[dict[str, list[float]], dict[str, list[str]], set[str], Counter[str]]:
    parquet = pq.ParquetFile(path)
    columns = ["inchikey14", "precursor_mz", "adduct"]
    missing = sorted(set(columns) - set(parquet.schema_arrow.names))
    if missing:
        raise ValueError(f"Train Parquet missing columns: {missing}")
    # The competition train file has no physical spectrum_id column.  The
    # shared reader deterministically creates ``<inchikey14>_<1-based row>``;
    # reproduce that identifier without loading peak arrays.
    wanted_rows: dict[int, str] = {}
    for spectrum_id in wanted_spectrum_ids:
        _, separator, row_text = spectrum_id.rpartition("_")
        if not separator or not row_text.isdigit():
            raise ValueError(f"Unsupported generated spectrum id: {spectrum_id!r}")
        wanted_rows[int(row_text)] = spectrum_id
    masses: dict[str, list[float]] = defaultdict(list)
    adducts: dict[str, list[str]] = defaultdict(list)
    found: set[str] = set()
    unsupported: Counter[str] = Counter()
    row_offset = 0
    for batch in parquet.iter_batches(batch_size=131_072, columns=columns):
        batch_start = row_offset + 1
        batch_stop = row_offset + batch.num_rows
        selected_rows = sorted(
            row_number
            for row_number in wanted_rows
            if batch_start <= row_number <= batch_stop
        )
        for row_number in selected_rows:
            row = batch.slice(row_number - batch_start, 1).to_pylist()[0]
            spectrum_id = wanted_rows[row_number]
            identity = str(row["inchikey14"]).strip().upper()
            if spectrum_id != f"{identity}_{row_number}":
                raise RuntimeError(
                    "Generated spectrum-id mismatch: "
                    f"plan={spectrum_id!r}, parquet={identity}_{row_number}"
                )
            adduct = str(row["adduct"])
            found.add(spectrum_id)
            neutral_mass = neutral_mass_from_mz(float(row["precursor_mz"]), adduct)
            if neutral_mass is None:
                unsupported[adduct] += 1
                continue
            masses[identity].append(float(neutral_mass))
            adducts[identity].append(adduct)
        row_offset = batch_stop
    return dict(masses), dict(adducts), found, unsupported


def _extract_test_masses(path: Path) -> tuple[dict[str, float], Counter[str], int]:
    parquet = pq.ParquetFile(path)
    columns = ["molecule_id", "precursor_mz", "adduct"]
    missing = sorted(set(columns) - set(parquet.schema_arrow.names))
    if missing:
        raise ValueError(f"Test Parquet missing columns: {missing}")
    values: dict[str, list[float]] = defaultdict(list)
    unsupported: Counter[str] = Counter()
    row_count = 0
    for batch in parquet.iter_batches(batch_size=131_072, columns=columns):
        for row in batch.to_pylist():
            row_count += 1
            query_id = str(row["molecule_id"])
            adduct = str(row["adduct"])
            mass = neutral_mass_from_mz(float(row["precursor_mz"]), adduct)
            if mass is None:
                unsupported[adduct] += 1
            else:
                values[query_id].append(float(mass))
    return (
        {query_id: float(np.median(masses)) for query_id, masses in values.items()},
        unsupported,
        row_count,
    )


def _prediction_identities(path: Path) -> dict[str, list[str]]:
    frame = pd.read_csv(path, dtype={"molecule_id": str, "smiles": str})
    predictions: dict[str, list[str]] = {}
    for row in frame.itertuples(index=False):
        identities = [canonical_inchikey14(value) for value in str(row.smiles).split(";")]
        if any(value is None for value in identities):
            raise ValueError(f"Invalid SMILES in prediction row {row.molecule_id}")
        predictions[str(row.molecule_id)] = [str(value) for value in identities]
    return predictions


def _condition_c_zero(query_count: int) -> dict[str, Any]:
    return {
        "query_count": query_count,
        "catalog_present_count": 0,
        "catalog_recall": 0.0,
        "candidate_recall_at_25": 0.0,
        "candidate_recall_at_100": 0.0,
        "candidate_recall_at_1000": 0.0,
        "mrr_at_25": 0.0,
        "conditional_mrr_at_25": 0.0,
        "hit_at_1": 0.0,
        "hit_at_5": 0.0,
        "hit_at_10": 0.0,
        "protocol_note": "truth identities are physically removed by Condition C",
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/train.parquet"))
    parser.add_argument("--test", type=Path, default=Path("data/test.parquet"))
    parser.add_argument(
        "--sample-submission", type=Path, default=Path("data/sample_submission.csv")
    )
    parser.add_argument(
        "--submission",
        type=Path,
        default=Path("artifacts/goal4_kaggle_v4/submission.csv"),
    )
    parser.add_argument(
        "--inference-report",
        type=Path,
        default=Path(
            "artifacts/goal4_kaggle_v4/goal4_inference/goal4_selected_inference_report.json"
        ),
    )
    parser.add_argument(
        "--domain-plan",
        type=Path,
        default=Path("artifacts/goal5_kaggle_v3/goal5/domain_plan_internal.json"),
    )
    parser.add_argument(
        "--c1-index",
        type=Path,
        default=Path("artifacts/goal5_kaggle_v2/goal5/c1_mass_formula_index"),
    )
    parser.add_argument("--runner", type=Path, default=Path("kaggle/run_goal4.py"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/zero_score_recovery/forensics.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    started = time.perf_counter()
    plan = json.loads(args.domain_plan.read_text(encoding="utf-8"))
    development_ids = tuple(map(str, plan["development_identity_keys"]))
    development = next(
        manifest
        for manifest in plan["manifests"]
        if manifest["stage"] == "development"
        and manifest["condition"] == "A_library_visible"
    )
    query_spectrum_ids = set(map(str, development["query_spectrum_ids"]))

    c0_started = time.perf_counter()
    c0, c0_report = build_target_blind_catalog(
        args.train,
        Goal4InferenceConfig(seed=2026, max_scan_rows=300_000, catalog_size=50_000),
    )
    c0_seconds = time.perf_counter() - c0_started
    c0_index = MassCandidateIndex(c0)
    c0_ids = {item.candidate_id for item in c0}
    c0_formula = {item.candidate_id: item.formula for item in c0}
    c0_mass = {item.candidate_id: float(item.exact_mass) for item in c0}

    c1_started = time.perf_counter()
    c1_index = ScalableMassFormulaIndex.load(args.c1_index, mmap=True, verify_hashes=True)
    c1_ids = [c1_index.candidate_id_at(position) for position in range(len(c1_index))]
    c1_positions = {candidate_id: position for position, candidate_id in enumerate(c1_ids)}
    c1_id_set = set(c1_ids)
    c1_formula = {
        candidate_id: c1_index.formula_at(position) or None
        for candidate_id, position in c1_positions.items()
    }
    c1_mass = {
        candidate_id: float(c1_index.masses[position])
        for candidate_id, position in c1_positions.items()
    }
    c1_seconds = time.perf_counter() - c1_started

    mass_started = time.perf_counter()
    neutral_masses, adducts, found_spectra, unsupported_domain = _extract_selected_spectra(
        args.train, query_spectrum_ids
    )
    missing_spectra = sorted(query_spectrum_ids - found_spectra)
    query_mass = {
        identity: float(np.median(neutral_masses.get(identity, ())))
        for identity in development_ids
        if neutral_masses.get(identity)
    }
    missing_query_mass = sorted(set(development_ids) - set(query_mass))
    if missing_spectra or missing_query_mass or unsupported_domain:
        raise RuntimeError(
            "Domain query extraction incomplete: "
            f"missing_spectra={len(missing_spectra)}, "
            f"missing_query_mass={len(missing_query_mass)}, "
            f"unsupported_adduct_rows={sum(unsupported_domain.values())}"
        )
    mass_extract_seconds = time.perf_counter() - mass_started

    truth = {identity: identity for identity in development_ids}
    c0_rankings = {
        identity: [hit.candidate_id for hit in c0_index.retrieve(mass, top_k=1_000)]
        for identity, mass in query_mass.items()
    }
    c1_rankings = {
        identity: [hit.candidate_id for hit in c1_index.retrieve(mass, top_k=1_000)]
        for identity, mass in query_mass.items()
    }
    c0_metrics = summarize_candidate_tier(
        truth,
        c0_rankings,
        catalog_identities=c0_ids,
        formula_by_candidate=c0_formula,
    )
    c1_metrics = summarize_candidate_tier(
        truth,
        c1_rankings,
        catalog_identities=c1_id_set,
        formula_by_candidate=c1_formula,
    )
    truth_mass = {identity: c1_mass[identity] for identity in development_ids}
    mass_residuals = summarize_neutral_mass_residuals(
        neutral_masses, truth_mass, adducts
    )

    newly_covered = sorted(set(development_ids) & (c1_id_set - c0_ids))
    newly_covered_sources: Counter[str] = Counter()
    for identity in newly_covered:
        newly_covered_sources.update(c1_index.sources_at(c1_positions[identity]))

    expected_ids = (
        pd.read_csv(args.sample_submission, usecols=["molecule_id"])["molecule_id"]
        .astype(str)
        .tolist()
    )
    placeholder_masses, unsupported_test, test_spectrum_count = _extract_test_masses(
        args.test
    )
    predictions = _prediction_identities(args.submission)
    prediction_audit = audit_prediction_identities(
        expected_ids,
        predictions,
        catalog_identities=c0_ids,
        query_mass_by_id=placeholder_masses,
        candidate_mass_by_id=c0_mass,
    )

    runner_text = args.runner.read_text(encoding="utf-8")
    placeholder_ids_in_runner = [query_id for query_id in expected_ids if query_id in runner_text]
    inference_report = json.loads(args.inference_report.read_text(encoding="utf-8"))
    goal5_reference_ladder = []
    for manifest in plan["manifests"]:
        goal5_reference_ladder.append(
            {
                "stage": manifest["stage"],
                "condition": manifest["condition"],
                "reference_spectrum_count": len(manifest["reference_spectrum_ids"]),
                "reference_identity_visibility": manifest["same_identity_reference_allowed"],
            }
        )

    report: dict[str, Any] = {
        "experiment_id": "zero_score_forensics_v1",
        "submission_ref": 57109254,
        "submission_public_score_displayed": "0.000",
        "sealed_holdout_opened": False,
        "training_performed": False,
        "kaggle_run_started": False,
        "rdkit_version": rdkit_version(),
        "code_path": {
            "runner": str(args.runner),
            "runner_sha256": _sha256_file(args.runner),
            "dynamic_competition_root_resolution": all(
                marker in runner_text
                for marker in ("**/train.parquet", "test.parquet", "sample_submission.csv")
            ),
            "placeholder_query_ids_hardcoded_count": len(placeholder_ids_in_runner),
            "selection_fallback_present": 'selected_experiment = "E3"' in runner_text,
            "actual_selected_experiment": inference_report["selected_experiment"],
            "actual_selected_feature": inference_report["selected_feature"],
            "actual_evidence_weight": inference_report["evidence_weight"],
        },
        "placeholder_output": {
            **prediction_audit,
            "submission_sha256": _sha256_file(args.submission),
            "test_spectrum_count": test_spectrum_count,
            "test_molecule_count": len(placeholder_masses),
            "unsupported_adduct_rows": dict(unsupported_test),
        },
        "catalogs": {
            "C0": {
                **c0_report,
                "source_counts": dict(sorted(Counter(item.source for item in c0).items())),
                "build_seconds": c0_seconds,
            },
            "C1": {
                "structure_count": len(c1_index),
                "tier_name": c1_index.tier_name,
                "sources": list(c1_index.sources),
                "load_and_materialize_seconds": c1_seconds,
            },
            "overlap": {
                "C0_in_C1_count": len(c0_ids & c1_id_set),
                "C0_not_in_C1_count": len(c0_ids - c1_id_set),
                "C1_only_count": len(c1_id_set - c0_ids),
            },
        },
        "domain_matched_development": {
            "query_identity_count": len(development_ids),
            "query_spectrum_count": len(query_spectrum_ids),
            "query_source": plan["query_source"],
            "required_instrument": plan["required_instrument"],
            "mass_extraction_seconds": mass_extract_seconds,
            "unsupported_adduct_rows": dict(unsupported_domain),
            "neutral_mass_residuals": mass_residuals,
            "newly_covered_by_C1_count": len(newly_covered),
            "newly_covered_by_C1_fraction": len(newly_covered) / len(development_ids),
            "newly_covered_C1_sources": dict(sorted(newly_covered_sources.items())),
            "conditions": {
                "A_library_visible": {
                    "C0_mass_only": c0_metrics,
                    "C1_mass_only": c1_metrics,
                    "note": "mass-only audit; spectral reference visibility is not consumed",
                },
                "B_structure_known_spectra_hidden": {
                    "C0_mass_only": c0_metrics,
                    "C1_mass_only": c1_metrics,
                    "note": "identical to A for a mass-only candidate generator",
                },
                "C_structure_absent": {
                    "C0_mass_only": _condition_c_zero(len(development_ids)),
                    "C1_mass_only": _condition_c_zero(len(development_ids)),
                },
            },
        },
        "spectral_reference_scaling": {
            "E6_v4_reference_spectra": inference_report["reference_count"],
            "E6_v4_reference_spectra_before_query_content_filter": inference_report[
                "reference_count_before_query_content_filter"
            ],
            "E6_reference_policy": inference_report["reference_policy"],
            "goal5_v3_reference_ladder": goal5_reference_ladder,
            "effect_metrics_available": False,
            "reason": (
                "Goal5 v4 was still RUNNING when this bounded audit executed; "
                "no new multi-hour benchmark was launched"
            ),
        },
        "unmeasured_catalog_tiers": {
            "C2": "not built: COCONUT structures are not present locally",
            "C3": "not built: ChEBI/LIPID MAPS structures are not present locally",
            "PubChem": "not built: no general predeclared subset artifact exists",
        },
        "limitations": [
            "Kaggle does not expose the hidden rerun output or runtime through the CLI/API.",
            "Placeholder-output integrity cannot prove hidden candidate coverage.",
            "C0/C1 MRR values here are nearest-mass E0 values, not an E6 spectral rerun.",
            "The sealed Goal5 holdout was not opened.",
            "External tiers C2/C3/PubChem were not downloaded or indexed locally.",
        ],
        "elapsed_seconds": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
