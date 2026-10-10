from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from .retrieval import FEATURE_NAMES, feature_vector
from .schemas import CandidateHit, RankedCandidate


@dataclass(frozen=True, slots=True)
class RankerTrainingSummary:
    row_count: int
    positive_count: int
    negative_count: int
    query_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "row_count": self.row_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "query_count": self.query_count,
        }


class SupervisedRanker:
    def __init__(self, *, random_state: int = 2026):
        self.model = HistGradientBoostingClassifier(
            learning_rate=0.08,
            max_iter=120,
            max_leaf_nodes=15,
            min_samples_leaf=5,
            l2_regularization=0.1,
            random_state=random_state,
        )
        self.is_fitted = False

    def fit(
        self,
        candidate_groups: dict[str, list[CandidateHit]],
        truth_keys: dict[str, str],
    ) -> RankerTrainingSummary:
        rows: list[np.ndarray] = []
        labels: list[int] = []
        used_queries = 0
        for query_id, hits in candidate_groups.items():
            truth_key = truth_keys[query_id]
            group_labels = [int(hit.candidate_id == truth_key) for hit in hits]
            if not any(group_labels) or all(group_labels):
                continue
            used_queries += 1
            rows.extend(feature_vector(hit) for hit in hits)
            labels.extend(group_labels)
        if not rows or len(set(labels)) < 2:
            raise ValueError("Ranker training requires at least one positive and one negative")
        x = np.vstack(rows)
        y = np.asarray(labels, dtype=np.int8)
        self.model.fit(x, y)
        self.is_fitted = True
        return RankerTrainingSummary(
            row_count=len(labels),
            positive_count=int(y.sum()),
            negative_count=int((1 - y).sum()),
            query_count=used_queries,
        )

    def rank(self, hits: list[CandidateHit]) -> list[RankedCandidate]:
        if not hits:
            return []
        if self.is_fitted:
            x = np.vstack([feature_vector(hit) for hit in hits])
            scores = self.model.predict_proba(x)[:, 1]
        else:
            scores = np.asarray([hit.retrieval_score for hit in hits], dtype=np.float64)
        order = sorted(range(len(hits)), key=lambda idx: (-float(scores[idx]), hits[idx].candidate_id))
        return [
            RankedCandidate(
                candidate_id=hits[idx].candidate_id,
                smiles=hits[idx].smiles,
                score=float(scores[idx]),
                rank=rank,
            )
            for rank, idx in enumerate(order, start=1)
        ]

    def save(self, path: str | Path) -> None:
        if not self.is_fitted:
            raise ValueError("Cannot save an unfitted ranker")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "feature_names": FEATURE_NAMES,
                "format_version": 1,
            },
            destination,
        )

    @classmethod
    def load(cls, path: str | Path) -> "SupervisedRanker":
        payload = joblib.load(path)
        if tuple(payload["feature_names"]) != FEATURE_NAMES:
            raise ValueError("Ranker feature schema mismatch")
        ranker = cls()
        ranker.model = payload["model"]
        ranker.is_fitted = True
        return ranker

