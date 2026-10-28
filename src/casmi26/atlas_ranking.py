"""CPU scoring of formula-matched atlas spectra and reproducible rank fusion."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from casmi26.atlas import clean_peaks


@dataclass(frozen=True)
class AtlasSpectrum:
    mz: np.ndarray
    weight: np.ndarray
    energy_ev: float


def prepare_spectrum(mzs, intensities, precursor, energy_ev, *, max_peaks=128,
                     precursor_window=.5) -> AtlasSpectrum:
    """Clean peaks, optionally remove precursor, and L2-normalize sqrt intensity."""
    mzs, intensities = np.asarray(mzs), np.asarray(intensities)
    if mzs.ndim != 1 or intensities.shape != mzs.shape:
        raise ValueError("Peak arrays must be aligned and one-dimensional")
    if not math.isfinite(precursor) or precursor <= 0 or max_peaks < 1:
        raise ValueError("Invalid precursor or peak limit")
    if not math.isfinite(precursor_window) or precursor_window < 0:
        raise ValueError("Invalid precursor window")
    mz, intensity = clean_peaks(np.column_stack((mzs, intensities)))
    if precursor_window:
        keep = np.abs(mz - precursor) > precursor_window
        mz, intensity = mz[keep], intensity[keep]
    if len(mz) > max_peaks:
        chosen = np.lexsort((mz, -intensity))[:max_peaks]
        chosen.sort()
        mz, intensity = mz[chosen], intensity[chosen]
    weight = np.sqrt(intensity)
    norm = np.linalg.norm(weight)
    if norm:
        weight /= norm
    try:
        energies = np.asarray(energy_ev, dtype=np.float64).reshape(-1)
        energies = energies[np.isfinite(energies) & (energies >= 0)]
        ce = float(energies.mean()) if len(energies) else float("nan")
    except (ValueError, TypeError):
        ce = float("nan")
    return AtlasSpectrum(mz, weight, ce)


def cosine(query: AtlasSpectrum, reference: AtlasSpectrum, tolerance_da=.02) -> float:
    """One-to-one greedy cosine, ordered by intensity product then mass error.

    Vectorize candidate peak pairs to avoid Python searchsorted per query peak.
    The ordering matches casmi26.spectral_evidence.cosine_similarity.
    """
    if not math.isfinite(tolerance_da) or tolerance_da < 0:
        raise ValueError("Invalid tolerance")
    if not len(query.mz) or not len(reference.mz):
        return 0.
    error = np.abs(query.mz[:, None] - reference.mz[None, :])
    qi, ri = np.nonzero(error <= tolerance_da)
    if not len(qi):
        return 0.
    products = query.weight[qi] * reference.weight[ri]
    order = np.lexsort((ri, qi, error[qi, ri], -products))
    used_q, used_r = set(), set()
    score = 0.
    for index in order:
        q, r = int(qi[index]), int(ri[index])
        if q not in used_q and r not in used_r:
            used_q.add(q)
            used_r.add(r)
            score += products[index]
    return float(np.clip(score, 0., 1.))


def score_atlas(queries: list[AtlasSpectrum], references: list[list[AtlasSpectrum]],
                *, tolerance_da=.02) -> dict[str, np.ndarray]:
    """Average query scores per molecule, after max-CE or nearest-CE reduction.

    Missing query CE falls back to max-CE. Empty references receive zero. This
    scorer supports [M+H]+ only; callers must select matching acquisitions.
    """
    if not queries:
        raise ValueError("At least one query spectrum required")
    maximum = np.zeros((len(queries), len(references)))
    nearest = np.zeros_like(maximum)
    for c, spectra in enumerate(references):
        if not spectra:
            continue
        energies = np.array([s.energy_ev for s in spectra])
        if not np.isfinite(energies).all():
            raise ValueError("Atlas collision energies must be finite")
        for q, query in enumerate(queries):
            values = np.array([cosine(query, ref, tolerance_da) for ref in spectra])
            maximum[q, c] = values.max()
            if math.isfinite(query.energy_ev):
                delta = np.abs(energies - query.energy_ev)
                # Average equal-distance acquisitions; never break CE ties using truth.
                nearest[q, c] = values[delta == delta.min()].mean()
            else:
                nearest[q, c] = maximum[q, c]
    return dict(atlas_max=maximum.mean(0), atlas_nearest=nearest.mean(0))


def ranks(scores, keys):
    scores = np.asarray(scores, dtype=np.float64)
    if scores.shape != (len(keys),) or not np.isfinite(scores).all():
        raise ValueError("Scores must be finite and candidate aligned")
    if len(set(keys)) != len(keys):
        raise ValueError("Candidate identities must be unique")
    order = np.lexsort((np.asarray(keys), -scores))
    result = np.empty(len(keys), dtype=np.int64)
    result[order] = np.arange(1, len(keys) + 1)
    return result


def leader_safe_fusion(neural_scores, atlas_scores, keys, *, atlas_weight=.25):
    """Fixed RRF on ranks 2+, preserving the neurally selected leader."""
    if not math.isfinite(atlas_weight) or atlas_weight < 0:
        raise ValueError("Invalid atlas fusion weight")
    nr, ar = ranks(neural_scores, keys), ranks(atlas_scores, keys)
    score = 1. / (3. + nr) + atlas_weight / (3. + ar)
    if len(score):
        score[nr == 1] = score.max() + 1.
    return score


def paired_bootstrap(delta, *, seed=20261028, samples=5000):
    values = np.asarray(delta, dtype=np.float64)
    if not len(values):
        return {"molecules": 0, "mean": None, "ci95": None}
    if not np.isfinite(values).all():
        raise ValueError("Non-finite deltas")
    rng = np.random.default_rng(seed)
    means = np.empty(samples)
    for start in range(0, samples, 256):
        n = min(256, samples - start)
        means[start:start+n] = values[rng.integers(0, len(values), size=(n, len(values)))].mean(1)
    return dict(molecules=len(values), mean=float(values.mean()),
                ci95=np.quantile(means, [.025, .975]).tolist())
