from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem
from rdkit.Chem.Scaffolds import MurckoScaffold
from sklearn.ensemble import HistGradientBoostingClassifier

from .mass_retrieval import StructureCandidate
from .schemas import CandidateHit, RankedCandidate


FP_FEATURE_NAMES = (
    "fingerprint_log_likelihood",
    "fingerprint_soft_jaccard",
    "candidate_active_bit_fraction",
)

CHEMISTRY_CONTEXT_FEATURE_NAMES = (
    "formula_group_size",
    "exact_mass_group_size",
)


@dataclass(frozen=True, slots=True)
class HardNegative:
    candidate_id: str
    tier: int
    mass_error_ppm: float
    same_formula: bool
    same_scaffold: bool
    target_tanimoto: float
    baseline_rank: int | None


@dataclass(frozen=True, slots=True)
class HardNegativeSummary:
    selected_count: int
    same_formula_count: int
    same_scaffold_count: int
    tier_counts: dict[int, int]


def fingerprint_compatibility(
    probabilities: np.ndarray,
    candidate_bits: np.ndarray,
    *,
    epsilon: float = 1e-6,
) -> dict[str, float]:
    """Return inference-safe compatibility between predicted and candidate bits."""

    probability = np.asarray(probabilities, dtype=np.float64)
    bits = np.asarray(candidate_bits, dtype=np.float64)
    if probability.ndim != 1 or bits.shape != probability.shape:
        raise ValueError("Fingerprint probability and candidate arrays must be aligned 1-D vectors")
    probability = np.clip(probability, epsilon, 1.0 - epsilon)
    bits = (bits > 0.5).astype(np.float64)
    log_likelihood = float(np.mean(bits * np.log(probability) + (1.0 - bits) * np.log1p(-probability)))
    intersection = float(np.dot(probability, bits))
    union = float(probability.sum() + bits.sum() - intersection)
    return {
        "fingerprint_log_likelihood": log_likelihood,
        "fingerprint_soft_jaccard": intersection / union if union > 0 else 1.0,
        "candidate_active_bit_fraction": float(bits.mean()),
    }


def annotate_fingerprint_features(
    hits: Sequence[CandidateHit],
    predicted_fingerprint: np.ndarray,
    candidate_fingerprints: Mapping[str, np.ndarray],
) -> list[CandidateHit]:
    """Add fingerprint and candidate-ambiguity features without using truth labels."""

    formula_counts = Counter(str(hit.metadata.get("formula") or "") for hit in hits)
    rounded_mass_counts = Counter(
        round(float(hit.metadata.get("exact_mass", math.nan)), 6)
        for hit in hits
        if math.isfinite(float(hit.metadata.get("exact_mass", math.nan)))
    )
    annotated: list[CandidateHit] = []
    for hit in hits:
        candidate_bits = candidate_fingerprints.get(hit.candidate_id)
        if candidate_bits is None:
            fp_features = {name: 0.0 for name in FP_FEATURE_NAMES}
        else:
            fp_features = fingerprint_compatibility(predicted_fingerprint, candidate_bits)
        formula = str(hit.metadata.get("formula") or "")
        exact_mass = float(hit.metadata.get("exact_mass", math.nan))
        context = {
            "formula_group_size": float(formula_counts[formula]) if formula else 0.0,
            "exact_mass_group_size": float(rounded_mass_counts[round(exact_mass, 6)])
            if math.isfinite(exact_mass)
            else 0.0,
        }
        clone = CandidateHit(
            candidate_id=hit.candidate_id,
            smiles=hit.smiles,
            source=hit.source,
            source_rank=hit.source_rank,
            retrieval_score=hit.retrieval_score,
            features={**hit.features, **fp_features, **context},
            references_seen=hit.references_seen,
            metadata=dict(hit.metadata),
        )
        annotated.append(clone)
    return annotated


def mine_hard_negatives(
    target: StructureCandidate,
    candidates: Iterable[StructureCandidate],
    *,
    baseline_ranks: Mapping[str, int] | None = None,
    max_negatives: int = 64,
    mass_window_ppm: float = 100.0,
) -> tuple[list[HardNegative], HardNegativeSummary]:
    """Mine label-aware training negatives; no returned value is an inference feature."""

    if max_negatives <= 0:
        return [], HardNegativeSummary(0, 0, 0, {})
    target_mol = Chem.MolFromSmiles(target.smiles)
    if target_mol is None:
        raise ValueError(f"Invalid target SMILES for {target.candidate_id}")
    target_scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=target_mol)
    target_fp = AllChem.GetMorganGenerator(radius=2, fpSize=512).GetFingerprint(target_mol)
    ranks = baseline_ranks or {}
    negatives: list[HardNegative] = []
    for candidate in candidates:
        if candidate.candidate_id == target.candidate_id:
            continue
        candidate_mol = Chem.MolFromSmiles(candidate.smiles)
        if candidate_mol is None:
            continue
        mass_error = abs(candidate.exact_mass - target.exact_mass) / target.exact_mass * 1e6
        same_formula = bool(target.formula and candidate.formula == target.formula)
        candidate_scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=candidate_mol)
        same_scaffold = bool(target_scaffold and candidate_scaffold == target_scaffold)
        candidate_fp = AllChem.GetMorganGenerator(radius=2, fpSize=512).GetFingerprint(candidate_mol)
        tanimoto = float(DataStructs.TanimotoSimilarity(target_fp, candidate_fp))
        if same_formula and same_scaffold and tanimoto >= 0.7:
            tier = 4
        elif same_formula and same_scaffold:
            tier = 3
        elif same_formula:
            tier = 2
        elif mass_error <= mass_window_ppm or candidate.candidate_id in ranks:
            tier = 1
        else:
            continue
        negatives.append(
            HardNegative(
                candidate_id=candidate.candidate_id,
                tier=tier,
                mass_error_ppm=float(mass_error),
                same_formula=same_formula,
                same_scaffold=same_scaffold,
                target_tanimoto=tanimoto,
                baseline_rank=ranks.get(candidate.candidate_id),
            )
        )
    negatives.sort(
        key=lambda item: (
            -item.tier,
            item.baseline_rank if item.baseline_rank is not None else 10**9,
            -item.target_tanimoto,
            item.mass_error_ppm,
            item.candidate_id,
        )
    )
    selected = negatives[:max_negatives]
    tier_counts = Counter(item.tier for item in selected)
    return selected, HardNegativeSummary(
        selected_count=len(selected),
        same_formula_count=sum(item.same_formula for item in selected),
        same_scaffold_count=sum(item.same_scaffold for item in selected),
        tier_counts=dict(sorted(tier_counts.items())),
    )


class IsomerAwareRanker:
    """Compact candidate ranker with explicit, versioned feature groups."""

    def __init__(
        self,
        feature_names: Sequence[str],
        *,
        random_state: int = 2026,
        backend: str = "hist_gbdt",
    ) -> None:
        self.feature_names = tuple(feature_names)
        if not self.feature_names:
            raise ValueError("At least one ranking feature is required")
        self.backend = backend
        if backend == "hist_gbdt":
            self.model = HistGradientBoostingClassifier(
                learning_rate=0.06,
                max_iter=160,
                max_leaf_nodes=15,
                min_samples_leaf=5,
                l2_regularization=0.2,
                random_state=random_state,
            )
        elif backend == "lightgbm":
            try:
                from lightgbm import LGBMRanker
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("Install the 'goal3' extra to use LightGBM") from exc
            self.model = LGBMRanker(
                objective="lambdarank",
                metric="ndcg",
                n_estimators=160,
                learning_rate=0.05,
                num_leaves=15,
                min_child_samples=5,
                reg_lambda=0.2,
                random_state=random_state,
                verbosity=-1,
            )
        else:
            raise ValueError(f"Unknown ranker backend: {backend}")
        self.is_fitted = False

    def _vector(self, hit: CandidateHit) -> np.ndarray:
        missing = [name for name in self.feature_names if name not in hit.features]
        if missing:
            raise ValueError(f"Missing ranking features: {missing}")
        return np.asarray([hit.features[name] for name in self.feature_names], dtype=np.float64)

    def fit(
        self,
        candidate_groups: Mapping[str, Sequence[CandidateHit]],
        truth_keys: Mapping[str, str],
    ) -> dict[str, int]:
        rows: list[np.ndarray] = []
        labels: list[int] = []
        group_sizes: list[int] = []
        used_queries = 0
        for query_id in sorted(candidate_groups):
            hits = candidate_groups[query_id]
            group_labels = [int(hit.candidate_id == truth_keys[query_id]) for hit in hits]
            if not any(group_labels) or all(group_labels):
                continue
            rows.extend(self._vector(hit) for hit in hits)
            labels.extend(group_labels)
            group_sizes.append(len(hits))
            used_queries += 1
        if not rows or len(set(labels)) < 2:
            raise ValueError("Ranker requires at least one positive and one negative")
        x = np.vstack(rows)
        y = np.asarray(labels, dtype=np.int8)
        if not np.isfinite(x).all():
            raise ValueError("Ranking feature matrix contains NaN or Inf")
        if self.backend == "lightgbm":
            self.model.fit(x, y, group=group_sizes)
        else:
            self.model.fit(x, y)
        self.is_fitted = True
        return {
            "row_count": int(y.size),
            "positive_count": int(y.sum()),
            "negative_count": int((1 - y).sum()),
            "query_count": used_queries,
        }

    def rank(self, hits: Sequence[CandidateHit]) -> list[RankedCandidate]:
        if not self.is_fitted:
            raise ValueError("Ranker is not fitted")
        if not hits:
            return []
        x = np.vstack([self._vector(hit) for hit in hits])
        if self.backend == "lightgbm":
            scores = np.asarray(self.model.predict(x), dtype=np.float64)
        else:
            scores = np.asarray(self.model.predict_proba(x)[:, 1], dtype=np.float64)
        order = sorted(range(len(hits)), key=lambda idx: (-scores[idx], hits[idx].candidate_id))
        return [
            RankedCandidate(
                candidate_id=hits[idx].candidate_id,
                smiles=hits[idx].smiles,
                score=float(scores[idx]),
                rank=rank,
            )
            for rank, idx in enumerate(order, start=1)
        ]
