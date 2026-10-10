from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .retrieval import FEATURE_NAMES
from .schemas import CandidateHit


@dataclass(frozen=True, slots=True)
class StructureCandidate:
    candidate_id: str
    smiles: str
    exact_mass: float
    formula: str | None = None
    source: str = "structure_catalog"


class MassCandidateIndex:
    """Deterministic structure-only retrieval, independent of reference spectra."""

    def __init__(self, candidates: list[StructureCandidate]):
        if not candidates:
            raise ValueError("At least one structure candidate is required")
        by_key: dict[str, StructureCandidate] = {}
        for candidate in candidates:
            if not candidate.candidate_id or not math.isfinite(candidate.exact_mass):
                continue
            by_key.setdefault(candidate.candidate_id, candidate)
        if not by_key:
            raise ValueError("No valid structure candidate masses")
        self.candidates = [by_key[key] for key in sorted(by_key)]
        self._masses = np.asarray([candidate.exact_mass for candidate in self.candidates])
        self._candidate_ids = np.asarray(
            [candidate.candidate_id for candidate in self.candidates]
        )

    def retrieve(
        self,
        neutral_mass: float | None,
        *,
        top_k: int = 1000,
        tolerance_ppm: float | None = None,
    ) -> list[CandidateHit]:
        if top_k <= 0:
            return []
        if neutral_mass is None or not math.isfinite(neutral_mass) or neutral_mass <= 0:
            order = np.arange(len(self.candidates))
            errors = np.full(len(self.candidates), 1_000_000.0)
        else:
            errors = np.abs(self._masses - neutral_mass) / neutral_mass * 1e6
            if tolerance_ppm is not None:
                selected = np.flatnonzero(errors <= tolerance_ppm)
            elif top_k < len(self.candidates):
                # O(N) selection. Include the full boundary tie before the
                # deterministic candidate-id tie-break.
                kth_error = float(np.partition(errors, top_k - 1)[top_k - 1])
                selected = np.flatnonzero(errors <= kth_error)
            else:
                selected = np.arange(len(self.candidates))
            order = selected[
                np.lexsort((self._candidate_ids[selected], errors[selected]))
            ]

        hits: list[CandidateHit] = []
        for rank, idx in enumerate(order[:top_k], start=1):
            candidate = self.candidates[int(idx)]
            error = float(errors[int(idx)])
            score = float(1.0 / (1.0 + error))
            features = {name: 0.0 for name in FEATURE_NAMES}
            features.update(
                {
                    "mass_error_ppm": error,
                    "abs_precursor_delta": abs(
                        (neutral_mass if neutral_mass is not None else candidate.exact_mass)
                        - candidate.exact_mass
                    ),
                    "retrieval_score": score,
                }
            )
            hits.append(
                CandidateHit(
                    candidate_id=candidate.candidate_id,
                    smiles=candidate.smiles,
                    source=candidate.source,
                    source_rank=rank,
                    retrieval_score=score,
                    features=features,
                    metadata={
                        "formula": candidate.formula,
                        "exact_mass": candidate.exact_mass,
                        "candidate_channel": "mass",
                    },
                )
            )
        return hits


def merge_candidate_hits(
    *sources: list[CandidateHit],
    top_k: int | None = None,
) -> list[CandidateHit]:
    """Union candidate sources while retaining best evidence and provenance."""

    merged: dict[str, CandidateHit] = {}
    provenance: dict[str, set[str]] = {}
    lower_is_better = {"mass_error_ppm", "abs_precursor_delta"}
    for hits in sources:
        for hit in hits:
            provenance.setdefault(hit.candidate_id, set()).add(hit.source or "unknown")
            current = merged.get(hit.candidate_id)
            if current is None:
                merged[hit.candidate_id] = CandidateHit(
                    candidate_id=hit.candidate_id,
                    smiles=hit.smiles,
                    source=hit.source,
                    source_rank=hit.source_rank,
                    retrieval_score=hit.retrieval_score,
                    features=dict(hit.features),
                    references_seen=hit.references_seen,
                    metadata=dict(hit.metadata),
                )
                continue
            previous_score = current.retrieval_score
            current.retrieval_score = max(previous_score, hit.retrieval_score)
            current.references_seen += hit.references_seen
            for name in FEATURE_NAMES:
                value = hit.features.get(name, 0.0)
                previous = current.features.get(name, 0.0)
                current.features[name] = (
                    min(previous, value) if name in lower_is_better else max(previous, value)
                )
            if hit.retrieval_score > previous_score:
                current.smiles = hit.smiles
            current.metadata.update(hit.metadata)

    ordered = sorted(merged.values(), key=lambda hit: (-hit.retrieval_score, hit.candidate_id))
    if top_k is not None:
        ordered = ordered[:top_k]
    for rank, hit in enumerate(ordered, start=1):
        hit.source_rank = rank
        hit.source = "+".join(sorted(provenance[hit.candidate_id]))
        hit.metadata["provenance"] = sorted(provenance[hit.candidate_id])
    return ordered
