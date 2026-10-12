from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .benchmark_audit import construct_candidate_catalog
from .candidate_catalogs import CatalogRecord
from .chemistry import canonical_inchikey14
from .chemistry import rdkit_version
from .data import read_processed
from .domain_validation import (
    audit_domain_validation_plan,
    compare_domain_diagnostics,
    make_domain_validation_plan,
)
from .goal3_pipeline import Goal3ExperimentConfig, collect_goal3_dataset
from .goal5_baseline import FrozenE6Contract, verify_goal4_v3_v4_replication
from .goal5_pipeline import (
    Goal5ExperimentConfig,
    collect_domain_spectra,
    evaluate_goal5_stage,
    read_identity_file,
    write_goal5_results,
)
from .scalable_retrieval import (
    ScalableMassFormulaIndex,
    build_streaming_structure_catalog,
    iter_parquet_structure_rows,
)


def build_goal4_c0(
    train_path: str | Path,
    frozen_identity_path: str | Path,
    config: Goal5ExperimentConfig,
) -> tuple[tuple[CatalogRecord, ...], dict[str, object]]:
    dataset = collect_goal3_dataset(
        train_path,
        frozen_identity_path,
        Goal3ExperimentConfig(
            seed=2026,
            max_scan_rows=300_000,
            spectra_per_identity=3,
            validation_fraction=0.25,
            realistic_catalog_size=50_000,
            candidate_pool_size=100,
            max_peaks=config.max_peaks,
            intensity_floor=config.intensity_floor,
            peak_tolerance_da=config.peak_tolerance_da,
            bootstrap_samples=1,
            fingerprint_bits=config.fingerprint_bits,
        ),
    )
    trace = construct_candidate_catalog(
        dataset.source_candidate_ids,
        mode="realistic",
        max_size=50_000,
        controlled_target_ids=(),
    )
    source = {item.candidate_id: item for item in dataset.source_catalog}
    selected = [source[candidate_id] for candidate_id in trace.candidate_ids]
    valid = [
        item for item in selected if canonical_inchikey14(item.smiles) == item.candidate_id
    ]
    records = tuple(
        CatalogRecord(
            candidate_id=item.candidate_id,
            inchikey14=item.candidate_id,
            smiles=item.smiles,
            exact_mass=item.exact_mass,
            formula=item.formula,
            sources=(item.source or "train_structure_catalog",),
        )
        for item in valid
    )
    return records, {
        "tier": "C0",
        "source_catalog_size": len(dataset.source_catalog),
        "selected_before_canonical_filter": len(selected),
        "structure_count": len(records),
        "canonical_rejection_count": len(selected) - len(records),
        "construction": "frozen_Goal4_target_blind_seeded_catalog_rule",
    }


def run_goal5_full(
    train_path: str | Path,
    test_path: str | Path,
    frozen_identity_path: str | Path,
    prior_final_identity_path: str | Path,
    output_dir: str | Path,
    *,
    config: Goal5ExperimentConfig = Goal5ExperimentConfig(),
    repository_root: str | Path | None = None,
    prebuilt_c1_index_path: str | Path | None = None,
) -> dict[str, Any]:
    train_path = Path(train_path)
    test_path = Path(test_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    c0, c0_report = build_goal4_c0(train_path, frozen_identity_path, config)
    if prebuilt_c1_index_path is None:
        c1, streaming_report = build_streaming_structure_catalog(
            iter_parquet_structure_rows(train_path),
            default_source="kaggle_train",
        )
        c1_report: dict[str, Any] = {
            **streaming_report.to_dict(),
            "construction": "streaming_full_train_canonicalization",
        }
        c1_index = ScalableMassFormulaIndex.build(c1, tier_name="C1_train_unique")
    else:
        prebuilt_path = Path(prebuilt_c1_index_path)
        source_manifest = json.loads(
            (prebuilt_path / "manifest.json").read_text(encoding="utf-8")
        )
        if source_manifest.get("rdkit_version") != rdkit_version():
            raise RuntimeError(
                "Prebuilt C1 RDKit version differs from the inference environment"
            )
        c1_index = ScalableMassFormulaIndex.load(
            prebuilt_path, mmap=True, verify_hashes=True
        )
        c1 = c1_index.to_catalog_records()
        c1_report = {
            "unique_structure_count": len(c1),
            "construction": "verified_prebuilt_index_from_cancelled_goal5_v2",
            "source_index_manifest": source_manifest,
            "chemistry_recomputation_performed": False,
        }
    c1_manifest = c1_index.save(output / "c1_mass_formula_index")
    prior_final = read_identity_file(prior_final_identity_path)
    spectra, collection_report = collect_domain_spectra(
        train_path,
        catalog_identity_keys=[item.inchikey14 for item in c1],
        prior_final_identity_keys=prior_final,
        config=config,
    )
    plan = make_domain_validation_plan(
        spectra,
        candidate_identity_keys=[item.inchikey14 for item in c1],
        prior_final_identity_keys=prior_final,
        query_source=config.query_source,
        required_instrument=config.required_instrument,
        sealed_fraction=0.2,
        seed=config.seed,
    )
    audit = audit_domain_validation_plan(plan, spectra, raise_on_error=True)
    (output / "domain_plan_internal.json").write_text(
        json.dumps(plan.to_dict(include_sealed_membership=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (output / "domain_plan_redacted.json").write_text(
        json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    domain_records = [
        item
        for item in spectra
        if "".join(
            character
            for character in str(item.ingest_lib or "").lower()
            if character.isalnum()
        )
        == "envedanpexamples"
    ]
    domain_spectrum_ids = {item.spectrum_id for item in domain_records}
    train_reference_records = [
        item for item in spectra if item.spectrum_id not in domain_spectrum_ids
    ]
    test_records = list(read_processed(test_path))
    domain_diagnostics = compare_domain_diagnostics(
        train=train_reference_records,
        test=test_records,
        domain=domain_records,
    )

    tiers = {"C0": c0, "C1": c1}
    development = evaluate_goal5_stage(
        plan, spectra, tiers, stage="development", config=config
    )
    sealed = evaluate_goal5_stage(
        plan, spectra, tiers, stage="sealed", config=config
    )
    try:
        frozen_e6 = verify_goal4_v3_v4_replication(
            Path(repository_root) if repository_root is not None else Path.cwd()
        )
        frozen_e6["verification_scope"] = "local_v3_v4_artifact_exact_signature"
    except FileNotFoundError:
        frozen_e6 = {
            **asdict(FrozenE6Contract()),
            "replicated": None,
            "verification_scope": "frozen_contract_only_artifacts_not_bundled",
        }
    return write_goal5_results(
        output,
        config=config,
        plan=plan,
        collection_report=collection_report,
        catalog_reports={
            "C0": c0_report,
            "C1": {
                **c1_report,
                "index_manifest": c1_manifest.to_dict(),
            },
        },
        domain_audit=audit.to_dict(),
        domain_diagnostics=domain_diagnostics,
        frozen_e6=frozen_e6,
        development=development,
        sealed=sealed,
    )
