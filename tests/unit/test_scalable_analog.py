from __future__ import annotations

import numpy as np
import pytest

from casmi26.analog_propagation import (
    AnalogLeakageError,
    AnalogReference,
    LeakagePolicy,
    retrieve_analogs,
    spectrum_content_hash,
)
from casmi26.scalable_analog import ScalableAnalogIndex
from casmi26.schemas import ProcessedSpectrum


def _spectrum(
    spectrum_id: str,
    identity: str,
    mass: float,
    peaks: tuple[float, ...],
    *,
    ion_mode: str = "positive",
) -> ProcessedSpectrum:
    return ProcessedSpectrum(
        spectrum_id=spectrum_id,
        molecule_id=identity,
        mz=np.asarray(peaks, dtype=np.float64),
        intensity=np.linspace(1.0, 0.5, len(peaks)),
        precursor_mz=mass + 1.007276466621,
        neutral_mass=mass,
        adduct="[M+H]+",
        ion_mode=ion_mode,
        collision_energy_ev=(20.0,),
        instrument="timsTOF",
        quality={},
        inchikey14=identity,
    )


def _reference(
    reference_id: str,
    identity: str,
    mass: float,
    peaks: tuple[float, ...],
    *,
    ion_mode: str = "positive",
) -> AnalogReference:
    spectrum = _spectrum(reference_id, identity, mass, peaks, ion_mode=ion_mode)
    return AnalogReference(
        reference_id=reference_id,
        structure_id=identity,
        inchikey14=identity,
        neutral_mass=mass,
        spectrum=spectrum,
        fingerprint=np.asarray([1, 0, 1], dtype=np.uint8),
    )


def _references() -> list[AnalogReference]:
    return [
        _reference("far-low", "A" * 14, 50.0, (10.0, 20.0)),
        _reference("near", "B" * 14, 200.0, (50.0, 75.0)),
        _reference("near-neg", "C" * 14, 201.0, (50.0, 75.0), ion_mode="negative"),
        _reference("far-high", "D" * 14, 500.0, (10.0, 20.0)),
    ]


def test_indexed_analog_retrieval_is_equivalent_to_goal4_brute_force() -> None:
    references = _references()
    query = _spectrum("query", "Q" * 14, 200.0, (50.0, 75.0))
    policy = LeakagePolicy(query_inchikey14="Q" * 14)
    expected = retrieve_analogs(
        [query],
        references,
        query_neutral_mass=200.0,
        policy=policy,
        mass_window_da=10.0,
        top_k=10,
    )
    observed, report = ScalableAnalogIndex(references).retrieve(
        [query],
        query_neutral_mass=200.0,
        policy=policy,
        mass_window_da=10.0,
        top_k=10,
    )
    assert [hit.reference.reference_id for hit in observed] == [
        hit.reference.reference_id for hit in expected
    ]
    assert [hit.spectral_similarity for hit in observed] == pytest.approx(
        [hit.spectral_similarity for hit in expected]
    )
    assert report.mass_window_reference_spectra == 2
    assert report.scored_reference_spectra == 1
    assert report.reduction_fraction == pytest.approx(0.5)


def test_index_audits_entire_library_before_mass_window() -> None:
    references = _references()
    index = ScalableAnalogIndex(references)
    query = _spectrum("query", "Q" * 14, 200.0, (50.0, 75.0))
    with pytest.raises(AnalogLeakageError, match="Forbidden holdout identity"):
        index.retrieve(
            [query],
            query_neutral_mass=200.0,
            policy=LeakagePolicy(forbidden_inchikey14=frozenset({"A" * 14})),
            mass_window_da=10.0,
        )
    digest = spectrum_content_hash(references[-1].spectrum)
    with pytest.raises(AnalogLeakageError, match="Forbidden holdout spectrum"):
        index.retrieve(
            [query],
            query_neutral_mass=200.0,
            policy=LeakagePolicy(forbidden_spectrum_hashes=frozenset({digest})),
            mass_window_da=10.0,
        )


def test_index_is_sorted_and_validates_contracts() -> None:
    index = ScalableAnalogIndex(list(reversed(_references())))
    assert np.all(np.diff(index.masses) >= 0.0)
    assert not index.masses.flags.writeable
    with pytest.raises(ValueError, match="unique"):
        ScalableAnalogIndex([_references()[0], _references()[0]])
    with pytest.raises(ValueError, match="mass_window_da"):
        index.window(200.0, mass_window_da=0.0)
