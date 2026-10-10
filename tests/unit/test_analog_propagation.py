from dataclasses import replace

import numpy as np
import pytest

from casmi26.analog_propagation import (
    AnalogCandidate,
    AnalogLeakageError,
    AnalogReference,
    LeakagePolicy,
    audit_reference_library,
    fingerprint_tanimoto,
    plausible_mass_transforms,
    propagate_analog_scores,
    retrieve_analogs,
    score_analog_candidates,
    spectrum_content_hash,
)
from casmi26.schemas import ProcessedSpectrum


def spectrum(
    spectrum_id: str,
    molecule_id: str,
    mz: list[float],
    *,
    precursor_mz: float = 200.0,
    neutral_mass: float = 198.992723533379,
    adduct: str = "[M+H]+",
    ion_mode: str = "positive",
    instrument: str = "timsTOF",
) -> ProcessedSpectrum:
    intensity = np.linspace(1.0, 0.5, len(mz), dtype=np.float64)
    return ProcessedSpectrum(
        spectrum_id=spectrum_id,
        molecule_id=molecule_id,
        mz=np.asarray(mz, dtype=np.float64),
        intensity=intensity,
        precursor_mz=precursor_mz,
        neutral_mass=neutral_mass,
        adduct=adduct,
        ion_mode=ion_mode,
        collision_energy_ev=(20.0,),
        instrument=instrument,
        quality={},
        inchikey14=molecule_id,
    )


def reference(
    reference_id: str,
    key: str,
    peaks: list[float],
    fingerprint: list[int],
    *,
    mass: float = 198.992723533379,
    **spectrum_kwargs: object,
) -> AnalogReference:
    return AnalogReference(
        reference_id=reference_id,
        structure_id=key,
        inchikey14=key,
        neutral_mass=mass,
        spectrum=spectrum(reference_id, key, peaks, neutral_mass=mass, **spectrum_kwargs),
        fingerprint=np.asarray(fingerprint, dtype=np.uint8),
        formula="C6H12O6",
        source="fixture",
    )


def test_spectrum_hash_is_order_and_identifier_invariant() -> None:
    first = spectrum("a", "key-a", [50.0, 75.0])
    second = spectrum("b", "key-b", [75.0, 50.0])
    second = replace(second, intensity=first.intensity[::-1], instrument="Orbitrap")
    assert spectrum_content_hash(first) == spectrum_content_hash(second)


def test_reference_audit_blocks_holdout_identity() -> None:
    held_out = reference("r1", "held-out", [50.0], [1, 0, 1])
    policy = LeakagePolicy(forbidden_inchikey14=frozenset({"held-out"}))
    with pytest.raises(AnalogLeakageError, match="Forbidden holdout identity"):
        audit_reference_library([held_out], policy)


def test_reference_audit_blocks_forbidden_content_and_duplicates() -> None:
    first = reference("r1", "key-a", [50.0, 75.0], [1, 0, 1])
    duplicate = replace(
        reference("r2", "key-b", [50.0, 75.0], [0, 1, 0]),
        spectrum=replace(first.spectrum, spectrum_id="r2", molecule_id="key-b"),
    )
    digest = spectrum_content_hash(first.spectrum)
    with pytest.raises(AnalogLeakageError, match="Forbidden holdout spectrum"):
        audit_reference_library(
            [first], LeakagePolicy(forbidden_spectrum_hashes=frozenset({digest}))
        )
    with pytest.raises(AnalogLeakageError, match="Duplicate analog spectrum"):
        audit_reference_library([first, duplicate], LeakagePolicy())


def test_identity_disjoint_policy_fails_on_same_query_identity() -> None:
    same = reference("r1", "query-key", [50.0], [1, 0])
    with pytest.raises(AnalogLeakageError, match="Query identity"):
        audit_reference_library(
            [same], LeakagePolicy(query_inchikey14="query-key", allow_same_identity=False)
        )


def test_retrieve_analogs_filters_mass_and_ion_mode() -> None:
    query = spectrum("q", "query", [50.0, 75.0])
    good = reference("good", "analog-a", [50.0, 75.0], [1, 1, 0])
    far = reference("far", "analog-b", [50.0, 75.0], [1, 0, 1], mass=500.0)
    negative = reference(
        "neg",
        "analog-c",
        [50.0, 75.0],
        [0, 1, 1],
        adduct="[M-H]-",
        ion_mode="negative",
    )
    hits = retrieve_analogs(
        [query],
        [good, far, negative],
        query_neutral_mass=query.neutral_mass or 0.0,
        policy=LeakagePolicy(query_inchikey14="query"),
        mass_window_da=200.0,
    )
    assert [hit.reference.reference_id for hit in hits] == ["good"]
    assert hits[0].spectral_similarity == pytest.approx(1.0)
    assert hits[0].same_instrument == 1.0


def test_plausible_mass_transform_is_hypothesis_with_exact_error() -> None:
    matches = plausible_mass_transforms(15.99491461957, tolerance_da=1e-6)
    assert matches[0].transform.name == "oxidation_or_hydroxylation"
    assert matches[0].error_da == pytest.approx(0.0, abs=1e-12)
    assert plausible_mass_transforms(13.37, tolerance_da=0.001) == ()


def test_fingerprint_tanimoto() -> None:
    assert fingerprint_tanimoto(np.array([1, 0, 1]), np.array([1, 1, 0])) == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match="aligned"):
        fingerprint_tanimoto(np.array([1, 0]), np.array([1, 0, 1]))


def test_candidate_scoring_prefers_structurally_related_candidate() -> None:
    query = spectrum("q", "query", [50.0, 75.0])
    analog = reference("r", "analog", [50.0, 75.0], [1, 1, 0, 0])
    hit = retrieve_analogs(
        [query],
        [analog],
        query_neutral_mass=query.neutral_mass or 0.0,
        policy=LeakagePolicy(query_inchikey14="query"),
    )[0]
    candidates = [
        AnalogCandidate("close", "close", query.neutral_mass or 0.0, np.array([1, 1, 0, 0])),
        AnalogCandidate("far", "far", query.neutral_mass or 0.0, np.array([0, 0, 1, 1])),
    ]
    scores = score_analog_candidates(
        candidates,
        [hit],
        query_neutral_mass=query.neutral_mass or 0.0,
    )
    assert [score.candidate_id for score in scores] == ["close", "far"]
    assert scores[0].score > scores[1].score
    assert scores[0].features["analog_best_structural_similarity"] == 1.0
    assert scores[0].best_reference_id == "r"
    without_context = score_analog_candidates(
        candidates,
        [hit],
        query_neutral_mass=query.neutral_mass or 0.0,
        include_transform=False,
        include_adduct=False,
    )
    assert without_context[0].score <= scores[0].score


def test_propagation_returns_scores_and_audited_hits_without_target_injection() -> None:
    query = spectrum("q", "query", [50.0, 75.0])
    analog = reference("r", "analog", [50.0, 75.0], [1, 1, 0])
    candidates = [
        AnalogCandidate(
            "candidate",
            "candidate",
            query.neutral_mass or 0.0,
            np.array([1, 1, 0]),
        )
    ]
    scores, hits = propagate_analog_scores(
        [query],
        candidates,
        [analog],
        query_neutral_mass=query.neutral_mass or 0.0,
        policy=LeakagePolicy(
            forbidden_inchikey14=frozenset({"query"}),
            query_inchikey14="query",
        ),
    )
    assert [score.candidate_id for score in scores] == ["candidate"]
    assert [hit.reference.inchikey14 for hit in hits] == ["analog"]
    assert "analog_score" in scores[0].features
