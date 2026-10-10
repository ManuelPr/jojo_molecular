from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .schemas import ProcessedSpectrum


@dataclass(frozen=True, slots=True)
class MatchStats:
    cosine: float
    matched_peaks: int
    query_coverage: float
    reference_coverage: float


def _match_pairs(
    query_mz: np.ndarray,
    reference_mz: np.ndarray,
    tolerance_da: float,
) -> list[tuple[int, int]]:
    """Greedy one-to-one nearest peak matching for sorted peak arrays."""

    pairs: list[tuple[int, int]] = []
    used: set[int] = set()
    for qi, value in enumerate(query_mz):
        left = int(np.searchsorted(reference_mz, value - tolerance_da, side="left"))
        right = int(np.searchsorted(reference_mz, value + tolerance_da, side="right"))
        candidates = [ri for ri in range(left, right) if ri not in used]
        if not candidates:
            continue
        ri = min(candidates, key=lambda idx: abs(float(reference_mz[idx]) - float(value)))
        used.add(ri)
        pairs.append((qi, ri))
    return pairs


def cosine_similarity(
    query_mz: np.ndarray,
    query_intensity: np.ndarray,
    reference_mz: np.ndarray,
    reference_intensity: np.ndarray,
    *,
    tolerance_da: float = 0.02,
) -> MatchStats:
    if query_mz.size == 0 or reference_mz.size == 0:
        return MatchStats(0.0, 0, 0.0, 0.0)
    pairs = _match_pairs(query_mz, reference_mz, tolerance_da)
    if not pairs:
        return MatchStats(0.0, 0, 0.0, 0.0)
    qi = np.fromiter((pair[0] for pair in pairs), dtype=np.int32)
    ri = np.fromiter((pair[1] for pair in pairs), dtype=np.int32)
    dot = float(np.dot(query_intensity[qi], reference_intensity[ri]))
    q_norm = float(np.linalg.norm(query_intensity))
    r_norm = float(np.linalg.norm(reference_intensity))
    cosine = dot / (q_norm * r_norm) if q_norm and r_norm else 0.0
    q_total = float(np.sum(query_intensity))
    r_total = float(np.sum(reference_intensity))
    return MatchStats(
        cosine=max(0.0, min(1.0, cosine)),
        matched_peaks=len(pairs),
        query_coverage=float(np.sum(query_intensity[qi]) / q_total) if q_total else 0.0,
        reference_coverage=float(np.sum(reference_intensity[ri]) / r_total) if r_total else 0.0,
    )


def shifted_cosine(
    query: ProcessedSpectrum,
    reference: ProcessedSpectrum,
    *,
    tolerance_da: float = 0.02,
) -> MatchStats:
    precursor_delta = query.precursor_mz - reference.precursor_mz
    return cosine_similarity(
        query.mz,
        query.intensity,
        reference.mz + precursor_delta,
        reference.intensity,
        tolerance_da=tolerance_da,
    )


def neutral_loss_cosine(
    query: ProcessedSpectrum,
    reference: ProcessedSpectrum,
    *,
    tolerance_da: float = 0.02,
) -> MatchStats:
    query_losses = np.sort(query.precursor_mz - query.mz)
    reference_losses = np.sort(reference.precursor_mz - reference.mz)
    query_order = np.argsort(query.precursor_mz - query.mz)
    reference_order = np.argsort(reference.precursor_mz - reference.mz)
    return cosine_similarity(
        query_losses,
        query.intensity[query_order],
        reference_losses,
        reference.intensity[reference_order],
        tolerance_da=tolerance_da,
    )


def spectral_entropy(intensity: np.ndarray) -> float:
    total = float(np.sum(intensity))
    if total <= 0:
        return 0.0
    probabilities = np.asarray(intensity, dtype=np.float64) / total
    probabilities = probabilities[probabilities > 0]
    return float(-np.sum(probabilities * np.log(probabilities)))


def entropy_similarity(
    query: ProcessedSpectrum,
    reference: ProcessedSpectrum,
    *,
    tolerance_da: float = 0.02,
) -> float:
    pairs = _match_pairs(query.mz, reference.mz, tolerance_da)
    if not pairs:
        return 0.0
    qi = np.fromiter((pair[0] for pair in pairs), dtype=np.int32)
    ri = np.fromiter((pair[1] for pair in pairs), dtype=np.int32)
    p = np.asarray(query.intensity[qi], dtype=np.float64)
    q = np.asarray(reference.intensity[ri], dtype=np.float64)
    if p.sum() <= 0 or q.sum() <= 0:
        return 0.0
    p /= p.sum()
    q /= q.sum()
    midpoint = 0.5 * (p + q)
    jsd = 0.5 * np.sum(p * np.log(np.maximum(p / midpoint, 1e-12)))
    jsd += 0.5 * np.sum(q * np.log(np.maximum(q / midpoint, 1e-12)))
    return float(max(0.0, min(1.0, 1.0 - jsd / math.log(2.0))))

