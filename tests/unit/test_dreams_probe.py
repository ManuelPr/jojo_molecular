from __future__ import annotations

import builtins

import numpy as np
import pytest

from casmi26.dreams_probe import (
    DreaMSProbeError,
    FrozenEmbeddingIndex,
    aggregate_frozen_results,
    compute_official_dreams_embeddings,
    evaluate_frozen_retrieval,
    search_frozen_embeddings,
    write_dreams_mgf,
)
from casmi26.schemas import SpectrumRecord


def _index() -> FrozenEmbeddingIndex:
    return FrozenEmbeddingIndex(
        embeddings=np.asarray(
            [
                [1.0, 0.0],
                [0.8, 0.2],
                [0.0, 1.0],
                [-1.0, 0.0],
            ],
            dtype=np.float32,
        ),
        reference_ids=("a-1", "a-2", "b-1", "c-1"),
        structure_keys=("A", "A", "B", "C"),
        checkpoint_sha256="abc",
    )


def test_frozen_search_is_structure_deduplicated_and_chunk_invariant() -> None:
    queries = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    first = search_frozen_embeddings(
        queries,
        ["q1", "q2"],
        _index(),
        top_k=3,
        query_batch_size=1,
        reference_block_size=1,
        exclude_same_identity=False,
    )
    second = search_frozen_embeddings(
        queries,
        ["q1", "q2"],
        _index(),
        top_k=3,
        query_batch_size=4,
        reference_block_size=99,
        exclude_same_identity=False,
    )
    assert first == second
    assert [neighbor.structure_key for neighbor in first["q1"].neighbors] == ["A", "B", "C"]
    assert [neighbor.structure_key for neighbor in first["q2"].neighbors] == ["B", "A", "C"]


def test_frozen_search_uses_truth_only_for_exclusion() -> None:
    results = search_frozen_embeddings(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        ["q"],
        _index(),
        query_structure_keys=["A"],
        top_k=2,
    )
    assert results["q"].same_identity_excluded
    assert [neighbor.structure_key for neighbor in results["q"].neighbors] == ["B", "C"]


def test_frozen_search_rejects_invalid_embeddings() -> None:
    with pytest.raises(DreaMSProbeError, match="non-zero norm"):
        search_frozen_embeddings(np.zeros((1, 2)), ["q"], _index())
    bad = FrozenEmbeddingIndex(
        embeddings=np.asarray([[np.nan, 1.0]], dtype=np.float32),
        reference_ids=("x",),
        structure_keys=("X",),
    )
    with pytest.raises(DreaMSProbeError, match="non-finite"):
        search_frozen_embeddings(np.ones((1, 2)), ["q"], bad)


def test_multi_spectrum_aggregation_and_evaluation() -> None:
    per_spectrum = search_frozen_embeddings(
        np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        ["s1", "s2"],
        _index(),
        top_k=3,
        exclude_same_identity=False,
    )
    maximum = aggregate_frozen_results(
        per_spectrum,
        {"s1": "molecule", "s2": "molecule"},
        method="max",
        top_k=3,
    )
    assert maximum["molecule"].neighbors[0].structure_key in {"A", "B"}
    evaluation = evaluate_frozen_retrieval({"molecule": "B"}, maximum)
    assert evaluation.query_count == 1
    assert evaluation.reference_visible_fraction == 1.0
    assert evaluation.metrics.recall_at_25 == 1.0


def test_write_dreams_mgf_has_deterministic_boundary(tmp_path) -> None:
    record = SpectrumRecord(
        spectrum_id="spec-1",
        molecule_id="mol-1",
        mz=np.asarray([50.0, 75.123456789]),
        intensity=np.asarray([1.0, 0.5]),
        precursor_mz=100.0,
        adduct="[M+H]+",
        ion_mode="positive",
    )
    output = write_dreams_mgf([record], tmp_path / "probe.mgf")
    text = output.read_text(encoding="utf-8")
    assert "BEGIN IONS\nTITLE=spec-1\nPEPMASS=100.0000000000" in text
    assert "75.1234567890 0.5" in text
    assert text.endswith("END IONS\n\n")


def test_official_api_is_an_explicit_optional_dependency(monkeypatch, tmp_path) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "dreams.api":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("importlib.import_module", lambda name: guarded_import(name))
    with pytest.raises(RuntimeError, match="optional upstream DreaMS"):
        compute_official_dreams_embeddings(tmp_path / "missing.mgf")
