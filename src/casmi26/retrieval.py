from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import math

import numpy as np

from .schemas import CandidateHit, LibraryEntry, ProcessedSpectrum
from .similarity import cosine_similarity, entropy_similarity, neutral_loss_cosine, shifted_cosine


FEATURE_NAMES = (
    "direct_cosine",
    "shifted_cosine",
    "neutral_loss_cosine",
    "entropy_similarity",
    "matched_peaks",
    "query_coverage",
    "reference_coverage",
    "mass_error_ppm",
    "abs_precursor_delta",
    "same_adduct",
    "same_ion_mode",
    "peak_count_ratio",
    "retrieval_score",
)


class SpectralLibraryIndex:
    """Small, deterministic brute-force baseline index.

    The interface deliberately allows replacement by a disk/ANN index without
    changing downstream ranking code.
    """

    def __init__(
        self,
        entries: list[LibraryEntry],
        *,
        peak_tolerance_da: float = 0.02,
        mass_tolerance_ppm: float = 20.0,
        min_mass_candidates: int = 25,
    ):
        if not entries:
            raise ValueError("At least one library entry is required")
        self.entries = list(entries)
        self.peak_tolerance_da = peak_tolerance_da
        self.mass_tolerance_ppm = mass_tolerance_ppm
        self.min_mass_candidates = max(1, min_mass_candidates)
        masses = np.asarray(
            [np.nan if entry.spectrum.neutral_mass is None else entry.spectrum.neutral_mass for entry in entries],
            dtype=np.float64,
        )
        self._masses = masses
        self._mass_order = np.argsort(np.nan_to_num(masses, nan=np.inf))
        self._sorted_masses = masses[self._mass_order]

    def _mass_candidates(self, query: ProcessedSpectrum) -> list[int]:
        if query.neutral_mass is None:
            return list(range(len(self.entries)))
        delta = query.neutral_mass * self.mass_tolerance_ppm * 1e-6
        left = int(np.searchsorted(self._sorted_masses, query.neutral_mass - delta, side="left"))
        right = int(np.searchsorted(self._sorted_masses, query.neutral_mass + delta, side="right"))
        matches = [int(idx) for idx in self._mass_order[left:right] if math.isfinite(self._masses[idx])]

        # Exact-mass filtering can leave only the positive identity in a small
        # development library. Add the closest-mass entries as hard negatives
        # so the supervised ranker always sees a meaningful candidate group.
        target_size = min(self.min_mass_candidates, len(self.entries))
        if len(matches) < target_size:
            selected = set(matches)
            finite_indices = np.flatnonzero(np.isfinite(self._masses))
            nearest = finite_indices[
                np.argsort(np.abs(self._masses[finite_indices] - query.neutral_mass), kind="stable")
            ]
            for idx in nearest:
                candidate_idx = int(idx)
                if candidate_idx not in selected:
                    matches.append(candidate_idx)
                    selected.add(candidate_idx)
                if len(matches) >= target_size:
                    break
        return matches or list(range(len(self.entries)))

    def retrieve(self, query: ProcessedSpectrum, *, top_k: int = 25) -> list[CandidateHit]:
        by_candidate: dict[str, CandidateHit] = {}
        reference_counts: defaultdict[str, int] = defaultdict(int)
        for idx in self._mass_candidates(query):
            entry = self.entries[idx]
            direct = cosine_similarity(
                query.mz,
                query.intensity,
                entry.spectrum.mz,
                entry.spectrum.intensity,
                tolerance_da=self.peak_tolerance_da,
            )
            shifted = shifted_cosine(query, entry.spectrum, tolerance_da=self.peak_tolerance_da)
            loss = neutral_loss_cosine(query, entry.spectrum, tolerance_da=self.peak_tolerance_da)
            entropy = entropy_similarity(query, entry.spectrum, tolerance_da=self.peak_tolerance_da)
            mass_error = _mass_error_ppm(query.neutral_mass, entry.spectrum.neutral_mass)
            peak_ratio = min(len(query.mz), len(entry.spectrum.mz)) / max(len(query.mz), len(entry.spectrum.mz), 1)
            retrieval_score = (
                0.50 * direct.cosine
                + 0.20 * shifted.cosine
                + 0.20 * loss.cosine
                + 0.10 * entropy
            )
            features = {
                "direct_cosine": direct.cosine,
                "shifted_cosine": shifted.cosine,
                "neutral_loss_cosine": loss.cosine,
                "entropy_similarity": entropy,
                "matched_peaks": float(direct.matched_peaks),
                "query_coverage": direct.query_coverage,
                "reference_coverage": direct.reference_coverage,
                "mass_error_ppm": mass_error,
                "abs_precursor_delta": abs(query.precursor_mz - entry.spectrum.precursor_mz),
                "same_adduct": float(query.adduct == entry.spectrum.adduct),
                "same_ion_mode": float(query.ion_mode == entry.spectrum.ion_mode),
                "peak_count_ratio": float(peak_ratio),
                "retrieval_score": float(retrieval_score),
            }
            reference_counts[entry.candidate_id] += 1
            hit = CandidateHit(
                candidate_id=entry.candidate_id,
                smiles=entry.smiles,
                source=entry.source,
                source_rank=0,
                retrieval_score=float(retrieval_score),
                features=features,
            )
            previous = by_candidate.get(entry.candidate_id)
            if previous is None or hit.retrieval_score > previous.retrieval_score:
                by_candidate[entry.candidate_id] = hit

        ordered = sorted(by_candidate.values(), key=lambda hit: (-hit.retrieval_score, hit.candidate_id))
        for rank, hit in enumerate(ordered, start=1):
            hit.source_rank = rank
            hit.references_seen = reference_counts[hit.candidate_id]
        return ordered[:top_k]

    def retrieve_many(
        self,
        queries: list[ProcessedSpectrum],
        *,
        top_k: int = 25,
    ) -> list[CandidateHit]:
        """Aggregate multiple acquisitions with max evidence per feature."""

        combined: dict[str, CandidateHit] = {}
        counts: defaultdict[str, int] = defaultdict(int)
        for query in queries:
            for hit in self.retrieve(query, top_k=max(top_k, len(self.entries))):
                counts[hit.candidate_id] += 1
                previous = combined.get(hit.candidate_id)
                if previous is None:
                    combined[hit.candidate_id] = replace(hit, features=dict(hit.features))
                    continue
                if hit.retrieval_score > previous.retrieval_score:
                    previous.smiles = hit.smiles
                    previous.source = hit.source
                    previous.retrieval_score = hit.retrieval_score
                for name, value in hit.features.items():
                    if name in {"mass_error_ppm", "abs_precursor_delta"}:
                        previous.features[name] = min(
                            previous.features.get(name, float("inf")), value
                        )
                    else:
                        previous.features[name] = max(
                            previous.features.get(name, float("-inf")), value
                        )
        ordered = sorted(combined.values(), key=lambda hit: (-hit.retrieval_score, hit.candidate_id))
        for rank, hit in enumerate(ordered, start=1):
            hit.source_rank = rank
            hit.references_seen = counts[hit.candidate_id]
        return ordered[:top_k]


def feature_vector(hit: CandidateHit) -> np.ndarray:
    return np.asarray([hit.features[name] for name in FEATURE_NAMES], dtype=np.float64)


def _mass_error_ppm(query_mass: float | None, candidate_mass: float | None) -> float:
    if query_mass is None or candidate_mass is None or query_mass <= 0:
        return 1_000_000.0
    return abs(query_mass - candidate_mass) / query_mass * 1e6
