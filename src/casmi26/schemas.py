from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class SpectrumRecord:
    spectrum_id: str
    molecule_id: str
    mz: np.ndarray
    intensity: np.ndarray
    precursor_mz: float
    adduct: str
    ion_mode: str
    collision_energy_ev: tuple[float, ...] = ()
    instrument: str | None = None
    base_peak_intensity: float | None = None
    normalized_smiles: str | None = None
    inchikey14: str | None = None
    molecular_formula: str | None = None
    ingest_lib: str | None = None


@dataclass(frozen=True, slots=True)
class ProcessedSpectrum:
    spectrum_id: str
    molecule_id: str
    mz: np.ndarray
    intensity: np.ndarray
    precursor_mz: float
    neutral_mass: float | None
    adduct: str
    ion_mode: str
    collision_energy_ev: tuple[float, ...]
    instrument: str | None
    quality: dict[str, float]
    normalized_smiles: str | None = None
    inchikey14: str | None = None
    molecular_formula: str | None = None
    ingest_lib: str | None = None


@dataclass(frozen=True, slots=True)
class LibraryEntry:
    candidate_id: str
    smiles: str
    spectrum: ProcessedSpectrum
    formula: str | None = None
    source: str | None = None


@dataclass(slots=True)
class CandidateHit:
    candidate_id: str
    smiles: str
    source: str | None
    source_rank: int
    retrieval_score: float
    features: dict[str, float]
    references_seen: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate_id: str
    smiles: str
    score: float
    rank: int

