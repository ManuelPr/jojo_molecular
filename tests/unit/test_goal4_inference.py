from __future__ import annotations

import numpy as np
import pytest

from casmi26.goal4_inference import (
    _representative_reference_ids,
    aggregate_neutral_mass,
    exclude_query_duplicate_references,
    group_query_spectra,
    predict_nearest_mass,
)
from casmi26.analog_propagation import AnalogReference
from casmi26.mass_retrieval import StructureCandidate
from casmi26.schemas import ProcessedSpectrum


def _spectrum(spectrum_id: str, molecule_id: str, mass: float | None) -> ProcessedSpectrum:
    return ProcessedSpectrum(
        spectrum_id=spectrum_id,
        molecule_id=molecule_id,
        mz=np.asarray([50.0], dtype=np.float32),
        intensity=np.asarray([1.0], dtype=np.float32),
        precursor_mz=mass or 100.0,
        neutral_mass=mass,
        adduct="[M+H]+",
        ion_mode="positive",
        collision_energy_ev=(),
        instrument="fixture",
        quality={},
    )


def test_grouping_and_median_mass_are_acquisition_order_independent() -> None:
    grouped = group_query_spectra(
        [_spectrum("z", "q", 102.0), _spectrum("a", "q", 100.0)]
    )
    assert [item.spectrum_id for item in grouped["q"]] == ["a", "z"]
    assert aggregate_neutral_mass(grouped["q"]) == 101.0


def test_nearest_mass_prediction_is_unique_and_bounded() -> None:
    catalog = [
        StructureCandidate("A", "C", 16.0313),
        StructureCandidate("B", "CC", 30.0470),
    ]
    predictions = predict_nearest_mass(
        {"q": [_spectrum("s", "q", 16.0313)]},
        catalog,
        retrieval_pool_size=2,
        output_size=2,
    )
    assert len(predictions["q"]) == 2
    assert predictions["q"][0] == "C"


def test_retrieval_pool_must_cover_output() -> None:
    with pytest.raises(ValueError, match="at least"):
        predict_nearest_mass({}, [], retrieval_pool_size=1, output_size=2)


def test_representative_reference_is_deterministic_and_one_per_identity() -> None:
    low = _spectrum("a", "AAAAAAAAAAAAAA", 16.0)
    high = _spectrum("b", "AAAAAAAAAAAAAA", 16.0)
    high = ProcessedSpectrum(
        **{
            **{field: getattr(high, field) for field in high.__dataclass_fields__},
            "quality": {"retained_fraction": 1.0},
            "inchikey14": "AAAAAAAAAAAAAA",
        }
    )
    low = ProcessedSpectrum(
        **{
            **{field: getattr(low, field) for field in low.__dataclass_fields__},
            "quality": {"retained_fraction": 0.5},
            "inchikey14": "AAAAAAAAAAAAAA",
        }
    )
    assert _representative_reference_ids([low, high]) == ("b",)


def test_query_duplicate_reference_content_is_excluded_without_identity_access() -> None:
    duplicate = _spectrum("hidden", "unknown-test-id", 16.0)
    distinct = ProcessedSpectrum(
        **{
            **{
                field: getattr(duplicate, field)
                for field in duplicate.__dataclass_fields__
            },
            "spectrum_id": "distinct",
            "mz": np.asarray([51.0], dtype=np.float32),
        }
    )
    references = [
        AnalogReference(
            reference_id="copied-reference",
            structure_id="A",
            inchikey14="AAAAAAAAAAAAAA",
            neutral_mass=16.0,
            spectrum=_spectrum("train-copy", "AAAAAAAAAAAAAA", 16.0),
            fingerprint=np.zeros(8, dtype=np.uint8),
        ),
        AnalogReference(
            reference_id="safe-reference",
            structure_id="B",
            inchikey14="BBBBBBBBBBBBBB",
            neutral_mass=16.0,
            spectrum=distinct,
            fingerprint=np.zeros(8, dtype=np.uint8),
        ),
    ]

    kept, excluded = exclude_query_duplicate_references(references, [duplicate])

    assert [reference.reference_id for reference in kept] == ["safe-reference"]
    assert excluded == ("copied-reference",)
