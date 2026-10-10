from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


CandidatePoolMode = Literal["controlled", "realistic"]


@dataclass(frozen=True, slots=True)
class FingerprintSpec:
    """Competition-normalized molecular fingerprint definition."""

    kind: Literal["morgan", "maccs"] = "morgan"
    n_bits: int = 512
    radius: int = 2
    use_chirality: bool = False

    def __post_init__(self) -> None:
        if self.kind == "morgan" and self.n_bits <= 0:
            raise ValueError("Morgan fingerprint n_bits must be positive")
        if self.kind == "morgan" and self.radius <= 0:
            raise ValueError("Morgan fingerprint radius must be positive")
        if self.kind == "maccs" and self.n_bits != 167:
            raise ValueError("RDKit MACCS fingerprints have exactly 167 bits")


@dataclass(frozen=True, slots=True)
class SpectrumBatch:
    """Framework-neutral padded spectrum batch consumed by neural adapters."""

    mz: np.ndarray
    intensity: np.ndarray
    neutral_loss: np.ndarray
    peak_mask: np.ndarray
    precursor_mass: np.ndarray
    collision_energy: np.ndarray
    adduct_index: np.ndarray
    ion_mode_index: np.ndarray

    def __post_init__(self) -> None:
        peak_shape = self.mz.shape
        if len(peak_shape) != 2:
            raise ValueError("Peak arrays must have shape [batch, peaks]")
        for name in ("intensity", "neutral_loss", "peak_mask"):
            if getattr(self, name).shape != peak_shape:
                raise ValueError(f"{name} must match mz shape")
        batch_size = peak_shape[0]
        for name in (
            "precursor_mass",
            "collision_energy",
            "adduct_index",
            "ion_mode_index",
        ):
            if getattr(self, name).shape != (batch_size,):
                raise ValueError(f"{name} must have shape [batch]")


@dataclass(frozen=True, slots=True)
class CandidatePoolAudit:
    mode: CandidatePoolMode
    query_count: int
    catalog_size: int
    target_in_catalog_count: int
    target_in_pool_count: int
    target_in_top25_count: int
    explicit_target_injection_count: int
    median_pool_size: float
    median_same_formula_competitors: float
    median_exact_mass_competitors: float

    @property
    def catalog_recall(self) -> float:
        return self.target_in_catalog_count / self.query_count if self.query_count else 0.0

    @property
    def pool_recall(self) -> float:
        return self.target_in_pool_count / self.query_count if self.query_count else 0.0

    @property
    def recall_at_25(self) -> float:
        return self.target_in_top25_count / self.query_count if self.query_count else 0.0


@dataclass(frozen=True, slots=True)
class Goal3ExperimentSpec:
    experiment_id: Literal["E0", "E1", "E2", "E3", "E4", "E5", "E6"]
    candidate_pool_mode: CandidatePoolMode
    feature_groups: tuple[str, ...]
    hard_negative_strategy: str
    uses_neural_fingerprint: bool

