import numpy as np
import pytest

from casmi26.spectral_evidence import (
    COMMON_NEUTRAL_LOSSES,
    aggregate_candidate_scores,
    balanced_acquisition_weights,
    candidate_spectrum_compatibility,
    cosine_similarity,
    detect_neutral_losses,
    formula_compatible_neutral_losses,
    match_peaks_one_to_one,
    modified_cosine_similarity,
    neutral_loss_candidate_compatibility,
    neutral_loss_fingerprint,
    neutral_loss_similarity,
    precursor_shifted_cosine_similarity,
    spectral_entropy_similarity,
    spectrum_only_descriptors,
)


def test_peak_matching_is_one_to_one_and_prefers_strongest_pair() -> None:
    matches = match_peaks_one_to_one(
        [100.000, 100.015],
        [100.010],
        query_intensity=[0.2, 1.0],
        reference_intensity=[1.0],
        tolerance_da=0.02,
    )
    assert len(matches) == 1
    assert matches[0].query_index == 1
    assert matches[0].reference_index == 0


def test_peak_matching_is_invariant_to_input_order() -> None:
    first = match_peaks_one_to_one(
        [100.0, 50.0],
        [50.005, 100.005],
        query_intensity=[0.5, 1.0],
        reference_intensity=[1.0, 0.5],
    )
    second = match_peaks_one_to_one(
        [50.0, 100.0],
        [100.005, 50.005],
        query_intensity=[1.0, 0.5],
        reference_intensity=[0.5, 1.0],
    )
    assert [(m.query_mz, m.reference_mz) for m in first] == [
        (m.query_mz, m.reference_mz) for m in second
    ]


def test_cosine_identical_is_one_and_reports_coverage() -> None:
    result = cosine_similarity([50.0, 75.0], [4.0, 1.0], [50.0, 75.0], [4.0, 1.0])
    assert result.score == pytest.approx(1.0)
    assert result.matched_peaks == 2
    assert result.query_coverage == pytest.approx(1.0)
    assert result.reference_coverage == pytest.approx(1.0)


def test_modified_cosine_unites_direct_and_precursor_shifted_matches() -> None:
    direct = cosine_similarity([50.0, 110.0], [1.0, 1.0], [50.0, 100.0], [1.0, 1.0])
    shifted = precursor_shifted_cosine_similarity(
        [50.0, 110.0],
        [1.0, 1.0],
        [50.0, 100.0],
        [1.0, 1.0],
        query_precursor_mz=210.0,
        reference_precursor_mz=200.0,
    )
    modified = modified_cosine_similarity(
        [50.0, 110.0],
        [1.0, 1.0],
        [50.0, 100.0],
        [1.0, 1.0],
        query_precursor_mz=210.0,
        reference_precursor_mz=200.0,
    )
    assert direct.score == pytest.approx(0.5)
    assert shifted.score == pytest.approx(0.5)
    assert modified.score == pytest.approx(1.0)
    assert {match.mode for match in modified.matches} == {"direct", "shifted"}


def test_entropy_similarity_uses_unmatched_peaks() -> None:
    identical = spectral_entropy_similarity([50.0], [1.0], [50.0], [1.0])
    disjoint = spectral_entropy_similarity([50.0], [1.0], [80.0], [1.0])
    assert identical.score == pytest.approx(1.0)
    assert disjoint.score == pytest.approx(0.0, abs=1e-12)


def test_common_neutral_losses_use_exact_monoisotopic_masses() -> None:
    losses = {loss.name: loss.exact_mass for loss in COMMON_NEUTRAL_LOSSES}
    assert losses["H2O"] == pytest.approx(18.01056468403, abs=1e-10)
    assert losses["NH3"] == pytest.approx(17.02654910112, abs=1e-10)
    assert losses["CO2"] == pytest.approx(43.98982923914, abs=1e-10)
    assert losses["CH3OH"] == pytest.approx(32.02621474849, abs=1e-10)


def test_neutral_loss_detection_and_fingerprint() -> None:
    water = next(loss for loss in COMMON_NEUTRAL_LOSSES if loss.name == "H2O")
    hits = detect_neutral_losses(
        200.0,
        [200.0 - water.exact_mass, 150.0],
        [0.8, 0.2],
        tolerance_da=1e-6,
    )
    assert [hit.name for hit in hits] == ["H2O"]
    assert hits[0].mass_error_da == pytest.approx(0.0, abs=1e-12)
    fingerprint = neutral_loss_fingerprint(
        200.0,
        [200.0 - water.exact_mass],
        [0.8],
        mode="binary",
        tolerance_da=1e-6,
    )
    assert fingerprint.sum() == 1.0


def test_formula_compatibility_is_candidate_specific_but_only_necessary() -> None:
    compatible = formula_compatible_neutral_losses("C6H12O6")
    assert compatible["H2O"]
    assert compatible["hexose"]
    assert not compatible["H3PO4"]
    hits = detect_neutral_losses(200.0, [181.98943531597], [1.0], tolerance_da=1e-6)
    assert neutral_loss_candidate_compatibility("C6H12O6", hits) == 1.0
    assert neutral_loss_candidate_compatibility("C6H10", hits) == 0.0


def test_neutral_loss_similarity_matches_losses_not_fragment_mz() -> None:
    result = neutral_loss_similarity(
        [180.0, 150.0],
        [1.0, 0.5],
        [80.0, 50.0],
        [1.0, 0.5],
        query_precursor_mz=200.0,
        reference_precursor_mz=100.0,
    )
    assert result.score == pytest.approx(1.0)
    assert result.matched_peaks == 2
    assert all(match.mode == "neutral_loss" for match in result.matches)


def test_spectrum_only_descriptors_are_explicitly_namespaced() -> None:
    descriptors = spectrum_only_descriptors([50.0, 150.0], [1.0, 1.0], precursor_mz=200.0)
    assert descriptors["spectrum_peak_count"] == 2.0
    assert descriptors["spectrum_low_mass_fraction"] == pytest.approx(0.5)
    assert all(name.startswith("spectrum_") for name in descriptors)


def test_candidate_spectrum_compatibility_emits_candidate_features() -> None:
    evidence = candidate_spectrum_compatibility(
        [50.0, 75.0],
        [1.0, 0.5],
        [50.005, 75.005],
        [1.0, 0.5],
        query_precursor_mz=200.0,
        candidate_precursor_mz=200.0,
        candidate_formula="C6H12O6",
        query_collision_energy=20.0,
        candidate_collision_energy=30.0,
        query_adduct="[M+H]+",
        candidate_adduct="[M+H]+",
    )
    features = evidence.as_features()
    assert features["fragment_modified_cosine"] == pytest.approx(1.0)
    assert features["fragment_matched_peaks"] == 2.0
    assert features["collision_energy_delta"] == 10.0
    assert features["same_adduct"] == 1.0


def test_balanced_weights_do_not_count_replicated_adduct_as_independent() -> None:
    weights = balanced_acquisition_weights(
        ["[M+H]+", "[M+H]+", "[M-H]-"],
        [10.0, 10.0, 20.0],
    )
    assert weights.sum() == pytest.approx(1.0)
    assert weights[:2].sum() == pytest.approx(weights[2])


def test_multi_spectrum_aggregation_methods() -> None:
    scores = np.asarray([[0.9, 0.1], [0.3, 0.8]])
    assert aggregate_candidate_scores(scores, method="mean") == pytest.approx([0.6, 0.45])
    assert aggregate_candidate_scores(scores, method="max") == pytest.approx([0.9, 0.8])
    assert aggregate_candidate_scores(
        scores, method="weighted", weights=[0.75, 0.25]
    ) == pytest.approx([0.75, 0.275])
    confidence = aggregate_candidate_scores(
        scores,
        method="confidence_weighted",
        weights=[1.0, 1.0],
        confidence=[1.0, 0.0],
    )
    assert confidence == pytest.approx([0.9, 0.1])
    rrf = aggregate_candidate_scores(scores, method="rrf", rrf_k=10.0)
    assert np.isfinite(rrf).all()
    assert rrf[0] == pytest.approx(rrf[1])


def test_invalid_peak_arrays_fail_closed() -> None:
    with pytest.raises(ValueError, match="aligned"):
        cosine_similarity([10.0], [1.0, 2.0], [10.0], [1.0])
    with pytest.raises(ValueError, match="finite"):
        detect_neutral_losses(100.0, [np.nan], [1.0])
    with pytest.raises(ValueError, match="tolerance"):
        match_peaks_one_to_one([], [], tolerance_da=None, tolerance_ppm=None)
    with pytest.raises(ValueError, match="mode"):
        neutral_loss_fingerprint(100.0, [], [], mode="unknown")
