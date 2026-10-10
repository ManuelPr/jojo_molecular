from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from .chemistry import canonical_inchikey14


@dataclass(frozen=True, slots=True)
class RankingMetrics:
    mrr_at_25: float
    hit_at_1: float
    hit_at_5: float
    hit_at_10: float
    recall_at_25: float
    query_count: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "mrr_at_25": self.mrr_at_25,
            "hit_at_1": self.hit_at_1,
            "hit_at_5": self.hit_at_5,
            "hit_at_10": self.hit_at_10,
            "recall_at_25": self.recall_at_25,
            "query_count": self.query_count,
        }


def reciprocal_rank(
    truth_smiles: str,
    predicted_smiles: Sequence[str],
    *,
    k: int = 25,
) -> float:
    truth_key = canonical_inchikey14(truth_smiles)
    if truth_key is None:
        raise ValueError("Truth SMILES is not parseable by RDKit")
    for rank, smiles in enumerate(predicted_smiles[:k], start=1):
        if canonical_inchikey14(smiles) == truth_key:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank_at_k(
    truths: Mapping[str, str],
    predictions: Mapping[str, Sequence[str]],
    *,
    k: int = 25,
) -> float:
    if not truths:
        raise ValueError("At least one truth row is required")
    missing = set(truths) - set(predictions)
    if missing:
        raise ValueError(f"Missing predictions for {len(missing)} molecule(s)")
    return float(np.mean([reciprocal_rank(smi, predictions[mid], k=k) for mid, smi in truths.items()]))


def evaluate_rankings(
    truth_keys: Mapping[str, str],
    ranked_keys: Mapping[str, Sequence[str]],
) -> RankingMetrics:
    if not truth_keys:
        raise ValueError("At least one query is required")
    ranks: list[int | None] = []
    for query_id, truth_key in truth_keys.items():
        candidates = ranked_keys.get(query_id, ())[:25]
        rank = next((idx for idx, key in enumerate(candidates, start=1) if key == truth_key), None)
        ranks.append(rank)
    arr = np.asarray([0 if rank is None else rank for rank in ranks], dtype=np.int32)
    reciprocal = np.asarray([0.0 if rank == 0 else 1.0 / rank for rank in arr])
    return RankingMetrics(
        mrr_at_25=float(reciprocal.mean()),
        hit_at_1=float(np.mean(arr == 1)),
        hit_at_5=float(np.mean((arr > 0) & (arr <= 5))),
        hit_at_10=float(np.mean((arr > 0) & (arr <= 10))),
        recall_at_25=float(np.mean(arr > 0)),
        query_count=len(ranks),
    )

