from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from casmi26.chemistry import canonical_inchikey14
from casmi26.schemas import ProcessedSpectrum
from casmi26.splits import (
    dataset_fingerprint,
    generate_split,
    load_split_manifest,
    make_library_holdout,
    make_molecule_disjoint_split,
    make_novelty_holdout_split,
    save_split_manifest,
    spectrum_fingerprint,
    spectrum_hash_mapping,
    spectrum_identity_mapping,
)


SMILES = ("CCO", "CCN", "CCC", "CCCl", "CCBr", "CCF")
KEYS = tuple(canonical_inchikey14(smiles) for smiles in SMILES)
assert all(KEYS)


def _spectrum(
    identity_index: int,
    acquisition_index: int,
    *,
    spectrum_id: str | None = None,
    source: str | None = None,
    instrument: str | None = None,
) -> ProcessedSpectrum:
    base = 60.0 + identity_index * 17.0 + acquisition_index * 0.4
    return ProcessedSpectrum(
        spectrum_id=spectrum_id or f"s-{identity_index}-{acquisition_index}",
        molecule_id=f"m-{identity_index}",
        mz=np.asarray([base, base + 12.0, base + 29.0], dtype=np.float64),
        intensity=np.asarray([0.8, 0.5, 0.2], dtype=np.float64),
        precursor_mz=201.0 + identity_index,
        neutral_mass=199.9927 + identity_index,
        adduct="[M+H]+" if identity_index % 2 == 0 else "[M-H]-",
        ion_mode="positive" if identity_index % 2 == 0 else "negative",
        collision_energy_ev=(10.0 + acquisition_index,),
        instrument=instrument or ("timsTOF" if identity_index % 2 == 0 else "Orbitrap"),
        quality={"retained_peak_count": 3.0},
        normalized_smiles=SMILES[identity_index],
        inchikey14=KEYS[identity_index],
        molecular_formula="C2H6O",
        ingest_lib=source or ("source-a" if identity_index < 3 else "source-b"),
    )


def _dataset(acquisitions: int = 3) -> list[ProcessedSpectrum]:
    return [
        _spectrum(identity_index, acquisition_index)
        for identity_index in range(len(KEYS))
        for acquisition_index in range(acquisitions)
    ]


def _by_id(spectra: list[ProcessedSpectrum]) -> dict[str, ProcessedSpectrum]:
    return {spectrum.spectrum_id: spectrum for spectrum in spectra}


def test_library_holdout_uses_distinct_acquisitions_and_removes_replicates() -> None:
    spectra = _dataset()
    duplicate = _spectrum(0, 0, spectrum_id="zz-replicated-acquisition")
    spectra.append(duplicate)

    manifest = make_library_holdout(spectra, validation_fraction=0.34, seed=41)
    lookup = _by_id(spectra)
    reference = [lookup[value] for value in manifest.reference_spectrum_ids]
    validation = [lookup[value] for value in manifest.validation_spectrum_ids]

    assert manifest.protocol == "library_holdout"
    assert set(manifest.train_spectrum_ids).isdisjoint(manifest.reference_spectrum_ids)
    assert set(manifest.reference_spectrum_ids).isdisjoint(manifest.validation_spectrum_ids)
    assert {spectrum_fingerprint(item) for item in reference}.isdisjoint(
        spectrum_fingerprint(item) for item in validation
    )
    assert manifest.metadata["deduplication"]["excluded_count"] == 1
    assert "zz-replicated-acquisition" in manifest.metadata["deduplication"][
        "excluded_spectrum_ids"
    ]
    for key in manifest.validation_identity_keys:
        assert any(item.inchikey14 == key for item in reference)
        assert any(item.inchikey14 == key for item in validation)


def test_library_holdout_keeps_singletons_reference_only() -> None:
    spectra = _dataset(acquisitions=2) + [_spectrum(0, 9, spectrum_id="singleton")]
    # Make the additional record a genuinely separate singleton identity.
    singleton = spectra[-1]
    object.__setattr__(singleton, "inchikey14", "GGGGGGGGGGGGGG")
    object.__setattr__(singleton, "molecule_id", "m-singleton")
    object.__setattr__(singleton, "normalized_smiles", None)

    manifest = make_library_holdout(spectra, validation_fraction=0.5, seed=7)

    assert "singleton" in manifest.reference_spectrum_ids
    assert "singleton" not in manifest.validation_spectrum_ids
    assert "GGGGGGGGGGGGGG" not in manifest.validation_identity_keys


def test_molecule_disjoint_has_no_labeled_or_spectral_identity_overlap() -> None:
    spectra = _dataset()
    manifest = make_molecule_disjoint_split(
        spectra,
        validation_fraction=0.34,
        seed=123,
        candidate_identity_keys=("EXTERNALKEY000",),
    )
    lookup = _by_id(spectra)
    validation_keys = set(manifest.validation_identity_keys)

    assert validation_keys.isdisjoint(manifest.ranker_train_identity_keys)
    assert set(manifest.train_spectrum_ids).isdisjoint(manifest.reference_spectrum_ids)
    assert validation_keys <= set(manifest.candidate_identity_keys)
    assert "EXTERNALKEY000" in manifest.candidate_identity_keys
    assert all(
        lookup[spectrum_id].inchikey14 not in validation_keys
        for spectrum_id in manifest.reference_spectrum_ids
    )
    assert all(
        lookup[spectrum_id].inchikey14 in validation_keys
        for spectrum_id in manifest.validation_spectrum_ids
    )


def test_novelty_holdout_removes_validation_from_candidate_database() -> None:
    spectra = _dataset()
    # Deliberately supply all targets as candidate input: the generator must
    # still remove the novelty targets selected by the split.
    manifest = make_novelty_holdout_split(
        spectra,
        validation_fraction=0.34,
        seed=123,
        candidate_identity_keys=KEYS + ("EXTERNALKEY000",),
    )
    validation_keys = set(manifest.validation_identity_keys)

    assert validation_keys.isdisjoint(manifest.ranker_train_identity_keys)
    assert validation_keys.isdisjoint(manifest.candidate_identity_keys)
    assert set(manifest.ranker_train_identity_keys) <= set(manifest.candidate_identity_keys)
    assert "EXTERNALKEY000" in manifest.candidate_identity_keys


def test_splits_are_order_independent_reproducible_and_seeded() -> None:
    spectra = _dataset()
    reversed_spectra = list(reversed(spectra))

    first = make_molecule_disjoint_split(spectra, validation_fraction=0.34, seed=11)
    repeated = make_molecule_disjoint_split(reversed_spectra, validation_fraction=0.34, seed=11)
    changed_seed = make_molecule_disjoint_split(spectra, validation_fraction=0.34, seed=29)

    assert first == repeated
    assert first.manifest_hash == repeated.manifest_hash
    assert first.validation_identity_keys != changed_seed.validation_identity_keys
    assert dataset_fingerprint(spectra) == dataset_fingerprint(reversed_spectra)


def test_molecule_and_novelty_membership_is_paired() -> None:
    spectra = _dataset()
    molecule = make_molecule_disjoint_split(spectra, validation_fraction=0.34, seed=17)
    novelty = make_novelty_holdout_split(spectra, validation_fraction=0.34, seed=17)

    assert molecule.train_spectrum_ids == novelty.train_spectrum_ids
    assert molecule.reference_spectrum_ids == novelty.reference_spectrum_ids
    assert molecule.validation_spectrum_ids == novelty.validation_spectrum_ids
    assert molecule.validation_identity_keys == novelty.validation_identity_keys
    assert set(molecule.validation_identity_keys) <= set(molecule.candidate_identity_keys)
    assert set(novelty.validation_identity_keys).isdisjoint(novelty.candidate_identity_keys)


def test_validation_stages_are_disjoint_complete_and_deterministic() -> None:
    spectra = _dataset()
    first = make_molecule_disjoint_split(spectra, validation_fraction=0.67, seed=19)
    repeated = make_molecule_disjoint_split(list(reversed(spectra)), validation_fraction=0.67, seed=19)
    selection = set(first.metadata["model_selection_identity_keys"])
    final = set(first.metadata["final_evaluation_identity_keys"])

    assert selection
    assert final
    assert selection.isdisjoint(final)
    assert selection | final == set(first.validation_identity_keys)
    assert first.metadata["model_selection_identity_keys"] == repeated.metadata[
        "model_selection_identity_keys"
    ]
    assert first.metadata["final_evaluation_identity_keys"] == repeated.metadata[
        "final_evaluation_identity_keys"
    ]


def test_audit_evidence_mappings_cover_every_input_spectrum() -> None:
    spectra = _dataset()
    identities = spectrum_identity_mapping(spectra)
    hashes = spectrum_hash_mapping(spectra)

    assert set(identities) == {item.spectrum_id for item in spectra}
    assert set(hashes) == set(identities)
    assert identities["s-0-0"] == KEYS[0]
    assert len(hashes["s-0-0"]) == 64


def test_manifest_round_trip_preserves_deterministic_hash(tmp_path: Path) -> None:
    manifest = generate_split(
        "novelty_holdout", _dataset(), validation_fraction=0.34, seed=2026
    )
    path = tmp_path / "nested" / "manifest.json"

    save_split_manifest(manifest, path)
    loaded = load_split_manifest(path)

    assert loaded == manifest
    assert loaded.manifest_hash == manifest.manifest_hash
    assert len(manifest.manifest_hash) == 64


def test_manifest_preserves_domain_shift_summaries() -> None:
    manifest = make_molecule_disjoint_split(_dataset(), validation_fraction=0.34, seed=3)
    summaries = manifest.metadata["domain_summary"]

    for partition in ("train", "reference", "validation"):
        summary = summaries[partition]
        assert summary["spectrum_count"] > 0
        assert summary["identity_count"] > 0
        assert sum(summary["source_counts"].values()) == summary["spectrum_count"]
        assert sum(summary["instrument_counts"].values()) == summary["spectrum_count"]
        assert sum(summary["adduct_counts"].values()) == summary["spectrum_count"]
        assert summary["neutral_mass"]["count"] == summary["spectrum_count"]
        assert summary["peak_count"]["mean"] == pytest.approx(3.0)


@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.1, float("nan")])
def test_invalid_validation_fraction_fails_fast(fraction: float) -> None:
    with pytest.raises(ValueError, match="validation_fraction"):
        make_molecule_disjoint_split(_dataset(), validation_fraction=fraction)


def test_missing_identity_and_duplicate_spectrum_ids_fail_fast() -> None:
    missing = _spectrum(0, 0)
    object.__setattr__(missing, "inchikey14", None)
    object.__setattr__(missing, "normalized_smiles", None)
    with pytest.raises(ValueError, match="no normalized chemical identity"):
        make_library_holdout([missing, _spectrum(0, 1)])

    duplicate_ids = [_spectrum(0, 0), _spectrum(1, 0, spectrum_id="s-0-0")]
    with pytest.raises(ValueError, match="Duplicate spectrum_id"):
        make_molecule_disjoint_split(duplicate_ids)


def test_provided_identity_must_match_canonical_smiles() -> None:
    inconsistent = _spectrum(0, 0)
    object.__setattr__(inconsistent, "inchikey14", KEYS[1])
    with pytest.raises(ValueError, match="inconsistent provided/canonical"):
        make_library_holdout([inconsistent, _spectrum(0, 1)])
