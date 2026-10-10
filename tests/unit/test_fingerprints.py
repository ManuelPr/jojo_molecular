from __future__ import annotations

import numpy as np
import pytest

from casmi26.fingerprints import (
    FingerprintKNNBaseline,
    batch_processed_spectra,
    candidate_compatibility_scores,
    fingerprint_batch,
    fingerprint_metrics,
    molecular_fingerprint,
    rank_candidate_fingerprints,
)
from casmi26.goal3_contracts import FingerprintSpec
from casmi26.schemas import ProcessedSpectrum


def _spectrum(
    spectrum_id: str,
    mz: list[float],
    intensity: list[float],
    *,
    adduct: str = "[M+H]+",
    ion_mode: str = "positive",
) -> ProcessedSpectrum:
    return ProcessedSpectrum(
        spectrum_id=spectrum_id,
        molecule_id=spectrum_id,
        mz=np.asarray(mz, dtype=np.float32),
        intensity=np.asarray(intensity, dtype=np.float32),
        precursor_mz=201.0,
        neutral_mass=199.9927,
        adduct=adduct,
        ion_mode=ion_mode,
        collision_energy_ev=(10.0, 30.0, float("nan")),
        instrument="fixture",
        quality={},
    )


def test_morgan_and_maccs_are_canonical_and_have_declared_shape() -> None:
    morgan = molecular_fingerprint("OCC", FingerprintSpec(n_bits=128))
    reordered = molecular_fingerprint("CCO", FingerprintSpec(n_bits=128))
    maccs = molecular_fingerprint("CCO", FingerprintSpec(kind="maccs", n_bits=167))

    assert morgan.shape == (128,)
    assert maccs.shape == (167,)
    assert morgan.dtype == np.uint8
    np.testing.assert_array_equal(morgan, reordered)
    assert set(np.unique(maccs)).issubset({0, 1})


def test_fingerprint_batch_preserves_order_and_rejects_bad_smiles() -> None:
    spec = FingerprintSpec(n_bits=64)
    batch = fingerprint_batch(["CC", "CCC", "CC"], spec)
    assert batch.shape == (3, 64)
    np.testing.assert_array_equal(batch[0], batch[2])
    assert not np.array_equal(batch[0], batch[1])
    with pytest.raises(ValueError, match="invalid SMILES"):
        molecular_fingerprint("not a molecule", spec)


def test_spectrum_batch_is_deterministic_padded_and_selects_strong_peaks() -> None:
    spectrum = _spectrum(
        "s1",
        [80.0, 20.0, 40.0, 60.0, np.nan],
        [0.8, 0.1, 0.8, 0.5, 1.0],
    )
    unknown = _spectrum("s2", [], [], adduct="unknown", ion_mode="mystery")

    first = batch_processed_spectra([spectrum, unknown], max_peaks=3)
    second = batch_processed_spectra([spectrum, unknown], max_peaks=3)

    np.testing.assert_array_equal(first.mz, second.mz)
    np.testing.assert_allclose(first.mz[0], [40.0, 60.0, 80.0])
    np.testing.assert_allclose(first.neutral_loss[0], [161.0, 141.0, 121.0])
    np.testing.assert_array_equal(first.peak_mask[0], [True, True, True])
    np.testing.assert_array_equal(first.peak_mask[1], [False, False, False])
    assert first.collision_energy.tolist() == [20.0, 20.0]
    assert first.adduct_index[0] > 0 and first.adduct_index[1] == 0
    assert first.ion_mode_index[0] > 0 and first.ion_mode_index[1] == 0
    assert first.mz.dtype == np.float32


def test_spectrum_batch_validates_shapes_and_max_peaks() -> None:
    bad = _spectrum("bad", [10.0], [0.1, 0.2])
    with pytest.raises(ValueError, match="Misaligned"):
        batch_processed_spectra([bad])
    with pytest.raises(ValueError, match="positive"):
        batch_processed_spectra([], max_peaks=0)


def test_knn_baseline_is_deterministic_and_recovers_training_examples() -> None:
    spectra = [
        _spectrum("a", [10.0, 50.0], [1.0, 0.2]),
        _spectrum("b", [90.0, 120.0], [0.3, 1.0], ion_mode="negative"),
    ]
    targets = np.asarray([[1, 0, 1], [0, 1, 0]], dtype=np.float32)
    model = FingerprintKNNBaseline(n_neighbors=1, bin_width=1.0).fit(spectra, targets)

    first = model.predict_proba(spectra)
    second = model.predict_proba(spectra)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_allclose(first, targets, atol=1e-5)


def test_metrics_and_candidate_compatibility_rank_the_exact_bits_first() -> None:
    targets = np.asarray([[1, 0, 1, 0], [0, 1, 0, 1]], dtype=np.uint8)
    probabilities = targets * 0.8 + 0.1
    metrics = fingerprint_metrics(probabilities, targets)
    assert metrics["micro_f1"] == pytest.approx(1.0)
    assert metrics["mean_sample_jaccard"] == pytest.approx(1.0)

    prediction = np.asarray([4.0, -4.0, 4.0, -4.0])
    candidates = np.asarray([[1, 0, 1, 0], [0, 1, 0, 1], [1, 1, 0, 0]])
    likelihood = candidate_compatibility_scores(prediction, candidates)
    tanimoto = candidate_compatibility_scores(prediction, candidates, method="soft_tanimoto")
    assert int(np.argmax(likelihood)) == 0
    assert int(np.argmax(tanimoto)) == 0

    ranked = rank_candidate_fingerprints(
        prediction,
        {"wrong": candidates[1], "right": candidates[0]},
    )
    assert ranked[0][0] == "right"


def test_fingerprint_metrics_reject_nonfinite_predictions() -> None:
    with pytest.raises(ValueError, match="finite"):
        fingerprint_metrics(np.asarray([[np.nan]]), np.asarray([[1]]))

