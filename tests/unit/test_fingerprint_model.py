from __future__ import annotations

import numpy as np
import pytest

from casmi26.fingerprint_model import (
    CompactPeakFingerprintConfig,
    CompactPeakFingerprintEncoder,
    PeakFingerprintConfig,
    PeakFingerprintEncoder,
    WeightedFingerprintBCELoss,
    compact_tiny_overfit_smoke,
    estimate_positive_weights,
    require_torch,
    spectrum_batch_to_torch,
    torch_available,
)
from casmi26.goal3_contracts import SpectrumBatch


TORCH_AVAILABLE = torch_available()


def _batch() -> SpectrumBatch:
    return SpectrumBatch(
        mz=np.asarray([[10.0, 30.0, 0.0], [20.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float32),
        intensity=np.asarray([[1.0, 0.5, 0.0], [0.7, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float32),
        neutral_loss=np.asarray([[190.0, 170.0, 0.0], [180.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float32),
        peak_mask=np.asarray([[True, True, False], [True, False, False], [False, False, False]]),
        precursor_mass=np.asarray([199.0, 199.0, 199.0], dtype=np.float32),
        collision_energy=np.asarray([20.0, 30.0, 0.0], dtype=np.float32),
        adduct_index=np.asarray([1, 1, 0], dtype=np.int64),
        ion_mode_index=np.asarray([1, 2, 0], dtype=np.int64),
    )


def _config() -> PeakFingerprintConfig:
    return PeakFingerprintConfig(
        n_bits=8,
        d_model=16,
        n_heads=4,
        n_layers=1,
        feedforward_dim=32,
        dropout=0.0,
        fourier_features=2,
        metadata_embedding_dim=4,
    )


def _compact_config() -> CompactPeakFingerprintConfig:
    return CompactPeakFingerprintConfig(
        n_bits=8,
        d_model=16,
        dropout=0.0,
        fourier_features=2,
        metadata_embedding_dim=4,
    )


def test_optional_torch_has_diagnostic_error_when_missing() -> None:
    if TORCH_AVAILABLE:
        require_torch()
    else:
        with pytest.raises(ImportError, match="PyTorch is required"):
            PeakFingerprintEncoder()
        with pytest.raises(ImportError, match="PyTorch is required"):
            CompactPeakFingerprintEncoder()


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch is not installed")
def test_forward_shape_masking_and_determinism() -> None:
    import torch

    torch.manual_seed(7)
    model = PeakFingerprintEncoder(_config()).eval()
    tensors = spectrum_batch_to_torch(_batch())
    with torch.inference_mode():
        first = model(**tensors)
        second = model.forward_batch(_batch())
    assert first.shape == (3, 8)
    assert torch.isfinite(first).all()
    torch.testing.assert_close(first, second)

    # Padding contents are ignored wherever peak_mask is false.
    tensors["mz"][0, 2] = 999.0
    tensors["intensity"][0, 2] = 999.0
    tensors["neutral_loss"][0, 2] = 999.0
    with torch.inference_mode():
        changed_padding = model(**tensors)
    torch.testing.assert_close(first, changed_padding)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch is not installed")
def test_backward_optimizer_step_and_weighted_loss() -> None:
    import torch

    torch.manual_seed(11)
    model = PeakFingerprintEncoder(_config())
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    targets = torch.tensor(
        [[1, 0, 1, 0, 1, 0, 0, 1], [0, 1, 0, 1, 0, 1, 1, 0], [1, 1, 0, 0, 1, 0, 1, 0]],
        dtype=torch.float32,
    )
    weights = estimate_positive_weights(targets)
    criterion = WeightedFingerprintBCELoss(weights)
    before = model.output_head[-1].weight.detach().clone()
    loss = criterion(model(**spectrum_batch_to_torch(_batch())), targets)
    assert torch.isfinite(loss)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    assert all(parameter.grad is None or torch.isfinite(parameter.grad).all() for parameter in model.parameters())
    optimizer.step()
    assert not torch.equal(before, model.output_head[-1].weight.detach())


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch is not installed")
def test_model_and_loss_reject_nan_and_inf() -> None:
    import torch

    model = PeakFingerprintEncoder(_config())
    tensors = spectrum_batch_to_torch(_batch())
    tensors["mz"][0, 0] = float("nan")
    with pytest.raises(ValueError, match="NaN or infinite"):
        model(**tensors)

    criterion = WeightedFingerprintBCELoss()
    with pytest.raises(ValueError, match="finite"):
        criterion(torch.tensor([[float("inf")]]), torch.tensor([[1.0]]))


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch is not installed")
def test_tiny_dataset_can_be_overfit_on_cpu() -> None:
    import torch

    torch.manual_seed(23)
    model = PeakFingerprintEncoder(_config())
    tensors = spectrum_batch_to_torch(_batch())
    targets = torch.tensor(
        [[1, 0, 1, 0, 1, 0, 0, 1], [0, 1, 0, 1, 0, 1, 1, 0], [1, 1, 0, 0, 1, 0, 1, 0]],
        dtype=torch.float32,
    )
    criterion = WeightedFingerprintBCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=2e-2)
    with torch.no_grad():
        initial = float(criterion(model(**tensors), targets))
    for _ in range(50):
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(**tensors), targets)
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        final = float(criterion(model(**tensors), targets))
    assert final < initial * 0.55


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch is not installed")
def test_compact_forward_masking_backward_and_optimizer_step() -> None:
    import torch

    torch.manual_seed(31)
    model = CompactPeakFingerprintEncoder(_compact_config())
    tensors = spectrum_batch_to_torch(_batch())
    targets = torch.tensor(
        [[1, 0, 1, 0, 1, 0, 0, 1], [0, 1, 0, 1, 0, 1, 1, 0], [1, 1, 0, 0, 1, 0, 1, 0]],
        dtype=torch.float32,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    criterion = WeightedFingerprintBCELoss()
    before = model.output_head[-1].weight.detach().clone()
    logits = model(**tensors)
    assert logits.shape == (3, 8)
    assert torch.isfinite(logits).all()
    loss = criterion(logits, targets)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    assert all(parameter.grad is None or torch.isfinite(parameter.grad).all() for parameter in model.parameters())
    optimizer.step()
    assert not torch.equal(before, model.output_head[-1].weight.detach())

    model.eval()
    with torch.inference_mode():
        reference = model(**spectrum_batch_to_torch(_batch()))
        changed = spectrum_batch_to_torch(_batch())
        changed["mz"][0, 2] = 999.0
        changed["intensity"][0, 2] = 999.0
        changed["neutral_loss"][0, 2] = 999.0
        padded = model(**changed)
    torch.testing.assert_close(reference, padded)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch is not installed")
def test_compact_tiny_dataset_can_be_overfit_on_cpu() -> None:
    report = compact_tiny_overfit_smoke(device="cpu")
    assert report["loss_ratio"] < 0.55
    assert report["parameter_count"] > 0
