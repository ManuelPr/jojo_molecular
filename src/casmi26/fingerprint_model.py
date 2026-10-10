from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .fingerprints import DEFAULT_ADDUCT_VOCAB, DEFAULT_ION_MODE_VOCAB
from .goal3_contracts import SpectrumBatch


try:
    import torch
    from torch import nn
    from torch.nn import functional as F
except (ImportError, OSError) as exc:  # OSError covers broken optional CUDA wheels.
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: BaseException | None = exc
else:
    _TORCH_IMPORT_ERROR = None


def torch_available() -> bool:
    return torch is not None


def require_torch() -> None:
    if torch is None:
        detail = f" ({_TORCH_IMPORT_ERROR})" if _TORCH_IMPORT_ERROR is not None else ""
        raise ImportError(
            "PyTorch is required for casmi26.fingerprint_model neural components; "
            "install a torch build compatible with the target CPU/CUDA environment" + detail
        ) from _TORCH_IMPORT_ERROR


@dataclass(frozen=True, slots=True)
class PeakFingerprintConfig:
    n_bits: int = 512
    d_model: int = 128
    n_heads: int = 4
    n_layers: int = 3
    feedforward_dim: int = 256
    dropout: float = 0.1
    fourier_features: int = 12
    metadata_embedding_dim: int = 16
    adduct_vocab_size: int = len(DEFAULT_ADDUCT_VOCAB) + 1
    ion_mode_vocab_size: int = len(DEFAULT_ION_MODE_VOCAB) + 1

    def __post_init__(self) -> None:
        if self.n_bits <= 0:
            raise ValueError("n_bits must be positive")
        if self.d_model <= 0 or self.n_heads <= 0 or self.d_model % self.n_heads:
            raise ValueError("d_model must be positive and divisible by n_heads")
        if self.n_layers <= 0 or self.feedforward_dim <= 0:
            raise ValueError("n_layers and feedforward_dim must be positive")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if self.fourier_features <= 0 or self.metadata_embedding_dim <= 0:
            raise ValueError("feature and embedding dimensions must be positive")
        if self.adduct_vocab_size <= 0 or self.ion_mode_vocab_size <= 0:
            raise ValueError("categorical vocabulary sizes must be positive")


@dataclass(frozen=True, slots=True)
class CompactPeakFingerprintConfig:
    """Configuration for the linear-in-peaks non-attention encoder."""

    n_bits: int = 512
    d_model: int = 96
    dropout: float = 0.1
    fourier_features: int = 12
    metadata_embedding_dim: int = 12
    adduct_vocab_size: int = len(DEFAULT_ADDUCT_VOCAB) + 1
    ion_mode_vocab_size: int = len(DEFAULT_ION_MODE_VOCAB) + 1

    def __post_init__(self) -> None:
        if self.n_bits <= 0 or self.d_model <= 0:
            raise ValueError("n_bits and d_model must be positive")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if self.fourier_features <= 0 or self.metadata_embedding_dim <= 0:
            raise ValueError("feature and embedding dimensions must be positive")
        if self.adduct_vocab_size <= 0 or self.ion_mode_vocab_size <= 0:
            raise ValueError("categorical vocabulary sizes must be positive")


def spectrum_batch_to_torch(
    batch: SpectrumBatch,
    *,
    device: Any = None,
) -> dict[str, Any]:
    """Convert the shared NumPy contract to model-ready tensors."""

    require_torch()
    return {
        "mz": torch.as_tensor(batch.mz, dtype=torch.float32, device=device),
        "intensity": torch.as_tensor(batch.intensity, dtype=torch.float32, device=device),
        "neutral_loss": torch.as_tensor(batch.neutral_loss, dtype=torch.float32, device=device),
        "peak_mask": torch.as_tensor(batch.peak_mask, dtype=torch.bool, device=device),
        "precursor_mass": torch.as_tensor(batch.precursor_mass, dtype=torch.float32, device=device),
        "collision_energy": torch.as_tensor(batch.collision_energy, dtype=torch.float32, device=device),
        "adduct_index": torch.as_tensor(batch.adduct_index, dtype=torch.long, device=device),
        "ion_mode_index": torch.as_tensor(batch.ion_mode_index, dtype=torch.long, device=device),
    }


if torch is not None:

    class _FourierPeakEmbedding(nn.Module):
        def __init__(self, config: PeakFingerprintConfig):
            super().__init__()
            # Wavelengths from roughly 0.02 to 200 Da after the 1/1000 scaling.
            frequencies = torch.logspace(0.0, 4.0, config.fourier_features)
            self.register_buffer("frequencies", frequencies, persistent=True)
            input_dim = 3 + 4 * config.fourier_features
            self.project = nn.Sequential(
                nn.Linear(input_dim, config.d_model),
                nn.GELU(),
                nn.LayerNorm(config.d_model),
            )

        def forward(self, mz: Any, intensity: Any, neutral_loss: Any) -> Any:
            mz_scaled = mz / 1_000.0
            loss_scaled = neutral_loss / 1_000.0
            mz_phase = 2.0 * torch.pi * mz_scaled.unsqueeze(-1) * self.frequencies
            loss_phase = 2.0 * torch.pi * loss_scaled.unsqueeze(-1) * self.frequencies
            features = torch.cat(
                (
                    mz_scaled.unsqueeze(-1),
                    intensity.unsqueeze(-1),
                    loss_scaled.unsqueeze(-1),
                    torch.sin(mz_phase),
                    torch.cos(mz_phase),
                    torch.sin(loss_phase),
                    torch.cos(loss_phase),
                ),
                dim=-1,
            )
            return self.project(features)


    class PeakFingerprintEncoder(nn.Module):
        """Compact masked peak Transformer for fingerprint-logit prediction.

        The default model is small enough for batched T4 inference. It combines
        masked attention pooling and masked mean pooling so padding never enters
        a spectrum representation, while precursor/adduct/acquisition metadata
        is injected after peak aggregation.
        """

        def __init__(self, config: PeakFingerprintConfig = PeakFingerprintConfig()):
            super().__init__()
            self.config = config
            self.peak_embedding = _FourierPeakEmbedding(config)
            layer = nn.TransformerEncoderLayer(
                d_model=config.d_model,
                nhead=config.n_heads,
                dim_feedforward=config.feedforward_dim,
                dropout=config.dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(
                layer,
                num_layers=config.n_layers,
                norm=nn.LayerNorm(config.d_model),
                enable_nested_tensor=False,
            )
            self.attention_pool = nn.Linear(config.d_model, 1)
            self.adduct_embedding = nn.Embedding(
                config.adduct_vocab_size,
                config.metadata_embedding_dim,
            )
            self.ion_mode_embedding = nn.Embedding(
                config.ion_mode_vocab_size,
                config.metadata_embedding_dim,
            )
            metadata_dim = 2 + 2 * config.metadata_embedding_dim
            self.metadata_projection = nn.Sequential(
                nn.Linear(metadata_dim, config.d_model),
                nn.GELU(),
                nn.LayerNorm(config.d_model),
            )
            self.output_head = nn.Sequential(
                nn.Linear(3 * config.d_model, config.d_model),
                nn.GELU(),
                nn.Dropout(config.dropout),
                nn.Linear(config.d_model, config.n_bits),
            )

        @staticmethod
        def _validate_shapes(
            mz: Any,
            intensity: Any,
            neutral_loss: Any,
            peak_mask: Any,
            precursor_mass: Any,
            collision_energy: Any,
            adduct_index: Any,
            ion_mode_index: Any,
        ) -> None:
            if mz.ndim != 2:
                raise ValueError("Peak tensors must have shape [batch, peaks]")
            if mz.shape[1] == 0:
                raise ValueError("Peak tensors must contain at least one padded position")
            for name, value in (
                ("intensity", intensity),
                ("neutral_loss", neutral_loss),
                ("peak_mask", peak_mask),
            ):
                if value.shape != mz.shape:
                    raise ValueError(f"{name} must match mz shape")
            for name, value in (
                ("precursor_mass", precursor_mass),
                ("collision_energy", collision_energy),
                ("adduct_index", adduct_index),
                ("ion_mode_index", ion_mode_index),
            ):
                if value.shape != (mz.shape[0],):
                    raise ValueError(f"{name} must have shape [batch]")

        @staticmethod
        def _ensure_finite(name: str, value: Any) -> None:
            if not bool(torch.isfinite(value).all()):
                raise ValueError(f"{name} contains NaN or infinite values")

        def forward(
            self,
            mz: Any,
            intensity: Any,
            neutral_loss: Any,
            peak_mask: Any,
            precursor_mass: Any,
            collision_energy: Any,
            adduct_index: Any,
            ion_mode_index: Any,
        ) -> Any:
            self._validate_shapes(
                mz,
                intensity,
                neutral_loss,
                peak_mask,
                precursor_mass,
                collision_energy,
                adduct_index,
                ion_mode_index,
            )
            for name, value in (
                ("mz", mz),
                ("intensity", intensity),
                ("neutral_loss", neutral_loss),
                ("precursor_mass", precursor_mass),
                ("collision_energy", collision_energy),
            ):
                self._ensure_finite(name, value)
            if peak_mask.dtype != torch.bool:
                raise ValueError("peak_mask must have boolean dtype")
            if torch.any(adduct_index < 0) or torch.any(adduct_index >= self.config.adduct_vocab_size):
                raise ValueError("adduct_index is outside the configured vocabulary")
            if torch.any(ion_mode_index < 0) or torch.any(ion_mode_index >= self.config.ion_mode_vocab_size):
                raise ValueError("ion_mode_index is outside the configured vocabulary")

            peaks = self.peak_embedding(mz, intensity, neutral_loss)
            peaks = peaks.masked_fill(~peak_mask.unsqueeze(-1), 0.0)

            # Transformer attention cannot consume a row where every token is
            # padding. Expose one zero token internally, while retaining the
            # original mask for all pooling operations.
            safe_mask = peak_mask.clone()
            empty = ~safe_mask.any(dim=1)
            safe_mask[empty, 0] = True
            encoded = self.encoder(peaks, src_key_padding_mask=~safe_mask)
            encoded = encoded.masked_fill(~peak_mask.unsqueeze(-1), 0.0)

            counts = peak_mask.sum(dim=1, keepdim=True).clamp_min(1).to(encoded.dtype)
            mean_pool = encoded.sum(dim=1) / counts
            attention_logits = self.attention_pool(encoded).squeeze(-1)
            attention_logits = attention_logits.masked_fill(~safe_mask, -torch.inf)
            attention_weights = torch.softmax(attention_logits, dim=1)
            attention_weights = attention_weights * peak_mask.to(attention_weights.dtype)
            attention_weights = attention_weights / attention_weights.sum(
                dim=1,
                keepdim=True,
            ).clamp_min(1e-12)
            attention_pool = torch.sum(encoded * attention_weights.unsqueeze(-1), dim=1)

            metadata = torch.cat(
                (
                    (precursor_mass / 1_000.0).unsqueeze(-1),
                    (collision_energy / 100.0).unsqueeze(-1),
                    self.adduct_embedding(adduct_index),
                    self.ion_mode_embedding(ion_mode_index),
                ),
                dim=-1,
            )
            metadata = self.metadata_projection(metadata)
            logits = self.output_head(torch.cat((attention_pool, mean_pool, metadata), dim=-1))
            if not bool(torch.isfinite(logits).all()):
                raise FloatingPointError("PeakFingerprintEncoder produced non-finite logits")
            return logits

        def forward_batch(self, batch: SpectrumBatch, *, device: Any = None) -> Any:
            return self(**spectrum_batch_to_torch(batch, device=device))


    class CompactPeakFingerprintEncoder(nn.Module):
        """Linear-memory spectrum encoder with shared peak MLP and masked pooling.

        This is the inexpensive reference architecture. It has no peak-to-peak
        attention: every peak is encoded independently, then masked mean, max,
        and learned gated pooling capture complementary spectrum summaries.
        Runtime and activation memory therefore scale linearly with peak count.
        """

        def __init__(
            self,
            config: CompactPeakFingerprintConfig = CompactPeakFingerprintConfig(),
        ):
            super().__init__()
            self.config = config
            self.peak_embedding = _FourierPeakEmbedding(config)  # type: ignore[arg-type]
            self.peak_mlp = nn.Sequential(
                nn.Linear(config.d_model, config.d_model),
                nn.GELU(),
                nn.LayerNorm(config.d_model),
            )
            self.gate = nn.Linear(config.d_model, 1)
            self.adduct_embedding = nn.Embedding(
                config.adduct_vocab_size,
                config.metadata_embedding_dim,
            )
            self.ion_mode_embedding = nn.Embedding(
                config.ion_mode_vocab_size,
                config.metadata_embedding_dim,
            )
            metadata_dim = 2 + 2 * config.metadata_embedding_dim
            self.metadata_projection = nn.Sequential(
                nn.Linear(metadata_dim, config.d_model),
                nn.GELU(),
                nn.LayerNorm(config.d_model),
            )
            self.output_head = nn.Sequential(
                nn.Linear(4 * config.d_model, config.d_model),
                nn.GELU(),
                nn.Dropout(config.dropout),
                nn.Linear(config.d_model, config.n_bits),
            )

        def forward(
            self,
            mz: Any,
            intensity: Any,
            neutral_loss: Any,
            peak_mask: Any,
            precursor_mass: Any,
            collision_energy: Any,
            adduct_index: Any,
            ion_mode_index: Any,
        ) -> Any:
            PeakFingerprintEncoder._validate_shapes(
                mz,
                intensity,
                neutral_loss,
                peak_mask,
                precursor_mass,
                collision_energy,
                adduct_index,
                ion_mode_index,
            )
            for name, value in (
                ("mz", mz),
                ("intensity", intensity),
                ("neutral_loss", neutral_loss),
                ("precursor_mass", precursor_mass),
                ("collision_energy", collision_energy),
            ):
                PeakFingerprintEncoder._ensure_finite(name, value)
            if peak_mask.dtype != torch.bool:
                raise ValueError("peak_mask must have boolean dtype")
            if torch.any(adduct_index < 0) or torch.any(adduct_index >= self.config.adduct_vocab_size):
                raise ValueError("adduct_index is outside the configured vocabulary")
            if torch.any(ion_mode_index < 0) or torch.any(ion_mode_index >= self.config.ion_mode_vocab_size):
                raise ValueError("ion_mode_index is outside the configured vocabulary")

            encoded = self.peak_mlp(self.peak_embedding(mz, intensity, neutral_loss))
            encoded = encoded.masked_fill(~peak_mask.unsqueeze(-1), 0.0)
            mask_float = peak_mask.unsqueeze(-1).to(encoded.dtype)
            counts = mask_float.sum(dim=1).clamp_min(1.0)
            mean_pool = encoded.sum(dim=1) / counts

            max_values = encoded.masked_fill(~peak_mask.unsqueeze(-1), -torch.inf).amax(dim=1)
            empty = ~peak_mask.any(dim=1)
            max_pool = torch.where(empty.unsqueeze(-1), torch.zeros_like(max_values), max_values)

            gate_weights = torch.sigmoid(self.gate(encoded)) * mask_float
            gate_pool = (encoded * gate_weights).sum(dim=1) / gate_weights.sum(dim=1).clamp_min(1e-12)

            metadata = torch.cat(
                (
                    (precursor_mass / 1_000.0).unsqueeze(-1),
                    (collision_energy / 100.0).unsqueeze(-1),
                    self.adduct_embedding(adduct_index),
                    self.ion_mode_embedding(ion_mode_index),
                ),
                dim=-1,
            )
            metadata = self.metadata_projection(metadata)
            logits = self.output_head(
                torch.cat((mean_pool, max_pool, gate_pool, metadata), dim=-1)
            )
            if not bool(torch.isfinite(logits).all()):
                raise FloatingPointError("CompactPeakFingerprintEncoder produced non-finite logits")
            return logits

        def forward_batch(self, batch: SpectrumBatch, *, device: Any = None) -> Any:
            return self(**spectrum_batch_to_torch(batch, device=device))


    class WeightedFingerprintBCELoss(nn.Module):
        """BCE-with-logits with independent positive-class and per-bit weights."""

        def __init__(
            self,
            pos_weight: Any = None,
            bit_weight: Any = None,
            *,
            reduction: str = "mean",
        ):
            super().__init__()
            if reduction not in {"none", "mean", "sum"}:
                raise ValueError("reduction must be 'none', 'mean', or 'sum'")
            positive = None if pos_weight is None else torch.as_tensor(pos_weight, dtype=torch.float32)
            bits = None if bit_weight is None else torch.as_tensor(bit_weight, dtype=torch.float32)
            if positive is not None and (not bool(torch.isfinite(positive).all()) or torch.any(positive < 0)):
                raise ValueError("pos_weight must be finite and non-negative")
            if bits is not None and (not bool(torch.isfinite(bits).all()) or torch.any(bits < 0)):
                raise ValueError("bit_weight must be finite and non-negative")
            self.register_buffer("pos_weight", positive)
            self.register_buffer("bit_weight", bits)
            self.reduction = reduction

        def forward(self, logits: Any, targets: Any) -> Any:
            if logits.shape != targets.shape or logits.ndim != 2:
                raise ValueError("logits and targets must share shape [batch, bits]")
            if not bool(torch.isfinite(logits).all()) or not bool(torch.isfinite(targets).all()):
                raise ValueError("logits and targets must be finite")
            if torch.any((targets < 0.0) | (targets > 1.0)):
                raise ValueError("targets must lie in [0, 1]")
            loss = F.binary_cross_entropy_with_logits(
                logits,
                targets,
                pos_weight=self.pos_weight,
                reduction="none",
            )
            if self.bit_weight is not None:
                loss = loss * self.bit_weight
            if self.reduction == "mean":
                return loss.mean()
            if self.reduction == "sum":
                return loss.sum()
            return loss


    def estimate_positive_weights(targets: Any, *, max_weight: float = 100.0) -> Any:
        """Estimate neg/pos weights per bit, safely handling constant bits."""

        values = torch.as_tensor(targets, dtype=torch.float32)
        if values.ndim != 2 or values.shape[0] == 0:
            raise ValueError("targets must be a non-empty [samples, bits] tensor")
        if not bool(torch.isfinite(values).all()) or torch.any((values < 0.0) | (values > 1.0)):
            raise ValueError("targets must be finite values in [0, 1]")
        if max_weight <= 0.0:
            raise ValueError("max_weight must be positive")
        positives = values.sum(dim=0)
        negatives = values.shape[0] - positives
        weights = negatives / positives.clamp_min(1.0)
        return weights.clamp(min=1e-3, max=max_weight)


else:

    class PeakFingerprintEncoder:  # type: ignore[no-redef]
        def __init__(self, *_: Any, **__: Any):
            require_torch()


    class WeightedFingerprintBCELoss:  # type: ignore[no-redef]
        def __init__(self, *_: Any, **__: Any):
            require_torch()


    class CompactPeakFingerprintEncoder:  # type: ignore[no-redef]
        def __init__(self, *_: Any, **__: Any):
            require_torch()


    def estimate_positive_weights(*_: Any, **__: Any) -> Any:
        require_torch()


FingerprintModel = PeakFingerprintEncoder
PeakTransformerFingerprintModel = PeakFingerprintEncoder
CompactFingerprintModel = CompactPeakFingerprintEncoder


def compact_tiny_overfit_smoke(
    *,
    device: str = "cpu",
    steps: int = 50,
    seed: int = 37,
) -> dict[str, float | int | str]:
    """Exercise compact-model forward/backward and memorization on three spectra."""

    require_torch()
    if steps <= 0:
        raise ValueError("steps must be positive")
    torch.manual_seed(seed)
    config = CompactPeakFingerprintConfig(
        n_bits=8,
        d_model=16,
        dropout=0.0,
        fourier_features=2,
        metadata_embedding_dim=4,
    )
    model = CompactPeakFingerprintEncoder(config).to(device)
    tensors = {
        "mz": torch.tensor(
            [[10.0, 30.0, 0.0], [20.0, 0.0, 0.0], [40.0, 55.0, 70.0]],
            device=device,
        ),
        "intensity": torch.tensor(
            [[1.0, 0.5, 0.0], [0.7, 0.0, 0.0], [0.2, 0.6, 1.0]],
            device=device,
        ),
        "neutral_loss": torch.tensor(
            [[190.0, 170.0, 0.0], [180.0, 0.0, 0.0], [160.0, 145.0, 130.0]],
            device=device,
        ),
        "peak_mask": torch.tensor(
            [[True, True, False], [True, False, False], [True, True, True]],
            device=device,
        ),
        "precursor_mass": torch.tensor([199.0, 199.0, 199.0], device=device),
        "collision_energy": torch.tensor([20.0, 30.0, 40.0], device=device),
        "adduct_index": torch.tensor([1, 1, 1], device=device),
        "ion_mode_index": torch.tensor([1, 1, 1], device=device),
    }
    targets = torch.tensor(
        [
            [1, 0, 1, 0, 1, 0, 0, 1],
            [0, 1, 0, 1, 0, 1, 1, 0],
            [1, 1, 0, 0, 1, 0, 1, 0],
        ],
        dtype=torch.float32,
        device=device,
    )
    criterion = WeightedFingerprintBCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=2e-2)
    with torch.no_grad():
        initial = float(criterion(model(**tensors), targets).cpu())
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(**tensors), targets)
        loss.backward()
        if any(
            parameter.grad is not None
            and not bool(torch.isfinite(parameter.grad).all())
            for parameter in model.parameters()
        ):
            raise FloatingPointError("Tiny-overfit smoke produced a non-finite gradient")
        optimizer.step()
    with torch.no_grad():
        final = float(criterion(model(**tensors), targets).cpu())
    ratio = final / initial
    if not ratio < 0.55:
        raise AssertionError(
            f"Compact encoder did not overfit the tiny batch: loss ratio={ratio:.4f}"
        )
    return {
        "device": device,
        "seed": seed,
        "steps": steps,
        "parameter_count": int(sum(parameter.numel() for parameter in model.parameters())),
        "initial_loss": initial,
        "final_loss": final,
        "loss_ratio": ratio,
    }
