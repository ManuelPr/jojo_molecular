from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import random
import time
from typing import Any, Literal, Sequence

import numpy as np

from .fingerprint_model import (
    CompactPeakFingerprintConfig,
    CompactPeakFingerprintEncoder,
    PeakFingerprintConfig,
    PeakFingerprintEncoder,
    WeightedFingerprintBCELoss,
    estimate_positive_weights,
    require_torch,
    spectrum_batch_to_torch,
)
from .fingerprints import batch_processed_spectra, fingerprint_metrics
from .schemas import ProcessedSpectrum


@dataclass(frozen=True, slots=True)
class FingerprintTrainingConfig:
    model_kind: Literal["compact", "transformer"] = "compact"
    n_bits: int = 512
    max_peaks: int = 256
    batch_size: int = 16
    epochs: int = 12
    learning_rate: float = 2e-3
    weight_decay: float = 1e-4
    patience: int = 4
    seed: int = 2026
    mixed_precision: bool = True
    compact_d_model: int = 96
    transformer_d_model: int = 128
    transformer_layers: int = 3

    def __post_init__(self) -> None:
        if self.n_bits <= 0 or self.max_peaks <= 0 or self.batch_size <= 0:
            raise ValueError("Fingerprint dimensions and batch size must be positive")
        if self.epochs <= 0 or self.patience <= 0:
            raise ValueError("epochs and patience must be positive")
        if self.learning_rate <= 0 or self.weight_decay < 0:
            raise ValueError("Invalid optimizer configuration")


@dataclass(frozen=True, slots=True)
class OOFFingerprintResult:
    oof_probabilities: np.ndarray
    validation_probabilities: np.ndarray
    fold_reports: tuple[dict[str, Any], ...]
    final_report: dict[str, Any]
    fold_by_group: dict[str, int]


def deterministic_group_folds(
    group_ids: Sequence[str],
    *,
    n_folds: int,
    seed: int,
) -> dict[str, int]:
    unique = sorted(set(str(value) for value in group_ids))
    if n_folds < 2 or n_folds > len(unique):
        raise ValueError("n_folds must be between two and the number of groups")
    ordered = sorted(
        unique,
        key=lambda value: (
            hashlib.sha256(f"goal3-oof\0{seed}\0{value}".encode()).digest(),
            value,
        ),
    )
    return {value: index % n_folds for index, value in enumerate(ordered)}


def _seed_everything(seed: int) -> None:
    require_torch()
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def _device(requested: str | None) -> str:
    require_torch()
    import torch

    if requested is not None:
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is not available")
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def _make_model(config: FingerprintTrainingConfig) -> Any:
    if config.model_kind == "compact":
        return CompactPeakFingerprintEncoder(
            CompactPeakFingerprintConfig(
                n_bits=config.n_bits,
                d_model=config.compact_d_model,
            )
        )
    if config.model_kind == "transformer":
        return PeakFingerprintEncoder(
            PeakFingerprintConfig(
                n_bits=config.n_bits,
                d_model=config.transformer_d_model,
                n_layers=config.transformer_layers,
            )
        )
    raise ValueError(f"Unsupported model kind: {config.model_kind}")


def _validate_targets(targets: np.ndarray, count: int, n_bits: int) -> np.ndarray:
    values = np.asarray(targets, dtype=np.float32)
    if values.shape != (count, n_bits):
        raise ValueError(f"Expected targets shape {(count, n_bits)}, got {values.shape}")
    if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError("Fingerprint targets must be finite values in [0, 1]")
    return values


def _rss_bytes() -> int | None:
    try:
        import psutil
    except ImportError:
        return None
    return int(psutil.Process().memory_info().rss)


def _predict_logits(
    model: Any,
    spectra: Sequence[ProcessedSpectrum],
    *,
    config: FingerprintTrainingConfig,
    device: str,
) -> np.ndarray:
    import torch

    model.eval()
    outputs: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(spectra), config.batch_size):
            subset = spectra[start : start + config.batch_size]
            batch = batch_processed_spectra(subset, max_peaks=config.max_peaks)
            tensors = spectrum_batch_to_torch(batch, device=device)
            logits = model(**tensors)
            outputs.append(logits.float().cpu().numpy())
    if not outputs:
        return np.empty((0, config.n_bits), dtype=np.float32)
    result = np.concatenate(outputs, axis=0).astype(np.float32, copy=False)
    if not np.isfinite(result).all():
        raise FloatingPointError("Fingerprint inference produced NaN or Inf")
    return result


def train_fingerprint_predictor(
    train_spectra: Sequence[ProcessedSpectrum],
    train_targets: np.ndarray,
    *,
    config: FingerprintTrainingConfig = FingerprintTrainingConfig(),
    validation_spectra: Sequence[ProcessedSpectrum] = (),
    validation_targets: np.ndarray | None = None,
    device: str | None = None,
    checkpoint_path: str | Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Train one bounded model with early stopping and resource accounting."""

    require_torch()
    import torch

    if not train_spectra:
        raise ValueError("At least one training spectrum is required")
    y_train = _validate_targets(train_targets, len(train_spectra), config.n_bits)
    if validation_spectra:
        if validation_targets is None:
            raise ValueError("validation_targets are required with validation_spectra")
        y_validation = _validate_targets(
            validation_targets, len(validation_spectra), config.n_bits
        )
    else:
        y_validation = None

    selected_device = _device(device)
    _seed_everything(config.seed)
    model = _make_model(config).to(selected_device)
    target_tensor = torch.as_tensor(y_train, dtype=torch.float32)
    positive_weights = estimate_positive_weights(target_tensor, max_weight=25.0).to(
        selected_device
    )
    criterion = WeightedFingerprintBCELoss(pos_weight=positive_weights)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    use_amp = config.mixed_precision and selected_device.startswith("cuda")
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)
    rng = np.random.default_rng(config.seed)
    best_state: dict[str, Any] | None = None
    best_loss = math.inf
    best_epoch = 0
    epochs_without_improvement = 0
    history: list[dict[str, float | int]] = []
    start_time = time.perf_counter()
    rss_start = _rss_bytes()
    peak_rss = rss_start
    if selected_device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()

    for epoch in range(1, config.epochs + 1):
        model.train()
        order = rng.permutation(len(train_spectra))
        losses: list[float] = []
        for start in range(0, len(order), config.batch_size):
            indices = order[start : start + config.batch_size]
            subset = [train_spectra[int(index)] for index in indices]
            batch = batch_processed_spectra(subset, max_peaks=config.max_peaks)
            tensors = spectrum_batch_to_torch(batch, device=selected_device)
            targets = torch.as_tensor(y_train[indices], device=selected_device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(
                device_type="cuda" if selected_device.startswith("cuda") else "cpu",
                dtype=torch.float16 if selected_device.startswith("cuda") else torch.bfloat16,
                enabled=use_amp,
            ):
                logits = model(**tensors)
                loss = criterion(logits, targets)
            if not bool(torch.isfinite(loss)):
                raise FloatingPointError(f"Non-finite fingerprint loss at epoch {epoch}")
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            if any(
                parameter.grad is not None
                and not bool(torch.isfinite(parameter.grad).all())
                for parameter in model.parameters()
            ):
                raise FloatingPointError(f"Non-finite fingerprint gradient at epoch {epoch}")
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))

        train_loss = float(np.mean(losses))
        if validation_spectra:
            validation_logits = _predict_logits(
                model, validation_spectra, config=config, device=selected_device
            )
            with torch.no_grad():
                validation_loss = float(
                    criterion(
                        torch.as_tensor(validation_logits, device=selected_device),
                        torch.as_tensor(y_validation, device=selected_device),
                    ).cpu()
                )
        else:
            validation_loss = train_loss
        history.append(
            {"epoch": epoch, "train_loss": train_loss, "validation_loss": validation_loss}
        )
        if validation_loss < best_loss - 1e-6:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = {
                key: value.detach().cpu().clone() for key, value in model.state_dict().items()
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        rss = _rss_bytes()
        if rss is not None:
            peak_rss = max(peak_rss or 0, rss)
        if validation_spectra and epochs_without_improvement >= config.patience:
            break

    if best_state is None:
        raise RuntimeError("Fingerprint training did not produce a checkpoint")
    model.load_state_dict(best_state)
    model.to(selected_device)
    train_logits = _predict_logits(model, train_spectra, config=config, device=selected_device)
    train_probability = 1.0 / (1.0 + np.exp(-np.clip(train_logits, -50.0, 50.0)))
    report: dict[str, Any] = {
        "config": asdict(config),
        "device": selected_device,
        "parameter_count": int(sum(parameter.numel() for parameter in model.parameters())),
        "best_epoch": best_epoch,
        "best_validation_loss": best_loss,
        "epochs_completed": len(history),
        "history": history,
        "train_fingerprint_metrics": fingerprint_metrics(train_probability, y_train),
        "elapsed_seconds": time.perf_counter() - start_time,
        "rss_start_bytes": rss_start,
        "peak_rss_bytes": peak_rss,
        "peak_vram_bytes": int(torch.cuda.max_memory_allocated())
        if selected_device.startswith("cuda")
        else 0,
    }
    if validation_spectra:
        validation_logits = _predict_logits(
            model, validation_spectra, config=config, device=selected_device
        )
        validation_probability = 1.0 / (
            1.0 + np.exp(-np.clip(validation_logits, -50.0, 50.0))
        )
        report["validation_fingerprint_metrics"] = fingerprint_metrics(
            validation_probability, y_validation
        )

    if checkpoint_path is not None:
        destination = Path(checkpoint_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "format_version": 1,
                "model_kind": config.model_kind,
                "config": asdict(config),
                "state_dict": best_state,
                "report": report,
            },
            destination,
        )
        report["checkpoint_path"] = str(destination)
        report["checkpoint_bytes"] = destination.stat().st_size
    return model, report


def oof_fingerprint_predictions(
    train_spectra: Sequence[ProcessedSpectrum],
    train_targets: np.ndarray,
    train_group_ids: Sequence[str],
    validation_spectra: Sequence[ProcessedSpectrum],
    *,
    config: FingerprintTrainingConfig = FingerprintTrainingConfig(),
    n_folds: int = 3,
    device: str | None = None,
    checkpoint_dir: str | Path | None = None,
) -> OOFFingerprintResult:
    """Generate strict identity-OOF train features and held-out predictions."""

    if len(train_spectra) != len(train_group_ids):
        raise ValueError("train_group_ids must align with train_spectra")
    y_train = _validate_targets(train_targets, len(train_spectra), config.n_bits)
    fold_by_group = deterministic_group_folds(
        train_group_ids, n_folds=n_folds, seed=config.seed
    )
    oof = np.zeros_like(y_train, dtype=np.float32)
    assigned = np.zeros(len(train_spectra), dtype=bool)
    fold_reports: list[dict[str, Any]] = []
    selected_device = _device(device)
    for fold in range(n_folds):
        validation_indices = np.asarray(
            [index for index, key in enumerate(train_group_ids) if fold_by_group[str(key)] == fold],
            dtype=np.int64,
        )
        training_indices = np.asarray(
            [index for index, key in enumerate(train_group_ids) if fold_by_group[str(key)] != fold],
            dtype=np.int64,
        )
        if not len(validation_indices) or not len(training_indices):
            raise RuntimeError(f"Empty OOF partition for fold {fold}")
        fold_config = FingerprintTrainingConfig(
            **{**asdict(config), "seed": config.seed + fold}
        )
        checkpoint = (
            Path(checkpoint_dir) / f"fingerprint_oof_fold_{fold}.pt"
            if checkpoint_dir is not None
            else None
        )
        model, report = train_fingerprint_predictor(
            [train_spectra[int(index)] for index in training_indices],
            y_train[training_indices],
            config=fold_config,
            validation_spectra=[train_spectra[int(index)] for index in validation_indices],
            validation_targets=y_train[validation_indices],
            device=selected_device,
            checkpoint_path=checkpoint,
        )
        logits = _predict_logits(
            model,
            [train_spectra[int(index)] for index in validation_indices],
            config=fold_config,
            device=selected_device,
        )
        oof[validation_indices] = 1.0 / (1.0 + np.exp(-np.clip(logits, -50.0, 50.0)))
        assigned[validation_indices] = True
        report["fold"] = fold
        report["training_spectrum_count"] = len(training_indices)
        report["validation_spectrum_count"] = len(validation_indices)
        fold_reports.append(report)
        del model
        if selected_device.startswith("cuda"):
            import torch

            torch.cuda.empty_cache()
    if not assigned.all():
        raise AssertionError("Every training spectrum must receive exactly one OOF prediction")

    selected_epochs = max(
        1,
        int(np.median([int(report["best_epoch"]) for report in fold_reports])),
    )
    final_config = FingerprintTrainingConfig(
        **{**asdict(config), "epochs": selected_epochs, "patience": selected_epochs}
    )
    final_checkpoint = (
        Path(checkpoint_dir) / "fingerprint_final.pt"
        if checkpoint_dir is not None
        else None
    )
    final_model, final_report = train_fingerprint_predictor(
        train_spectra,
        y_train,
        config=final_config,
        device=selected_device,
        checkpoint_path=final_checkpoint,
    )
    validation_logits = _predict_logits(
        final_model, validation_spectra, config=final_config, device=selected_device
    )
    validation_probability = 1.0 / (
        1.0 + np.exp(-np.clip(validation_logits, -50.0, 50.0))
    )
    return OOFFingerprintResult(
        oof_probabilities=oof,
        validation_probabilities=validation_probability.astype(np.float32, copy=False),
        fold_reports=tuple(fold_reports),
        final_report=final_report,
        fold_by_group=fold_by_group,
    )
