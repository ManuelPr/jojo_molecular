from __future__ import annotations

from dataclasses import dataclass
import math
import re
from collections.abc import Mapping, Sequence
from typing import Literal

import numpy as np


@dataclass(frozen=True, slots=True)
class PeakMatch:
    query_index: int
    reference_index: int
    query_mz: float
    reference_mz: float
    shifted_reference_mz: float
    mass_error_da: float
    mode: str
    weight: float


@dataclass(frozen=True, slots=True)
class SimilarityResult:
    score: float
    matched_peaks: int
    query_coverage: float
    reference_coverage: float
    mean_abs_mass_error_da: float
    max_abs_mass_error_da: float
    matches: tuple[PeakMatch, ...] = ()


@dataclass(frozen=True, slots=True)
class NeutralLossSpec:
    name: str
    formula: str
    exact_mass: float


@dataclass(frozen=True, slots=True)
class NeutralLossHit:
    name: str
    formula: str
    exact_mass: float
    observed_mass: float
    mass_error_da: float
    peak_index: int
    intensity: float


@dataclass(frozen=True, slots=True)
class CandidateSpectrumEvidence:
    """Evidence that can discriminate candidates only with a candidate spectrum.

    The reference spectrum can be experimental (an identity-linked library
    spectrum) or predicted by a forward model.  A query-only descriptor is
    deliberately not accepted as candidate evidence.
    """

    direct_cosine: float
    modified_cosine: float
    precursor_shifted_cosine: float
    entropy_similarity: float
    neutral_loss_similarity: float
    matched_peaks: int
    query_coverage: float
    reference_coverage: float
    mean_mass_error_da: float
    max_mass_error_da: float
    intensity_distribution_similarity: float
    high_mass_fragment_coverage: float
    low_mass_fragment_coverage: float
    formula_loss_compatibility: float
    collision_energy_delta: float
    same_adduct: float

    def as_features(self, prefix: str = "") -> dict[str, float]:
        return {
            f"{prefix}fragment_direct_cosine": self.direct_cosine,
            f"{prefix}fragment_modified_cosine": self.modified_cosine,
            f"{prefix}fragment_shifted_cosine": self.precursor_shifted_cosine,
            f"{prefix}fragment_entropy_similarity": self.entropy_similarity,
            f"{prefix}neutral_loss_similarity": self.neutral_loss_similarity,
            f"{prefix}fragment_matched_peaks": float(self.matched_peaks),
            f"{prefix}fragment_query_coverage": self.query_coverage,
            f"{prefix}fragment_reference_coverage": self.reference_coverage,
            f"{prefix}fragment_mean_mass_error_da": self.mean_mass_error_da,
            f"{prefix}fragment_max_mass_error_da": self.max_mass_error_da,
            f"{prefix}fragment_intensity_distribution_similarity": (
                self.intensity_distribution_similarity
            ),
            f"{prefix}high_mass_fragment_coverage": self.high_mass_fragment_coverage,
            f"{prefix}low_mass_fragment_coverage": self.low_mass_fragment_coverage,
            f"{prefix}candidate_formula_loss_compatibility": self.formula_loss_compatibility,
            f"{prefix}collision_energy_delta": self.collision_energy_delta,
            f"{prefix}same_adduct": self.same_adduct,
        }


MONOISOTOPIC_MASS: Mapping[str, float] = {
    "H": 1.00782503223,
    "C": 12.0,
    "N": 14.00307400443,
    "O": 15.99491461957,
    "P": 30.97376199842,
    "S": 31.9720711744,
}


def _formula_mass(formula: Mapping[str, int]) -> float:
    return float(sum(MONOISOTOPIC_MASS[element] * count for element, count in formula.items()))


_LOSS_DEFINITIONS: tuple[tuple[str, str, Mapping[str, int]], ...] = (
    ("H2", "H2", {"H": 2}),
    ("H2O", "H2O", {"H": 2, "O": 1}),
    ("NH3", "NH3", {"N": 1, "H": 3}),
    ("CO", "CO", {"C": 1, "O": 1}),
    ("CO2", "CO2", {"C": 1, "O": 2}),
    ("CH2O", "CH2O", {"C": 1, "H": 2, "O": 1}),
    ("CH3OH", "CH4O", {"C": 1, "H": 4, "O": 1}),
    ("HCOOH", "CH2O2", {"C": 1, "H": 2, "O": 2}),
    ("CH3COOH", "C2H4O2", {"C": 2, "H": 4, "O": 2}),
    ("SO3", "SO3", {"S": 1, "O": 3}),
    ("H3PO4", "H3PO4", {"H": 3, "P": 1, "O": 4}),
    ("pentose_residue", "C5H8O4", {"C": 5, "H": 8, "O": 4}),
    ("deoxyhexose_residue", "C6H10O4", {"C": 6, "H": 10, "O": 4}),
    ("hexose_residue", "C6H10O5", {"C": 6, "H": 10, "O": 5}),
    ("hexose", "C6H12O6", {"C": 6, "H": 12, "O": 6}),
)

COMMON_NEUTRAL_LOSSES: tuple[NeutralLossSpec, ...] = tuple(
    NeutralLossSpec(name, formula, _formula_mass(counts))
    for name, formula, counts in _LOSS_DEFINITIONS
)

_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


def _validated_peaks(
    mz: np.ndarray | Sequence[float],
    intensity: np.ndarray | Sequence[float] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    masses = np.asarray(mz, dtype=np.float64)
    if masses.ndim != 1:
        raise ValueError("m/z values must be one-dimensional")
    values = np.ones_like(masses) if intensity is None else np.asarray(intensity, dtype=np.float64)
    if values.shape != masses.shape or values.ndim != 1:
        raise ValueError("m/z and intensity arrays must be aligned one-dimensional arrays")
    if not np.isfinite(masses).all() or not np.isfinite(values).all():
        raise ValueError("Peak arrays must contain finite values")
    if np.any(masses < 0.0) or np.any(values < 0.0):
        raise ValueError("m/z and intensity values must be non-negative")
    original = np.arange(masses.size, dtype=np.int64)
    order = np.lexsort((original, masses))
    return masses[order], values[order], original[order]


def _allowed_error(
    query_mz: float,
    reference_mz: float,
    tolerance_da: float | None,
    tolerance_ppm: float | None,
) -> float:
    limits: list[float] = []
    if tolerance_da is not None:
        if tolerance_da < 0.0 or not math.isfinite(tolerance_da):
            raise ValueError("tolerance_da must be finite and non-negative")
        limits.append(float(tolerance_da))
    if tolerance_ppm is not None:
        if tolerance_ppm < 0.0 or not math.isfinite(tolerance_ppm):
            raise ValueError("tolerance_ppm must be finite and non-negative")
        limits.append(max(query_mz, reference_mz) * tolerance_ppm * 1e-6)
    if not limits:
        raise ValueError("At least one mass tolerance is required")
    return min(limits)


def _validate_tolerances(
    tolerance_da: float | None,
    tolerance_ppm: float | None,
) -> None:
    # Validate even for empty spectra, where no candidate pair would otherwise
    # call _allowed_error.
    _allowed_error(100.0, 100.0, tolerance_da, tolerance_ppm)


def _candidate_peak_pairs(
    query_mz: np.ndarray,
    reference_mz: np.ndarray,
    query_weight: np.ndarray,
    reference_weight: np.ndarray,
    query_original: np.ndarray,
    reference_original: np.ndarray,
    shifts: Sequence[tuple[str, float]],
    tolerance_da: float | None,
    tolerance_ppm: float | None,
) -> list[PeakMatch]:
    _validate_tolerances(tolerance_da, tolerance_ppm)
    pairs: list[PeakMatch] = []
    max_tolerance = tolerance_da if tolerance_da is not None else 0.0
    if tolerance_ppm is not None and query_mz.size:
        max_tolerance = max(max_tolerance, float(query_mz.max()) * tolerance_ppm * 1e-6)
    for mode, shift in shifts:
        shifted = reference_mz + float(shift)
        for qi, mass in enumerate(query_mz):
            left = int(np.searchsorted(shifted, mass - max_tolerance, side="left"))
            right = int(np.searchsorted(shifted, mass + max_tolerance, side="right"))
            for ri in range(left, right):
                error = abs(float(mass - shifted[ri]))
                if error <= _allowed_error(
                    float(mass), float(shifted[ri]), tolerance_da, tolerance_ppm
                ):
                    pairs.append(
                        PeakMatch(
                            query_index=int(query_original[qi]),
                            reference_index=int(reference_original[ri]),
                            query_mz=float(mass),
                            reference_mz=float(reference_mz[ri]),
                            shifted_reference_mz=float(shifted[ri]),
                            mass_error_da=error,
                            mode=mode,
                            weight=float(query_weight[qi] * reference_weight[ri]),
                        )
                    )
    return pairs


def _select_one_to_one(pairs: Sequence[PeakMatch]) -> tuple[PeakMatch, ...]:
    # This mirrors the deterministic greedy strategy used by matchms: strongest
    # intensity product first, then lower mass error. Direct matches win exact ties.
    ordered = sorted(
        pairs,
        key=lambda pair: (
            -pair.weight,
            pair.mass_error_da,
            0 if pair.mode == "direct" else 1,
            pair.query_index,
            pair.reference_index,
        ),
    )
    query_used: set[int] = set()
    reference_used: set[int] = set()
    selected: list[PeakMatch] = []
    for pair in ordered:
        if pair.query_index in query_used or pair.reference_index in reference_used:
            continue
        query_used.add(pair.query_index)
        reference_used.add(pair.reference_index)
        selected.append(pair)
    return tuple(sorted(selected, key=lambda pair: (pair.query_mz, pair.reference_mz)))


def match_peaks_one_to_one(
    query_mz: np.ndarray | Sequence[float],
    reference_mz: np.ndarray | Sequence[float],
    *,
    query_intensity: np.ndarray | Sequence[float] | None = None,
    reference_intensity: np.ndarray | Sequence[float] | None = None,
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
    shift_da: float = 0.0,
    mode: str = "direct",
) -> tuple[PeakMatch, ...]:
    qmz, qint, qoriginal = _validated_peaks(query_mz, query_intensity)
    rmz, rint, roriginal = _validated_peaks(reference_mz, reference_intensity)
    if not math.isfinite(shift_da):
        raise ValueError("shift_da must be finite")
    pairs = _candidate_peak_pairs(
        qmz,
        rmz,
        qint,
        rint,
        qoriginal,
        roriginal,
        ((mode, shift_da),),
        tolerance_da,
        tolerance_ppm,
    )
    return _select_one_to_one(pairs)


def _weighted_intensity(
    mz: np.ndarray,
    intensity: np.ndarray,
    *,
    mz_power: float,
    intensity_power: float,
) -> np.ndarray:
    if mz_power < 0.0 or intensity_power <= 0.0:
        raise ValueError("mz_power must be non-negative and intensity_power positive")
    return np.power(mz, mz_power) * np.power(intensity, intensity_power)


def _similarity_from_matches(
    matches: tuple[PeakMatch, ...],
    query_intensity: np.ndarray,
    reference_intensity: np.ndarray,
) -> SimilarityResult:
    query_norm = float(np.linalg.norm(query_intensity))
    reference_norm = float(np.linalg.norm(reference_intensity))
    dot = float(sum(pair.weight for pair in matches))
    score = dot / (query_norm * reference_norm) if query_norm and reference_norm else 0.0
    q_total = float(query_intensity.sum())
    r_total = float(reference_intensity.sum())
    q_coverage = (
        sum(float(query_intensity[pair.query_index]) for pair in matches) / q_total
        if q_total
        else 0.0
    )
    r_coverage = (
        sum(float(reference_intensity[pair.reference_index]) for pair in matches) / r_total
        if r_total
        else 0.0
    )
    errors = [pair.mass_error_da for pair in matches]
    return SimilarityResult(
        score=float(np.clip(score, 0.0, 1.0)),
        matched_peaks=len(matches),
        query_coverage=float(np.clip(q_coverage, 0.0, 1.0)),
        reference_coverage=float(np.clip(r_coverage, 0.0, 1.0)),
        mean_abs_mass_error_da=float(np.mean(errors)) if errors else 0.0,
        max_abs_mass_error_da=float(max(errors, default=0.0)),
        matches=matches,
    )


def _cosine_with_shifts(
    query_mz: np.ndarray | Sequence[float],
    query_intensity: np.ndarray | Sequence[float],
    reference_mz: np.ndarray | Sequence[float],
    reference_intensity: np.ndarray | Sequence[float],
    *,
    shifts: Sequence[tuple[str, float]],
    tolerance_da: float | None,
    tolerance_ppm: float | None,
    mz_power: float,
    intensity_power: float,
) -> SimilarityResult:
    qmz, qraw, qoriginal = _validated_peaks(query_mz, query_intensity)
    rmz, rraw, roriginal = _validated_peaks(reference_mz, reference_intensity)
    qweighted = _weighted_intensity(qmz, qraw, mz_power=mz_power, intensity_power=intensity_power)
    rweighted = _weighted_intensity(rmz, rraw, mz_power=mz_power, intensity_power=intensity_power)
    candidates = _candidate_peak_pairs(
        qmz,
        rmz,
        qweighted,
        rweighted,
        qoriginal,
        roriginal,
        shifts,
        tolerance_da,
        tolerance_ppm,
    )
    selected = _select_one_to_one(candidates)
    # _similarity_from_matches indexes original arrays, so preserve caller order.
    return _similarity_from_matches(
        selected,
        _weighted_intensity(
            np.asarray(query_mz, dtype=np.float64),
            np.asarray(query_intensity, dtype=np.float64),
            mz_power=mz_power,
            intensity_power=intensity_power,
        ),
        _weighted_intensity(
            np.asarray(reference_mz, dtype=np.float64),
            np.asarray(reference_intensity, dtype=np.float64),
            mz_power=mz_power,
            intensity_power=intensity_power,
        ),
    )


def cosine_similarity(
    query_mz: np.ndarray | Sequence[float],
    query_intensity: np.ndarray | Sequence[float],
    reference_mz: np.ndarray | Sequence[float],
    reference_intensity: np.ndarray | Sequence[float],
    *,
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
    mz_power: float = 0.0,
    intensity_power: float = 0.5,
) -> SimilarityResult:
    return _cosine_with_shifts(
        query_mz,
        query_intensity,
        reference_mz,
        reference_intensity,
        shifts=(("direct", 0.0),),
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
        mz_power=mz_power,
        intensity_power=intensity_power,
    )


def precursor_shifted_cosine_similarity(
    query_mz: np.ndarray | Sequence[float],
    query_intensity: np.ndarray | Sequence[float],
    reference_mz: np.ndarray | Sequence[float],
    reference_intensity: np.ndarray | Sequence[float],
    *,
    query_precursor_mz: float,
    reference_precursor_mz: float,
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
    mz_power: float = 0.0,
    intensity_power: float = 0.5,
) -> SimilarityResult:
    shift = float(query_precursor_mz - reference_precursor_mz)
    return _cosine_with_shifts(
        query_mz,
        query_intensity,
        reference_mz,
        reference_intensity,
        shifts=(("shifted", shift),),
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
        mz_power=mz_power,
        intensity_power=intensity_power,
    )


def modified_cosine_similarity(
    query_mz: np.ndarray | Sequence[float],
    query_intensity: np.ndarray | Sequence[float],
    reference_mz: np.ndarray | Sequence[float],
    reference_intensity: np.ndarray | Sequence[float],
    *,
    query_precursor_mz: float,
    reference_precursor_mz: float,
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
    mz_power: float = 0.0,
    intensity_power: float = 0.5,
) -> SimilarityResult:
    shift = float(query_precursor_mz - reference_precursor_mz)
    shifts: tuple[tuple[str, float], ...] = (("direct", 0.0),)
    if abs(shift) > 1e-12:
        shifts += (("shifted", shift),)
    return _cosine_with_shifts(
        query_mz,
        query_intensity,
        reference_mz,
        reference_intensity,
        shifts=shifts,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
        mz_power=mz_power,
        intensity_power=intensity_power,
    )


def spectral_entropy(intensity: np.ndarray | Sequence[float]) -> float:
    values = np.asarray(intensity, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all() or np.any(values < 0.0):
        raise ValueError("intensities must be a finite, non-negative vector")
    total = float(values.sum())
    if total <= 0.0:
        return 0.0
    probabilities = values[values > 0.0] / total
    return float(-np.sum(probabilities * np.log(probabilities)))


def _entropy_weight(intensity: np.ndarray) -> np.ndarray:
    total = float(intensity.sum())
    if total <= 0.0:
        return np.zeros_like(intensity, dtype=np.float64)
    probabilities = intensity.astype(np.float64) / total
    entropy = spectral_entropy(probabilities)
    if entropy < 3.0:
        probabilities = np.power(probabilities, 0.25 + 0.25 * entropy)
        probabilities /= probabilities.sum()
    return probabilities


def spectral_entropy_similarity(
    query_mz: np.ndarray | Sequence[float],
    query_intensity: np.ndarray | Sequence[float],
    reference_mz: np.ndarray | Sequence[float],
    reference_intensity: np.ndarray | Sequence[float],
    *,
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
    weighted: bool = True,
) -> SimilarityResult:
    qmz, qraw, _ = _validated_peaks(query_mz, query_intensity)
    rmz, rraw, _ = _validated_peaks(reference_mz, reference_intensity)
    qprob = _entropy_weight(qraw) if weighted else qraw / max(float(qraw.sum()), 1e-12)
    rprob = _entropy_weight(rraw) if weighted else rraw / max(float(rraw.sum()), 1e-12)
    matches = match_peaks_one_to_one(
        qmz,
        rmz,
        query_intensity=qprob,
        reference_intensity=rprob,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
    )
    qmatched = {pair.query_index for pair in matches}
    rmatched = {pair.reference_index for pair in matches}
    mixture = [0.5 * (qprob[pair.query_index] + rprob[pair.reference_index]) for pair in matches]
    mixture.extend(0.5 * qprob[index] for index in range(qprob.size) if index not in qmatched)
    mixture.extend(0.5 * rprob[index] for index in range(rprob.size) if index not in rmatched)
    mix_entropy = spectral_entropy(np.asarray(mixture, dtype=np.float64))
    divergence = 2.0 * mix_entropy - spectral_entropy(qprob) - spectral_entropy(rprob)
    score = float(np.clip(1.0 - divergence / math.log(4.0), 0.0, 1.0))
    base = _similarity_from_matches(matches, qprob, rprob)
    return SimilarityResult(
        score=score,
        matched_peaks=base.matched_peaks,
        query_coverage=base.query_coverage,
        reference_coverage=base.reference_coverage,
        mean_abs_mass_error_da=base.mean_abs_mass_error_da,
        max_abs_mass_error_da=base.max_abs_mass_error_da,
        matches=matches,
    )


def detect_neutral_losses(
    precursor_mz: float,
    mz: np.ndarray | Sequence[float],
    intensity: np.ndarray | Sequence[float],
    *,
    losses: Sequence[NeutralLossSpec] = COMMON_NEUTRAL_LOSSES,
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
    charge: int = 1,
) -> tuple[NeutralLossHit, ...]:
    masses, values, original = _validated_peaks(mz, intensity)
    if not math.isfinite(precursor_mz) or precursor_mz <= 0.0 or charge == 0:
        raise ValueError("precursor_mz must be positive and charge non-zero")
    result: list[NeutralLossHit] = []
    for mass, value, index in zip(masses, values, original, strict=True):
        observed = (float(precursor_mz) - float(mass)) * abs(charge)
        if observed <= 0.0:
            continue
        for spec in losses:
            error = observed - spec.exact_mass
            if abs(error) <= _allowed_error(
                observed, spec.exact_mass, tolerance_da, tolerance_ppm
            ):
                result.append(
                    NeutralLossHit(
                        name=spec.name,
                        formula=spec.formula,
                        exact_mass=spec.exact_mass,
                        observed_mass=observed,
                        mass_error_da=error,
                        peak_index=int(index),
                        intensity=float(value),
                    )
                )
    return tuple(sorted(result, key=lambda hit: (hit.peak_index, abs(hit.mass_error_da), hit.name)))


def neutral_loss_fingerprint(
    precursor_mz: float,
    mz: np.ndarray | Sequence[float],
    intensity: np.ndarray | Sequence[float],
    *,
    losses: Sequence[NeutralLossSpec] = COMMON_NEUTRAL_LOSSES,
    mode: Literal["binary", "count", "intensity"] = "intensity",
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
) -> np.ndarray:
    if mode not in {"binary", "count", "intensity"}:
        raise ValueError(f"Unknown neutral-loss fingerprint mode: {mode!r}")
    hits = detect_neutral_losses(
        precursor_mz,
        mz,
        intensity,
        losses=losses,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
    )
    index = {loss.name: position for position, loss in enumerate(losses)}
    fingerprint = np.zeros(len(losses), dtype=np.float64)
    for hit in hits:
        position = index[hit.name]
        if mode == "binary":
            fingerprint[position] = 1.0
        elif mode == "count":
            fingerprint[position] += 1.0
        elif mode == "intensity":
            fingerprint[position] = max(fingerprint[position], hit.intensity)
    if mode == "intensity" and fingerprint.sum() > 0.0:
        fingerprint /= fingerprint.sum()
    return fingerprint


def neutral_loss_similarity(
    query_mz: np.ndarray | Sequence[float],
    query_intensity: np.ndarray | Sequence[float],
    reference_mz: np.ndarray | Sequence[float],
    reference_intensity: np.ndarray | Sequence[float],
    *,
    query_precursor_mz: float,
    reference_precursor_mz: float,
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
    intensity_power: float = 0.5,
) -> SimilarityResult:
    query_losses = float(query_precursor_mz) - np.asarray(query_mz, dtype=np.float64)
    reference_losses = float(reference_precursor_mz) - np.asarray(reference_mz, dtype=np.float64)
    qvalid = query_losses > 0.0
    rvalid = reference_losses > 0.0
    result = cosine_similarity(
        query_losses[qvalid],
        np.asarray(query_intensity, dtype=np.float64)[qvalid],
        reference_losses[rvalid],
        np.asarray(reference_intensity, dtype=np.float64)[rvalid],
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
        intensity_power=intensity_power,
    )
    return SimilarityResult(
        score=result.score,
        matched_peaks=result.matched_peaks,
        query_coverage=result.query_coverage,
        reference_coverage=result.reference_coverage,
        mean_abs_mass_error_da=result.mean_abs_mass_error_da,
        max_abs_mass_error_da=result.max_abs_mass_error_da,
        matches=tuple(
            PeakMatch(
                query_index=int(np.flatnonzero(qvalid)[pair.query_index]),
                reference_index=int(np.flatnonzero(rvalid)[pair.reference_index]),
                query_mz=pair.query_mz,
                reference_mz=pair.reference_mz,
                shifted_reference_mz=pair.shifted_reference_mz,
                mass_error_da=pair.mass_error_da,
                mode="neutral_loss",
                weight=pair.weight,
            )
            for pair in result.matches
        ),
    )


def _parse_formula(formula: str) -> dict[str, int] | None:
    if not isinstance(formula, str) or not formula:
        return None
    counts: dict[str, int] = {}
    position = 0
    for match in _FORMULA_TOKEN.finditer(formula):
        if match.start() != position:
            return None
        element, raw_count = match.groups()
        counts[element] = counts.get(element, 0) + (int(raw_count) if raw_count else 1)
        position = match.end()
    return counts if position == len(formula) and counts else None


def formula_compatible_neutral_losses(
    candidate_formula: str,
    *,
    losses: Sequence[NeutralLossSpec] = COMMON_NEUTRAL_LOSSES,
) -> dict[str, bool]:
    candidate = _parse_formula(candidate_formula)
    if candidate is None:
        return {loss.name: False for loss in losses}
    result: dict[str, bool] = {}
    for loss in losses:
        required = _parse_formula(loss.formula) or {}
        result[loss.name] = all(candidate.get(element, 0) >= count for element, count in required.items())
    return result


def neutral_loss_candidate_compatibility(
    candidate_formula: str | None,
    hits: Sequence[NeutralLossHit],
) -> float:
    if not candidate_formula or not hits:
        return 0.0
    compatible = formula_compatible_neutral_losses(candidate_formula)
    total = sum(max(hit.intensity, 0.0) for hit in hits)
    if total <= 0.0:
        return 0.0
    supported = sum(hit.intensity for hit in hits if compatible.get(hit.name, False))
    return float(np.clip(supported / total, 0.0, 1.0))


def spectrum_only_descriptors(
    mz: np.ndarray | Sequence[float],
    intensity: np.ndarray | Sequence[float],
    *,
    precursor_mz: float,
) -> dict[str, float]:
    """Describe a spectrum; these values must not be treated as candidate evidence."""

    masses, values, _ = _validated_peaks(mz, intensity)
    total = float(values.sum())
    probability = values / total if total > 0.0 else np.zeros_like(values)
    losses = detect_neutral_losses(precursor_mz, masses, values)
    return {
        "spectrum_peak_count": float(masses.size),
        "spectrum_total_intensity": total,
        "spectrum_entropy": spectral_entropy(values),
        "spectrum_low_mass_fraction": float(probability[masses < 100.0].sum()),
        "spectrum_high_mass_fraction": float(probability[masses >= 0.5 * precursor_mz].sum()),
        "spectrum_neutral_loss_count": float(len(losses)),
        "spectrum_precursor_mz": float(precursor_mz),
    }


def _matched_region_coverage(
    result: SimilarityResult,
    query_intensity: np.ndarray,
    query_mz: np.ndarray,
    mask: np.ndarray,
) -> float:
    denominator = float(query_intensity[mask].sum())
    if denominator <= 0.0:
        return 0.0
    matched = {pair.query_index for pair in result.matches}
    numerator = sum(
        float(query_intensity[index])
        for index in matched
        if index < mask.size and bool(mask[index])
    )
    return float(np.clip(numerator / denominator, 0.0, 1.0))


def _distribution_similarity(result: SimilarityResult, query: np.ndarray, reference: np.ndarray) -> float:
    if not result.matches:
        return 0.0
    q = np.asarray([query[pair.query_index] for pair in result.matches], dtype=np.float64)
    r = np.asarray([reference[pair.reference_index] for pair in result.matches], dtype=np.float64)
    q /= max(float(q.sum()), 1e-12)
    r /= max(float(r.sum()), 1e-12)
    midpoint = 0.5 * (q + r)
    divergence = 0.5 * np.sum(q * np.log(np.maximum(q / midpoint, 1e-12)))
    divergence += 0.5 * np.sum(r * np.log(np.maximum(r / midpoint, 1e-12)))
    return float(np.clip(1.0 - divergence / math.log(2.0), 0.0, 1.0))


def candidate_spectrum_compatibility(
    query_mz: np.ndarray | Sequence[float],
    query_intensity: np.ndarray | Sequence[float],
    candidate_mz: np.ndarray | Sequence[float],
    candidate_intensity: np.ndarray | Sequence[float],
    *,
    query_precursor_mz: float,
    candidate_precursor_mz: float,
    candidate_formula: str | None = None,
    query_collision_energy: float | None = None,
    candidate_collision_energy: float | None = None,
    query_adduct: str | None = None,
    candidate_adduct: str | None = None,
    tolerance_da: float | None = 0.02,
    tolerance_ppm: float | None = None,
) -> CandidateSpectrumEvidence:
    qmass = np.asarray(query_mz, dtype=np.float64)
    qint = np.asarray(query_intensity, dtype=np.float64)
    rint = np.asarray(candidate_intensity, dtype=np.float64)
    direct = cosine_similarity(
        qmass,
        qint,
        candidate_mz,
        rint,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
    )
    modified = modified_cosine_similarity(
        qmass,
        qint,
        candidate_mz,
        rint,
        query_precursor_mz=query_precursor_mz,
        reference_precursor_mz=candidate_precursor_mz,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
    )
    shifted = precursor_shifted_cosine_similarity(
        qmass,
        qint,
        candidate_mz,
        rint,
        query_precursor_mz=query_precursor_mz,
        reference_precursor_mz=candidate_precursor_mz,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
    )
    entropy = spectral_entropy_similarity(
        qmass,
        qint,
        candidate_mz,
        rint,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
    )
    loss = neutral_loss_similarity(
        qmass,
        qint,
        candidate_mz,
        rint,
        query_precursor_mz=query_precursor_mz,
        reference_precursor_mz=candidate_precursor_mz,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
    )
    loss_hits = detect_neutral_losses(
        query_precursor_mz,
        qmass,
        qint,
        tolerance_da=tolerance_da,
        tolerance_ppm=tolerance_ppm,
    )
    ce_delta = 0.0
    if query_collision_energy is not None and candidate_collision_energy is not None:
        ce_delta = abs(float(query_collision_energy) - float(candidate_collision_energy))
    return CandidateSpectrumEvidence(
        direct_cosine=direct.score,
        modified_cosine=modified.score,
        precursor_shifted_cosine=shifted.score,
        entropy_similarity=entropy.score,
        neutral_loss_similarity=loss.score,
        matched_peaks=modified.matched_peaks,
        query_coverage=modified.query_coverage,
        reference_coverage=modified.reference_coverage,
        mean_mass_error_da=modified.mean_abs_mass_error_da,
        max_mass_error_da=modified.max_abs_mass_error_da,
        intensity_distribution_similarity=_distribution_similarity(modified, qint, rint),
        high_mass_fragment_coverage=_matched_region_coverage(
            modified, qint, qmass, qmass >= 0.5 * query_precursor_mz
        ),
        low_mass_fragment_coverage=_matched_region_coverage(
            modified, qint, qmass, qmass < 100.0
        ),
        formula_loss_compatibility=neutral_loss_candidate_compatibility(candidate_formula, loss_hits),
        collision_energy_delta=ce_delta,
        same_adduct=float(
            query_adduct is not None
            and candidate_adduct is not None
            and query_adduct == candidate_adduct
        ),
    )


def balanced_acquisition_weights(
    adducts: Sequence[str],
    collision_energies: Sequence[float | None],
    *,
    quality: Sequence[float] | None = None,
    confidence: Sequence[float] | None = None,
    collision_bin_width: float = 10.0,
) -> np.ndarray:
    """Balance correlated acquisitions by adduct and collision-energy bin."""

    count = len(adducts)
    if len(collision_energies) != count or count == 0 or collision_bin_width <= 0.0:
        raise ValueError("adducts and collision_energies must be non-empty and aligned")
    q = np.ones(count) if quality is None else np.asarray(quality, dtype=np.float64)
    c = np.ones(count) if confidence is None else np.asarray(confidence, dtype=np.float64)
    if q.shape != (count,) or c.shape != (count,) or np.any(q < 0.0) or np.any(c < 0.0):
        raise ValueError("quality and confidence must be aligned non-negative vectors")
    groups: dict[tuple[str, int | None], list[int]] = {}
    adduct_buckets: dict[str, set[int | None]] = {}
    for index, (adduct, energy) in enumerate(zip(adducts, collision_energies, strict=True)):
        bucket = None if energy is None or not math.isfinite(float(energy)) else int(float(energy) // collision_bin_width)
        groups.setdefault((str(adduct), bucket), []).append(index)
        adduct_buckets.setdefault(str(adduct), set()).add(bucket)
    weights = np.zeros(count, dtype=np.float64)
    for (adduct, _), indices in groups.items():
        raw = q[indices] * c[indices]
        if raw.sum() <= 0.0:
            raw = np.ones(len(indices), dtype=np.float64)
        # Each adduct has equal total weight and each of its CE buckets has an
        # equal share. Quality/confidence only redistributes within a bucket.
        group_share = 1.0 / len(adduct_buckets) / len(adduct_buckets[adduct])
        weights[indices] = raw / raw.sum() * group_share
    if weights.sum() <= 0.0:
        return np.full(count, 1.0 / count)
    return weights / weights.sum()


def aggregate_candidate_scores(
    scores: np.ndarray | Sequence[Sequence[float]],
    *,
    method: Literal["mean", "max", "weighted", "confidence_weighted", "rrf"] = "mean",
    weights: np.ndarray | Sequence[float] | None = None,
    confidence: np.ndarray | Sequence[float] | None = None,
    rrf_k: float = 60.0,
) -> np.ndarray:
    """Aggregate [acquisition, candidate] scores while preserving missingness."""

    matrix = np.asarray(scores, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("scores must have shape [acquisitions, candidates]")
    finite = np.isfinite(matrix)
    if method == "max":
        result = np.max(np.where(finite, matrix, -np.inf), axis=0)
        result[~np.any(finite, axis=0)] = np.nan
        return result
    base = np.ones(matrix.shape[0], dtype=np.float64)
    if weights is not None:
        base = np.asarray(weights, dtype=np.float64)
        if base.shape != (matrix.shape[0],) or not np.isfinite(base).all() or np.any(base < 0.0):
            raise ValueError("weights must be finite, non-negative, and acquisition-aligned")
    if method == "confidence_weighted":
        if confidence is None:
            raise ValueError("confidence_weighted aggregation requires confidence")
        conf = np.asarray(confidence, dtype=np.float64)
        if conf.shape != base.shape or not np.isfinite(conf).all() or np.any(conf < 0.0):
            raise ValueError("confidence must be finite, non-negative, and acquisition-aligned")
        base = base * conf
    if method == "rrf":
        if rrf_k <= 0.0:
            raise ValueError("rrf_k must be positive")
        fused = np.zeros(matrix.shape[1], dtype=np.float64)
        for row in range(matrix.shape[0]):
            valid = np.flatnonzero(finite[row])
            order = valid[np.argsort(-matrix[row, valid], kind="stable")]
            for rank, candidate in enumerate(order, start=1):
                fused[candidate] += base[row] / (rrf_k + rank)
        return fused
    if method not in {"mean", "weighted", "confidence_weighted"}:
        raise ValueError(f"Unknown aggregation method: {method!r}")
    effective = finite * base[:, None]
    denominator = effective.sum(axis=0)
    return np.divide(
        np.where(finite, matrix, 0.0).T @ base,
        denominator,
        out=np.full(matrix.shape[1], np.nan),
        where=denominator > 0.0,
    )
