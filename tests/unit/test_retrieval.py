import numpy as np

from casmi26.retrieval import FEATURE_NAMES, SpectralLibraryIndex, feature_vector
from casmi26.schemas import LibraryEntry, ProcessedSpectrum


def spectrum(
    spectrum_id: str,
    key: str,
    smiles: str,
    mz: list[float],
    precursor: float = 200.0,
) -> ProcessedSpectrum:
    intensity = np.asarray([1.0, 0.7, 0.3][: len(mz)], dtype=np.float32)
    intensity /= np.linalg.norm(intensity)
    return ProcessedSpectrum(
        spectrum_id=spectrum_id,
        molecule_id=key,
        mz=np.asarray(mz, dtype=np.float32),
        intensity=intensity,
        precursor_mz=precursor,
        neutral_mass=precursor - 1.007276466621,
        adduct="[M+H]+",
        ion_mode="positive",
        collision_energy_ev=(20.0,),
        instrument="timsTOF",
        quality={},
        normalized_smiles=smiles,
        inchikey14=key,
    )


def test_retrieval_ranks_matching_spectrum_first() -> None:
    entries = [
        LibraryEntry("key-a", "CCO", spectrum("a", "key-a", "CCO", [50.0, 75.0, 100.0])),
        LibraryEntry("key-b", "CCN", spectrum("b", "key-b", "CCN", [55.0, 85.0, 110.0])),
    ]
    index = SpectralLibraryIndex(entries)
    query = spectrum("q", "key-a", "CCO", [50.005, 75.005, 100.005])
    hits = index.retrieve(query, top_k=2)
    assert [hit.candidate_id for hit in hits] == ["key-a", "key-b"]
    assert tuple(hits[0].features) == FEATURE_NAMES
    assert feature_vector(hits[0]).shape == (len(FEATURE_NAMES),)


def test_multi_acquisition_retrieval_deduplicates_candidates() -> None:
    entry = LibraryEntry("key-a", "CCO", spectrum("a", "key-a", "CCO", [50.0, 75.0, 100.0]))
    index = SpectralLibraryIndex([entry])
    hits = index.retrieve_many(
        [
            spectrum("q1", "q", "CCO", [50.0, 75.0, 100.0]),
            spectrum("q2", "q", "CCO", [50.01, 75.01, 100.01]),
        ]
    )
    assert len(hits) == 1
    assert hits[0].references_seen == 2


def test_mass_filter_adds_nearest_hard_negatives() -> None:
    entries = [
        LibraryEntry(
            f"key-{idx}",
            "C" * (idx + 1),
            spectrum(
                f"s-{idx}",
                f"key-{idx}",
                "C" * (idx + 1),
                [50.0 + idx, 75.0 + idx],
                precursor=200.0 + idx * 10.0,
            ),
        )
        for idx in range(5)
    ]
    index = SpectralLibraryIndex(entries, min_mass_candidates=3)
    candidates = index._mass_candidates(entries[0].spectrum)
    assert candidates == [0, 1, 2]


def test_multi_acquisition_keeps_best_not_worst_mass_error() -> None:
    entry = LibraryEntry("key-a", "CCO", spectrum("a", "key-a", "CCO", [50.0, 75.0]))
    index = SpectralLibraryIndex([entry])
    exact = spectrum("q1", "q", "CCO", [50.0, 75.0])
    shifted = spectrum("q2", "q", "CCO", [50.0, 75.0], precursor=200.01)
    hit = index.retrieve_many([exact, shifted], top_k=1)[0]
    assert hit.features["mass_error_ppm"] == 0.0
    assert hit.features["abs_precursor_delta"] == 0.0
