from __future__ import annotations

import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from casmi26.chemistry import canonical_inchikey14
from casmi26.scalable_retrieval import (
    INDEX_BACKEND,
    CandidateChannel,
    DynamicPoolConfig,
    RetrievalCache,
    RetrievalRequest,
    ScalableMassFormulaIndex,
    apply_staged_reranking,
    batch_retrieve_dynamic_pools,
    build_streaming_structure_catalog,
    iter_parquet_structure_rows,
    retrieve_dynamic_pool,
    union_candidate_channels,
)


def _rows() -> list[dict[str, object]]:
    ethanol = canonical_inchikey14("CCO")
    propanol = canonical_inchikey14("CCCO")
    ether = canonical_inchikey14("CCOC")
    butanol = canonical_inchikey14("CCCCO")
    assert ethanol and propanol and ether and butanol
    return [
        {
            "molecule_id": "m1",
            "normalized_smiles": "CCO",
            "inchikey14": ethanol,
            "molecular_formula": "C2H6O",
            "ingest_lib": "train_a",
        },
        {
            "molecule_id": "m1b",
            "normalized_smiles": "OCC",
            "inchikey14": ethanol,
            "molecular_formula": "C2H6O",
            "ingest_lib": "train_b",
        },
        {
            "molecule_id": "m2",
            "normalized_smiles": "CCCO",
            "inchikey14": propanol,
            "molecular_formula": "C3H8O",
            "ingest_lib": "train_a",
        },
        {
            "molecule_id": "m3",
            "normalized_smiles": "CCOC",
            "inchikey14": ether,
            "molecular_formula": "C3H8O",
            "ingest_lib": "external",
        },
        {
            "molecule_id": "m4",
            "normalized_smiles": "CCCCO",
            "inchikey14": butanol,
            "molecular_formula": "C4H10O",
            "ingest_lib": "external",
        },
    ]


def _catalog():
    records, report = build_streaming_structure_catalog(_rows())
    assert report.unique_structure_count == 4
    return records


def test_streaming_catalog_deduplicates_spectra_and_preserves_provenance() -> None:
    rows = _rows()
    rows.extend([dict(rows[2]), {"normalized_smiles": None, "inchikey14": None}])
    records, report = build_streaming_structure_catalog(rows)
    ethanol = canonical_inchikey14("CCO")
    assert ethanol is not None
    item = next(record for record in records if record.inchikey14 == ethanol)
    assert item.sources == ("train_a", "train_b")
    assert item.source_ids == ("m1", "m1b")
    assert report.input_rows == 7
    assert report.provisional_identity_count == 4
    assert report.unique_structure_count == 4
    assert report.missing_smiles_rows == 1
    assert report.conflicting_smiles_identity_count == 1
    assert report.canonicalization_rule == "rdkit_tautomer_canonical_inchikey14"


def test_catalog_fails_closed_on_mismatch_and_excludes_holdout_before_emit() -> None:
    rows = _rows()
    rows.append(
        {
            "molecule_id": "bad",
            "normalized_smiles": "CCN",
            "inchikey14": "AAAAAAAAAAAAAA",
            "molecular_formula": "C2H7N",
            "ingest_lib": "bad",
        }
    )
    excluded = canonical_inchikey14("CCCO")
    assert excluded is not None
    records, report = build_streaming_structure_catalog(
        rows, excluded_inchikey14=(excluded,)
    )
    assert excluded not in {record.inchikey14 for record in records}
    assert report.canonical_identity_mismatch_count == 1
    assert report.excluded_holdout_count == 1


def test_parquet_reader_selects_only_structure_metadata(tmp_path) -> None:
    path = tmp_path / "train.parquet"
    rows = _rows()[:2]
    table = pa.Table.from_pylist(
        [
            {
                **row,
                "ms2_mzs": [10.0, 20.0],
                "ms2_normalized_intensities": [1.0, 0.5],
            }
            for row in rows
        ]
    )
    pq.write_table(table, path)
    observed = list(iter_parquet_structure_rows(path, batch_size=1))
    assert len(observed) == 2
    assert "ms2_mzs" not in observed[0]
    assert set(observed[0]) == {
        "molecule_id",
        "normalized_smiles",
        "inchikey14",
        "molecular_formula",
        "ingest_lib",
    }


def test_sorted_index_round_trip_formula_lookup_and_manifest(tmp_path) -> None:
    records = _catalog()
    index = ScalableMassFormulaIndex.build(records, tier_name="C1_train_unique")
    assert np.all(np.diff(index.masses) >= 0)
    target_mass = next(record.exact_mass for record in records if record.formula == "C3H8O")
    mass_hits = index.retrieve(target_mass, top_k=10, tolerance_ppm=200_000)
    formula_hits = index.retrieve(
        target_mass, top_k=10, tolerance_ppm=200_000, formula="C3H8O"
    )
    assert formula_hits
    assert all(hit.metadata["formula"] == "C3H8O" for hit in formula_hits)
    assert len(mass_hits) >= len(formula_hits)

    manifest = index.save(tmp_path / "index")
    assert manifest.backend == INDEX_BACKEND
    payload = json.loads((tmp_path / "index" / "manifest.json").read_text())
    assert payload["tier_name"] == "C1_train_unique"
    assert payload["structure_count"] == 4
    restored = ScalableMassFormulaIndex.load(tmp_path / "index", mmap=True)
    assert isinstance(restored.masses, np.memmap)
    materialized = restored.to_catalog_records()
    assert len(materialized) == len(records)
    assert {item.inchikey14 for item in materialized} == {
        item.inchikey14 for item in records
    }
    assert all(item.sources for item in materialized)
    assert [hit.candidate_id for hit in restored.retrieve(target_mass, top_k=3)] == [
        hit.candidate_id for hit in index.retrieve(target_mass, top_k=3)
    ]


def test_index_checksum_validation_is_fail_closed(tmp_path) -> None:
    index = ScalableMassFormulaIndex.build(_catalog(), tier_name="C0")
    index.save(tmp_path)
    masses = tmp_path / "masses.npy"
    with masses.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="checksum"):
        ScalableMassFormulaIndex.load(tmp_path, verify_hashes=True)


def test_dynamic_pool_expands_then_falls_back_and_preserves_e6_anchor() -> None:
    index = ScalableMassFormulaIndex.build(_catalog(), tier_name="C1")
    mass = float(index.masses[1])
    config = DynamicPoolConfig(
        ppm_schedule=(1.0, 5.0),
        target_pool_size=3,
        maximum_pool_size=4,
        cheap_stage_size=3,
        expensive_stage_size=2,
    )
    pool = retrieve_dynamic_pool(index, mass, config=config, formula_hint="C3H8O")
    baseline = index.retrieve(mass, top_k=3)
    assert pool.used_nearest_mass_fallback
    assert pool.mass_anchor_candidate_id == baseline[0].candidate_id
    assert [hit.candidate_id for hit in pool.hits] == [
        hit.candidate_id for hit in baseline
    ]
    assert pool.formula_match_count >= 1
    assert len(pool.cheap_stage_candidate_ids) == 3
    assert len(pool.expensive_stage_candidate_ids) == 2


def test_dense_dynamic_pool_uses_smallest_sufficient_window() -> None:
    records = _catalog()
    index = ScalableMassFormulaIndex.build(records, tier_name="C1")
    mass = next(record.exact_mass for record in records if record.formula == "C3H8O")
    config = DynamicPoolConfig(
        ppm_schedule=(1.0, 10.0, 100_000.0),
        target_pool_size=2,
        maximum_pool_size=4,
        cheap_stage_size=2,
        expensive_stage_size=1,
    )
    pool = retrieve_dynamic_pool(index, mass, config=config)
    assert pool.selected_ppm in config.ppm_schedule
    assert len(pool.hits) >= 2
    assert not pool.used_nearest_mass_fallback


def test_candidate_union_deduplicates_identity_and_preserves_channel_ranks() -> None:
    index = ScalableMassFormulaIndex.build(_catalog(), tier_name="C1")
    first = index.retrieve(float(index.masses[0]), top_k=3)
    second = [_ for _ in reversed(index.retrieve(float(index.masses[1]), top_k=3))]
    result = union_candidate_channels(
        (
            CandidateChannel("exact_mass", first, 1.0),
            CandidateChannel("analog", second, 0.5),
        )
    )
    assert len({hit.candidate_id for hit in result}) == len(result)
    overlap = set(hit.candidate_id for hit in first) & set(hit.candidate_id for hit in second)
    observed = next(hit for hit in result if hit.candidate_id in overlap)
    assert observed.metadata["candidate_channels"] == ["analog", "exact_mass"]
    assert set(observed.metadata["channel_ranks"]) == {"analog", "exact_mass"}


def test_cache_batching_and_resource_report_are_deterministic() -> None:
    index = ScalableMassFormulaIndex.build(_catalog(), tier_name="C1")
    config = DynamicPoolConfig(
        ppm_schedule=(5.0, 50.0),
        target_pool_size=2,
        maximum_pool_size=4,
        cheap_stage_size=2,
        expensive_stage_size=1,
    )
    cache = RetrievalCache(max_entries=2)
    mass = float(index.masses[0])
    requests = (RetrievalRequest("q1", mass), RetrievalRequest("q2", mass))
    pools, report = batch_retrieve_dynamic_pools(
        index, requests, config=config, cache=cache
    )
    assert list(pools) == ["q1", "q2"]
    assert report.cache_misses_delta == 1
    assert report.cache_hits_delta == 1
    assert report.index_array_bytes > 0
    assert report.backend == INDEX_BACKEND
    pools["q1"].hits[0].metadata["mutation"] = True
    cached = cache.get(RetrievalCache.key(mass, None, config, index.tier_name))
    assert cached is not None
    assert "mutation" not in cached.hits[0].metadata


def test_staged_reranking_bounds_expensive_work_without_dropping_candidates() -> None:
    index = ScalableMassFormulaIndex.build(_catalog(), tier_name="C1")
    config = DynamicPoolConfig(
        ppm_schedule=(5.0,),
        target_pool_size=4,
        maximum_pool_size=4,
        cheap_stage_size=3,
        expensive_stage_size=2,
    )
    pool = retrieve_dynamic_pool(index, float(index.masses[0]), config=config)
    result = apply_staged_reranking(
        pool,
        cheap_score=lambda hit: float(hit.metadata["exact_mass"]),
        expensive_score=lambda hit: -float(hit.metadata["exact_mass"]),
    )
    assert result.cheap_scored_count == 3
    assert result.expensive_scored_count == 2
    assert set(result.ranking) == {hit.candidate_id for hit in pool.hits}
    assert result.mass_anchor_candidate_id == pool.mass_anchor_candidate_id


def test_invalid_dynamic_and_duplicate_batch_contracts_fail_fast() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        DynamicPoolConfig(ppm_schedule=(10.0, 5.0))
    index = ScalableMassFormulaIndex.build(_catalog(), tier_name="C1")
    mass = float(index.masses[0])
    with pytest.raises(ValueError, match="unique"):
        batch_retrieve_dynamic_pools(
            index,
            (RetrievalRequest("q", mass), RetrievalRequest("q", mass)),
        )
