from __future__ import annotations

import numpy as np

from casmi26.analog_propagation import AnalogReference
from casmi26.fingerprints import molecular_fingerprint
from casmi26.goal3_contracts import FingerprintSpec
from casmi26.goal4_pipeline import (
    ANALOG_FEATURE,
    FRAGMENT_FEATURE,
    NEUTRAL_FEATURE,
    Goal4ExperimentConfig,
    _annotate_query,
    _per_query_change_counts,
)
from casmi26.mass_retrieval import MassCandidateIndex, StructureCandidate
from casmi26.schemas import ProcessedSpectrum


def _spectrum(
    spectrum_id: str,
    molecule_id: str,
    *,
    precursor: float,
    neutral: float,
    peaks: tuple[float, ...],
) -> ProcessedSpectrum:
    return ProcessedSpectrum(
        spectrum_id=spectrum_id,
        molecule_id=molecule_id,
        mz=np.asarray(peaks, dtype=np.float32),
        intensity=np.asarray([1.0 / len(peaks)] * len(peaks), dtype=np.float32),
        precursor_mz=precursor,
        neutral_mass=neutral,
        adduct="[M+H]+",
        ion_mode="positive",
        collision_energy_ev=(20.0,),
        instrument="timsTOF",
        quality={},
        inchikey14=molecule_id,
    )


def test_annotation_preserves_fixed_pool_and_adds_candidate_specific_features() -> None:
    methane = StructureCandidate("AAAAAAAAAAAAAA", "C", 16.031300128, "CH4")
    ethane = StructureCandidate("BBBBBBBBBBBBBB", "CC", 30.046950192, "C2H6")
    candidates = {item.candidate_id: item for item in (methane, ethane)}
    query = _spectrum(
        "query-spectrum",
        "CCCCCCCCCCCCCC",
        precursor=31.0542,
        neutral=30.04695,
        peaks=(13.043, 15.023, 29.039),
    )
    reference_spectrum = _spectrum(
        "reference-spectrum",
        methane.candidate_id,
        precursor=17.0386,
        neutral=methane.exact_mass,
        peaks=(13.043, 15.023),
    )
    spec = FingerprintSpec(n_bits=128)
    reference = AnalogReference(
        reference_id=reference_spectrum.spectrum_id,
        structure_id=methane.candidate_id,
        inchikey14=methane.candidate_id,
        neutral_mass=methane.exact_mass,
        spectrum=reference_spectrum,
        fingerprint=molecular_fingerprint(methane.smiles, spec),
        formula=methane.formula,
    )
    hits = MassCandidateIndex([methane, ethane]).retrieve(query.neutral_mass, top_k=2)
    annotated, report = _annotate_query(
        query.molecule_id,
        [query],
        hits,
        [reference],
        candidates,
        {},
        spec,
        forbidden_identities=frozenset({query.molecule_id}),
        forbidden_hashes=frozenset(),
        config=Goal4ExperimentConfig(
            candidate_pool_size=2,
            fingerprint_bits=128,
            analog_top_k=1,
            ranker_backend="hist_gbdt",
        ),
    )
    assert [item.candidate_id for item in annotated] == [item.candidate_id for item in hits]
    for item in annotated:
        assert NEUTRAL_FEATURE in item.features
        assert FRAGMENT_FEATURE in item.features
        assert ANALOG_FEATURE in item.features
    assert report["analog_hit_count"] == 1


def test_change_counts_use_mrr_at_25_not_raw_rank_beyond_cutoff() -> None:
    truths = {"q": "truth"}
    baseline = {"q": [*[f"x{i}" for i in range(25)], "truth"]}
    challenger = {"q": ["truth"]}
    result = _per_query_change_counts(truths, baseline, challenger)
    assert result["improved_count"] == 1
    assert result["worsened_count"] == 0
