from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from casmi26.domain_validation import (
    DomainValidationError,
    SealedHoldoutAccessError,
    audit_domain_validation_plan,
    compare_domain_diagnostics,
    make_domain_validation_plan,
    summarize_domain,
)
from casmi26.schemas import ProcessedSpectrum


IDENTITIES = tuple(letter * 14 for letter in "ABCDEFG")
PRIOR_FINAL = "F" * 14


def _record(
    spectrum_id: str,
    identity: str,
    *,
    source: str,
    instrument: str,
    offset: float,
    collision_energy: tuple[float, ...] = (20.0,),
    adduct: str = "[M+H]+",
    intensity: tuple[float, ...] = (1.0, 0.01, 0.001),
) -> ProcessedSpectrum:
    return ProcessedSpectrum(
        spectrum_id=spectrum_id,
        molecule_id=identity,
        mz=np.asarray([50.0 + offset, 75.0 + offset, 100.0 + offset]),
        intensity=np.asarray(intensity, dtype=np.float64),
        precursor_mz=250.0 + offset,
        neutral_mass=248.9927 + offset,
        adduct=adduct,
        ion_mode="positive",
        collision_energy_ev=collision_energy,
        instrument=instrument,
        quality={"base_peak_intensity": 1_000.0 + offset},
        normalized_smiles=None,
        inchikey14=identity,
        molecular_formula="C10H16O2",
        ingest_lib=source,
    )


def _collection() -> list[ProcessedSpectrum]:
    records: list[ProcessedSpectrum] = []
    for index, identity in enumerate(IDENTITIES[:6]):
        base = 10.0 * index
        records.extend(
            (
                _record(
                    f"{identity}-query-1",
                    identity,
                    source="enveda-np-examples",
                    instrument="timsTOF",
                    offset=base + 0.1,
                    collision_energy=(10.0,),
                ),
                _record(
                    f"{identity}-query-2",
                    identity,
                    source="enveda-np-examples",
                    instrument="timsTOF",
                    offset=base + 0.2,
                    collision_energy=(20.0, 30.0),
                ),
                _record(
                    f"{identity}-reference",
                    identity,
                    source="riken",
                    instrument="Orbitrap",
                    offset=base + 0.3,
                    collision_energy=(35.0,),
                ),
            )
        )
    records.append(
        _record(
            "background-reference",
            IDENTITIES[6],
            source="gnps",
            instrument="QTOF",
            offset=90.0,
        )
    )
    return records


def _plan(records: list[ProcessedSpectrum] | None = None):
    return make_domain_validation_plan(
        _collection() if records is None else records,
        candidate_identity_keys=IDENTITIES,
        prior_final_identity_keys=(PRIOR_FINAL,),
        sealed_fraction=0.2,
        seed=2027,
    )


def test_builds_paired_conditions_and_excludes_prior_final() -> None:
    records = _collection()
    plan = _plan(records)

    assert len(plan.manifests) == 6
    assert len(plan.development_identity_keys) == 4
    assert len(plan.sealed_identity_keys) == 1
    assert PRIOR_FINAL not in plan.development_identity_keys
    assert PRIOR_FINAL not in plan.sealed_identity_keys
    assert plan.metadata["eligible_identity_count"] == 5

    a = plan.manifest("A_library_visible")
    b = plan.manifest("B_structure_known_spectra_hidden")
    c = plan.manifest("C_structure_absent")
    by_id = {record.spectrum_id: record.inchikey14 for record in records}
    a_reference_keys = {by_id[value] for value in a.reference_spectrum_ids}
    b_reference_keys = {by_id[value] for value in b.reference_spectrum_ids}

    assert set(a.validation_identity_keys) <= a_reference_keys
    assert not (set(b.validation_identity_keys) & b_reference_keys)
    assert set(b.validation_identity_keys) <= set(b.candidate_identity_keys)
    assert not (set(c.validation_identity_keys) & set(c.candidate_identity_keys))
    assert b.query_spectrum_ids == c.query_spectrum_ids == a.query_spectrum_ids


def test_sealed_stage_requires_explicit_unlock_and_default_export_is_redacted() -> None:
    plan = _plan()
    with pytest.raises(SealedHoldoutAccessError):
        plan.manifest("A_library_visible", stage="sealed")

    sealed = plan.manifest(
        "A_library_visible", stage="sealed", allow_sealed=True
    )
    assert sealed.validation_identity_keys == plan.sealed_identity_keys
    redacted = plan.to_dict()
    assert redacted["sealed_identity_keys"] == []
    assert redacted["sealed_holdout_commitment"] == plan.sealed_holdout_commitment
    assert all(
        not item["query_spectrum_ids"]
        for item in redacted["manifests"]
        if item["stage"] == "sealed"
    )


def test_plan_is_deterministic_under_input_reordering() -> None:
    records = _collection()
    first = _plan(records)
    second = _plan(list(reversed(records)))
    assert first.manifest_hash == second.manifest_hash
    assert first.dataset_fingerprint == second.dataset_fingerprint


def test_audit_binds_plan_to_exact_dataset_state() -> None:
    records = _collection()
    plan = _plan(records)
    changed = [
        replace(record, precursor_mz=record.precursor_mz + 0.001)
        if index == 0
        else record
        for index, record in enumerate(records)
    ]
    report = audit_domain_validation_plan(plan, changed)
    assert report.checks["dataset_fingerprint_match"] is False
    assert "dataset_fingerprint_mismatch" in {item.code for item in report.issues}


def test_development_references_never_use_sealed_or_prior_final_identities() -> None:
    records = _collection()
    plan = _plan(records)
    identity = {record.spectrum_id: record.inchikey14 for record in records}
    forbidden = set(plan.sealed_identity_keys) | {PRIOR_FINAL}
    for condition in (
        "A_library_visible",
        "B_structure_known_spectra_hidden",
        "C_structure_absent",
    ):
        manifest = plan.manifest(condition)
        assert not ({identity[value] for value in manifest.reference_spectrum_ids} & forbidden)


def test_content_duplicate_is_excluded_even_when_provenance_changes() -> None:
    records = _collection()
    original = next(item for item in records if item.spectrum_id.endswith("query-1"))
    copied = replace(
        original,
        spectrum_id="copied-under-new-source",
        ingest_lib="massbank",
        instrument="Orbitrap",
    )
    records.append(copied)

    plan = _plan(records)
    assert copied.spectrum_id in plan.excluded_duplicate_reference_ids
    assert all(
        copied.spectrum_id not in manifest.reference_spectrum_ids
        for manifest in plan.manifests
    )
    assert audit_domain_validation_plan(plan, records).passed


def test_same_source_distinct_acquisition_can_be_reserved_for_condition_a() -> None:
    records: list[ProcessedSpectrum] = []
    for identity_index, identity in enumerate(IDENTITIES[:2]):
        for acquisition in range(3):
            records.append(
                _record(
                    f"{identity}-{acquisition}",
                    identity,
                    source="enveda-np-examples",
                    instrument="timsTOF",
                    offset=identity_index * 10.0 + acquisition,
                )
            )
    plan = make_domain_validation_plan(
        records,
        candidate_identity_keys=IDENTITIES[:2],
        prior_final_identity_keys=(PRIOR_FINAL,),
        sealed_fraction=0.5,
    )
    for stage in ("development", "sealed"):
        manifest = plan.manifest(
            "A_library_visible",
            stage=stage,
            allow_sealed=stage == "sealed",
        )
        assert len(manifest.query_spectrum_ids) == 2
        assert len(
            set(manifest.query_spectrum_ids) & set(manifest.reference_spectrum_ids)
        ) == 0


def test_missing_reference_provenance_fails_closed() -> None:
    records = _collection()
    changed = [
        replace(record, ingest_lib=None)
        if record.spectrum_id == "background-reference"
        else record
        for record in records
    ]
    with pytest.raises(DomainValidationError, match="missing_spectral_provenance"):
        _plan(changed)


def test_audit_catches_structure_known_identity_leakage() -> None:
    records = _collection()
    plan = _plan(records)
    b = plan.manifest("B_structure_known_spectra_hidden")
    a = plan.manifest("A_library_visible")
    identities = {record.spectrum_id: record.inchikey14 for record in records}
    leaked_reference = next(
        spectrum_id
        for spectrum_id in a.reference_spectrum_ids
        if identities[spectrum_id] in set(b.validation_identity_keys)
    )
    bad_b = replace(
        b,
        reference_spectrum_ids=tuple(sorted((*b.reference_spectrum_ids, leaked_reference))),
    )
    bad = replace(
        plan,
        manifests=tuple(bad_b if item == b else item for item in plan.manifests),
    )

    report = audit_domain_validation_plan(bad, records)
    assert not report.passed
    assert "structure_known_visibility_violation" in {item.code for item in report.issues}


def test_audit_catches_query_reference_content_overlap() -> None:
    records = _collection()
    plan = _plan(records)
    a = plan.manifest("A_library_visible")
    bad_a = replace(
        a,
        reference_spectrum_ids=tuple(sorted((*a.reference_spectrum_ids, a.query_spectrum_ids[0]))),
    )
    bad = replace(
        plan,
        manifests=tuple(bad_a if item == a else item for item in plan.manifests),
    )
    report = audit_domain_validation_plan(bad, records)
    codes = {item.code for item in report.issues}
    assert "query_reference_membership_overlap" in codes
    assert "query_reference_content_overlap" in codes


def test_audit_catches_structure_absent_candidate_contamination() -> None:
    records = _collection()
    plan = _plan(records)
    c = plan.manifest("C_structure_absent")
    bad_c = replace(
        c,
        candidate_identity_keys=tuple(
            sorted((*c.candidate_identity_keys, c.validation_identity_keys[0]))
        ),
    )
    bad = replace(
        plan,
        manifests=tuple(bad_c if item == c else item for item in plan.manifests),
    )
    report = audit_domain_validation_plan(bad, records)
    assert "structure_absent_visibility_violation" in {
        item.code for item in report.issues
    }


def test_audit_catches_query_provenance_change() -> None:
    records = _collection()
    plan = _plan(records)
    query_id = plan.manifest("A_library_visible").query_spectrum_ids[0]
    changed = [
        replace(record, ingest_lib="wrong-source")
        if record.spectrum_id == query_id
        else record
        for record in records
    ]
    report = audit_domain_validation_plan(plan, changed)
    assert not report.passed
    assert report.checks["query_provenance_failure_count"] > 0


def test_prior_final_evidence_is_required() -> None:
    with pytest.raises(DomainValidationError, match="prior_final_identity_keys"):
        make_domain_validation_plan(
            _collection(),
            candidate_identity_keys=IDENTITIES,
            prior_final_identity_keys=(),
        )


def test_ineligible_single_acquisition_identities_fail_closed() -> None:
    records = [
        _record(
            "one",
            IDENTITIES[0],
            source="enveda-np-examples",
            instrument="timsTOF",
            offset=1.0,
        ),
        _record(
            "two",
            IDENTITIES[1],
            source="enveda-np-examples",
            instrument="timsTOF",
            offset=2.0,
        ),
    ]
    with pytest.raises(DomainValidationError, match="At least two eligible"):
        make_domain_validation_plan(
            records,
            candidate_identity_keys=IDENTITIES[:2],
            prior_final_identity_keys=(PRIOR_FINAL,),
        )


def test_invalid_identity_and_fraction_fail_closed() -> None:
    with pytest.raises(DomainValidationError, match="invalid InChIKey14"):
        make_domain_validation_plan(
            _collection(),
            candidate_identity_keys=("not-a-key",),
            prior_final_identity_keys=(PRIOR_FINAL,),
        )
    with pytest.raises(DomainValidationError, match="sealed_fraction"):
        make_domain_validation_plan(
            _collection(),
            candidate_identity_keys=IDENTITIES,
            prior_final_identity_keys=(PRIOR_FINAL,),
            sealed_fraction=1.0,
        )


def test_domain_summary_covers_requested_acquisition_and_noise_diagnostics() -> None:
    records = _collection()
    summary = summarize_domain(records)
    assert summary["spectrum_count"] == len(records)
    assert summary["identity_count"] == len(IDENTITIES)
    assert summary["instrument_counts"]["timsTOF"] == 12
    assert summary["instrument_counts"]["Orbitrap"] == 6
    assert summary["numeric"]["precursor_mz"]["count"] == len(records)
    assert summary["numeric"]["collision_energy_mean_ev"]["count"] == len(records)
    assert summary["numeric"]["peak_count"]["median"] == 3.0
    assert summary["numeric"]["low_intensity_fraction_le_1pct"]["median"] == pytest.approx(2 / 3)
    assert summary["numeric"]["base_peak_intensity_log10"]["count"] == len(records)
    assert "timsTOF" in summary["by_instrument"]
    assert "low_intensity_fraction_le_1pct" in summary["noise_floor_proxy_definition"]


def test_domain_comparison_reports_numeric_and_categorical_shift() -> None:
    train = _collection()[:6]
    test = [replace(record, spectrum_id=f"test-{index}") for index, record in enumerate(train)]
    domain = [replace(record, spectrum_id=f"domain-{index}") for index, record in enumerate(train)]
    report = compare_domain_diagnostics(train=train, test=test, domain=domain)

    identical = report["pairwise_shift"]["domain_to_test"]
    assert identical["numeric"]["precursor_mz"]["ks_distance"] == 0.0
    assert identical["categorical"]["instrument"]["total_variation_distance"] == 0.0
    assert "does not prove" in report["interpretation_guard"]


def test_domain_comparison_exposes_instrument_and_peak_count_shift() -> None:
    train = _collection()[:6]
    shifted = [
        replace(
            record,
            spectrum_id=f"shift-{index}",
            instrument="QTOF",
            mz=np.append(record.mz, [150.0, 175.0]),
            intensity=np.append(record.intensity, [0.2, 0.1]),
        )
        for index, record in enumerate(train)
    ]
    report = compare_domain_diagnostics(train=train, test=shifted, domain=train)
    shift = report["pairwise_shift"]["train_to_test"]
    assert shift["categorical"]["instrument"]["total_variation_distance"] > 0.0
    assert shift["numeric"]["peak_count"]["median_delta_right_minus_left"] == 2.0


def test_audit_passes_all_six_generated_manifests() -> None:
    records = _collection()
    plan = _plan(records)
    report = audit_domain_validation_plan(plan, records)
    assert report.passed
    assert report.checks["condition_matrix_complete"] is True
    assert report.checks["query_reference_content_collision_count"] == 0
    assert report.checks["visibility_failure_count"] == 0
    assert report.checks["sealed_identity_in_development_reference_count"] == 0
    assert report.checks["prior_final_identity_in_query_or_reference_count"] == 0
