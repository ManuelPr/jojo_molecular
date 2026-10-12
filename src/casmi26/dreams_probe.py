from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import importlib
import math
from pathlib import Path
from typing import Literal

import numpy as np

from .metrics import RankingMetrics, evaluate_rankings
from .schemas import SpectrumRecord


Aggregation = Literal["max", "mean", "rrf"]


class DreaMSProbeError(ValueError):
    """Raised when a frozen-embedding probe violates its data contract."""


@dataclass(frozen=True, slots=True)
class FrozenEmbeddingIndex:
    """Read-only DreaMS reference embeddings and their structural identities.

    ``embeddings`` may be an ``np.memmap``. Normalization is deliberately done
    block-by-block during search so a multi-million-spectrum index need not be
    duplicated in RAM.
    """

    embeddings: np.ndarray
    reference_ids: tuple[str, ...]
    structure_keys: tuple[str, ...]
    model_name: str = "DreaMS_embedding"
    checkpoint_sha256: str | None = None

    def __post_init__(self) -> None:
        matrix = np.asarray(self.embeddings)
        if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
            raise DreaMSProbeError("Reference embeddings must be a non-empty 2-D matrix")
        if len(self.reference_ids) != matrix.shape[0]:
            raise DreaMSProbeError("reference_ids must align with embedding rows")
        if len(self.structure_keys) != matrix.shape[0]:
            raise DreaMSProbeError("structure_keys must align with embedding rows")
        if len(set(self.reference_ids)) != len(self.reference_ids):
            raise DreaMSProbeError("reference_ids must be unique")
        if any(not value for value in self.reference_ids):
            raise DreaMSProbeError("reference_ids must be non-empty")
        if any(not value for value in self.structure_keys):
            raise DreaMSProbeError("structure_keys must be non-empty")


@dataclass(frozen=True, slots=True)
class DreaMSNeighbor:
    structure_key: str
    similarity: float
    rank: int


@dataclass(frozen=True, slots=True)
class FrozenProbeResult:
    query_id: str
    neighbors: tuple[DreaMSNeighbor, ...]
    reference_structure_count: int
    same_identity_excluded: bool


@dataclass(frozen=True, slots=True)
class ProbeEvaluation:
    metrics: RankingMetrics
    reference_visible_fraction: float
    query_count: int


def _validate_query_matrix(
    embeddings: np.ndarray,
    query_ids: Sequence[str],
    *,
    expected_dim: int,
) -> np.ndarray:
    matrix = np.asarray(embeddings)
    if matrix.ndim != 2 or matrix.shape[1] != expected_dim:
        raise DreaMSProbeError(
            f"Query embeddings must have shape (n, {expected_dim}); got {matrix.shape}"
        )
    if matrix.shape[0] != len(query_ids):
        raise DreaMSProbeError("query_ids must align with query embedding rows")
    if len(set(query_ids)) != len(query_ids):
        raise DreaMSProbeError("query_ids must be unique for per-spectrum search")
    if any(not query_id for query_id in query_ids):
        raise DreaMSProbeError("query_ids must be non-empty")
    if not np.isfinite(matrix).all():
        raise DreaMSProbeError("Query embeddings must be finite")
    norms = np.linalg.norm(matrix, axis=1)
    if np.any(norms <= 0.0):
        raise DreaMSProbeError("Query embeddings must have non-zero norm")
    return matrix.astype(np.float32, copy=False) / norms[:, None].astype(np.float32)


def _structure_encoding(keys: Sequence[str]) -> tuple[tuple[str, ...], np.ndarray]:
    unique_keys = tuple(sorted(set(keys)))
    lookup = {key: idx for idx, key in enumerate(unique_keys)}
    encoded = np.fromiter((lookup[key] for key in keys), dtype=np.int32, count=len(keys))
    return unique_keys, encoded


def search_frozen_embeddings(
    query_embeddings: np.ndarray,
    query_ids: Sequence[str],
    index: FrozenEmbeddingIndex,
    *,
    top_k: int = 80,
    query_structure_keys: Sequence[str | None] | None = None,
    exclude_same_identity: bool = True,
    query_batch_size: int = 32,
    reference_block_size: int = 8_192,
) -> dict[str, FrozenProbeResult]:
    """Exact cosine search aggregated by unique reference structure.

    The function never consults a target structure except to *exclude* that
    identity in an identity-disjoint protocol. Reference blocks are normalized
    on demand and the full spectrum-by-spectrum similarity matrix is never
    materialized.
    """

    if top_k <= 0 or query_batch_size <= 0 or reference_block_size <= 0:
        raise DreaMSProbeError("top_k and block sizes must be positive")
    reference = np.asarray(index.embeddings)
    queries = _validate_query_matrix(
        query_embeddings,
        query_ids,
        expected_dim=reference.shape[1],
    )
    if query_structure_keys is None:
        query_structure_keys = [None] * len(query_ids)
    if len(query_structure_keys) != len(query_ids):
        raise DreaMSProbeError("query_structure_keys must align with query embeddings")

    unique_structures, structure_codes = _structure_encoding(index.structure_keys)
    structure_lookup = {key: idx for idx, key in enumerate(unique_structures)}
    result: dict[str, FrozenProbeResult] = {}

    for query_start in range(0, len(query_ids), query_batch_size):
        query_stop = min(query_start + query_batch_size, len(query_ids))
        query_block = queries[query_start:query_stop]
        best = np.full(
            (query_block.shape[0], len(unique_structures)),
            -np.inf,
            dtype=np.float32,
        )
        for ref_start in range(0, reference.shape[0], reference_block_size):
            ref_stop = min(ref_start + reference_block_size, reference.shape[0])
            raw_block = np.asarray(reference[ref_start:ref_stop], dtype=np.float32)
            if not np.isfinite(raw_block).all():
                raise DreaMSProbeError(
                    f"Reference embeddings contain non-finite values in rows "
                    f"[{ref_start}, {ref_stop})"
                )
            norms = np.linalg.norm(raw_block, axis=1)
            if np.any(norms <= 0.0):
                raise DreaMSProbeError(
                    f"Reference embeddings contain zero-norm rows in "
                    f"[{ref_start}, {ref_stop})"
                )
            normalized = raw_block / norms[:, None]
            similarities = query_block @ normalized.T
            codes = structure_codes[ref_start:ref_stop]
            for local_query in range(query_block.shape[0]):
                np.maximum.at(best[local_query], codes, similarities[local_query])

        for local_query, query_id in enumerate(query_ids[query_start:query_stop]):
            row = best[local_query]
            query_key = query_structure_keys[query_start + local_query]
            excluded = False
            if exclude_same_identity and query_key:
                structure_idx = structure_lookup.get(query_key)
                if structure_idx is not None:
                    row[structure_idx] = -np.inf
                    excluded = True
            finite = np.flatnonzero(np.isfinite(row))
            keep = min(top_k, finite.size)
            if keep:
                if keep < finite.size:
                    selected = finite[np.argpartition(row[finite], -keep)[-keep:]]
                else:
                    selected = finite
                ordered = sorted(
                    selected.tolist(),
                    key=lambda idx: (-float(row[idx]), unique_structures[idx]),
                )
            else:
                ordered = []
            neighbors = tuple(
                DreaMSNeighbor(
                    structure_key=unique_structures[idx],
                    similarity=float(row[idx]),
                    rank=rank,
                )
                for rank, idx in enumerate(ordered, start=1)
            )
            result[query_id] = FrozenProbeResult(
                query_id=query_id,
                neighbors=neighbors,
                reference_structure_count=len(unique_structures),
                same_identity_excluded=excluded,
            )
    return result


def aggregate_frozen_results(
    per_spectrum: Mapping[str, FrozenProbeResult],
    spectrum_to_query: Mapping[str, str],
    *,
    method: Aggregation = "max",
    top_k: int = 80,
    rrf_constant: float = 60.0,
) -> dict[str, FrozenProbeResult]:
    """Aggregate multiple acquisitions without assuming independence."""

    if method not in {"max", "mean", "rrf"}:
        raise DreaMSProbeError(f"Unknown aggregation method: {method}")
    if top_k <= 0 or rrf_constant <= 0.0:
        raise DreaMSProbeError("top_k and rrf_constant must be positive")
    missing = set(per_spectrum) - set(spectrum_to_query)
    if missing:
        raise DreaMSProbeError(f"Missing query mapping for {len(missing)} spectrum/spectra")

    grouped: dict[str, list[FrozenProbeResult]] = defaultdict(list)
    for spectrum_id, item in per_spectrum.items():
        grouped[spectrum_to_query[spectrum_id]].append(item)

    aggregated: dict[str, FrozenProbeResult] = {}
    for query_id, acquisitions in grouped.items():
        scores: dict[str, list[float]] = defaultdict(list)
        for acquisition in acquisitions:
            seen: set[str] = set()
            for neighbor in acquisition.neighbors:
                seen.add(neighbor.structure_key)
                value = (
                    1.0 / (rrf_constant + neighbor.rank)
                    if method == "rrf"
                    else neighbor.similarity
                )
                scores[neighbor.structure_key].append(float(value))
            if method == "mean":
                for key in set(scores) - seen:
                    scores[key].append(0.0)
        if method == "mean":
            n_acquisitions = len(acquisitions)
            reduced = {
                key: float(sum(values) / n_acquisitions) for key, values in scores.items()
            }
        elif method == "max":
            reduced = {key: max(values) for key, values in scores.items()}
        else:
            reduced = {key: sum(values) for key, values in scores.items()}
        ordered = sorted(reduced, key=lambda key: (-reduced[key], key))[:top_k]
        aggregated[query_id] = FrozenProbeResult(
            query_id=query_id,
            neighbors=tuple(
                DreaMSNeighbor(key, reduced[key], rank)
                for rank, key in enumerate(ordered, start=1)
            ),
            reference_structure_count=max(
                item.reference_structure_count for item in acquisitions
            ),
            same_identity_excluded=any(item.same_identity_excluded for item in acquisitions),
        )
    return aggregated


def evaluate_frozen_retrieval(
    truth_keys: Mapping[str, str],
    results: Mapping[str, FrozenProbeResult],
) -> ProbeEvaluation:
    missing = set(truth_keys) - set(results)
    if missing:
        raise DreaMSProbeError(f"Missing frozen-probe results for {len(missing)} query/queries")
    ranked = {
        query_id: [neighbor.structure_key for neighbor in results[query_id].neighbors]
        for query_id in truth_keys
    }
    visible = [
        truth_keys[query_id] in set(ranked[query_id])
        for query_id in truth_keys
    ]
    return ProbeEvaluation(
        metrics=evaluate_rankings(truth_keys, ranked),
        reference_visible_fraction=float(np.mean(visible)),
        query_count=len(truth_keys),
    )


def write_dreams_mgf(records: Sequence[SpectrumRecord], path: str | Path) -> Path:
    """Write an explicit, deterministic MGF boundary for the official API."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            mz = np.asarray(record.mz, dtype=np.float64)
            intensity = np.asarray(record.intensity, dtype=np.float64)
            if mz.ndim != 1 or intensity.shape != mz.shape or mz.size == 0:
                raise DreaMSProbeError(f"Invalid peak arrays for {record.spectrum_id}")
            if not np.isfinite(mz).all() or not np.isfinite(intensity).all():
                raise DreaMSProbeError(f"Non-finite peaks for {record.spectrum_id}")
            if not math.isfinite(record.precursor_mz) or record.precursor_mz <= 0.0:
                raise DreaMSProbeError(f"Invalid precursor m/z for {record.spectrum_id}")
            title = record.spectrum_id.replace("\n", " ").replace("\r", " ")
            handle.write("BEGIN IONS\n")
            handle.write(f"TITLE={title}\n")
            handle.write(f"PEPMASS={record.precursor_mz:.10f}\n")
            if record.ion_mode:
                handle.write(f"IONMODE={record.ion_mode}\n")
            for peak_mz, peak_intensity in zip(mz, intensity, strict=True):
                handle.write(f"{peak_mz:.10f} {peak_intensity:.10g}\n")
            handle.write("END IONS\n\n")
    return destination


def compute_official_dreams_embeddings(
    spectra_path: str | Path,
    *,
    checkpoint_path: str | Path | None = None,
    batch_size: int = 32,
) -> np.ndarray:
    """Call the upstream frozen API lazily; no training path is exposed."""

    if batch_size <= 0:
        raise DreaMSProbeError("batch_size must be positive")
    try:
        api = importlib.import_module("dreams.api")
    except ImportError as exc:
        raise RuntimeError(
            "The optional upstream DreaMS environment is unavailable. "
            "Run this probe in the separately pinned Python 3.11 Kaggle environment."
        ) from exc
    kwargs: dict[str, object] = {
        "batch_size": batch_size,
        "progress_bar": False,
        "store_embs": False,
    }
    if checkpoint_path is not None:
        checkpoint = Path(checkpoint_path)
        if not checkpoint.is_file():
            raise FileNotFoundError(checkpoint)
        kwargs["model_pth"] = checkpoint
    embeddings = np.asarray(api.dreams_embeddings(Path(spectra_path), **kwargs))
    if embeddings.ndim != 2 or not np.isfinite(embeddings).all():
        raise DreaMSProbeError("Official DreaMS API returned invalid embeddings")
    return embeddings.astype(np.float32, copy=False)
