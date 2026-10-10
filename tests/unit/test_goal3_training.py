from __future__ import annotations

import numpy as np
import pytest

from casmi26.fingerprint_model import torch_available
from casmi26.goal3_training import (
    FingerprintTrainingConfig,
    deterministic_group_folds,
    oof_fingerprint_predictions,
    train_fingerprint_predictor,
)
from casmi26.schemas import ProcessedSpectrum


def _spectrum(index: int) -> ProcessedSpectrum:
    return ProcessedSpectrum(
        spectrum_id=f"s{index}",
        molecule_id=f"g{index // 2}",
        mz=np.asarray([10.0 + index, 30.0 + index], dtype=np.float32),
        intensity=np.asarray([1.0, 0.5], dtype=np.float32),
        precursor_mz=201.0 + index,
        neutral_mass=200.0 + index,
        adduct="[M+H]+",
        ion_mode="positive",
        collision_energy_ev=(20.0,),
        instrument="fixture",
        quality={},
    )


def test_deterministic_group_folds_keep_groups_intact() -> None:
    groups = ["a", "a", "b", "b", "c", "d"]
    first = deterministic_group_folds(groups, n_folds=2, seed=7)
    second = deterministic_group_folds(groups, n_folds=2, seed=7)
    assert first == second
    assert set(first) == {"a", "b", "c", "d"}
    assert set(first.values()) == {0, 1}


def test_training_config_rejects_invalid_budget() -> None:
    with pytest.raises(ValueError, match="positive"):
        FingerprintTrainingConfig(epochs=0)


@pytest.mark.skipif(not torch_available(), reason="PyTorch is not installed")
def test_train_checkpoint_and_oof_are_finite(tmp_path) -> None:
    spectra = [_spectrum(index) for index in range(8)]
    targets = np.asarray(
        [[(index + bit) % 2 for bit in range(8)] for index in range(8)],
        dtype=np.float32,
    )
    config = FingerprintTrainingConfig(
        n_bits=8,
        max_peaks=4,
        batch_size=4,
        epochs=2,
        patience=2,
        compact_d_model=16,
        mixed_precision=False,
    )
    checkpoint = tmp_path / "model.pt"
    _, report = train_fingerprint_predictor(
        spectra[:6],
        targets[:6],
        config=config,
        validation_spectra=spectra[6:],
        validation_targets=targets[6:],
        device="cpu",
        checkpoint_path=checkpoint,
    )
    assert checkpoint.is_file()
    assert report["parameter_count"] > 0
    result = oof_fingerprint_predictions(
        spectra[:6],
        targets[:6],
        [item.molecule_id for item in spectra[:6]],
        spectra[6:],
        config=config,
        n_folds=3,
        device="cpu",
        checkpoint_dir=tmp_path / "oof",
    )
    assert result.oof_probabilities.shape == (6, 8)
    assert result.validation_probabilities.shape == (2, 8)
    assert np.isfinite(result.oof_probabilities).all()
