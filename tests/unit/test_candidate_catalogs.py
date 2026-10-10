from __future__ import annotations

import numpy as np
import pytest

from casmi26.candidate_catalogs import (
    CatalogRecord,
    build_mass_index_arrays,
    deduplicate_catalog_records,
    estimate_catalog_resources,
    evaluate_catalog_coverage,
    exclude_holdout_identities,
    load_mass_index,
    official_catalog_registry,
    pack_fingerprints,
    save_mass_index,
    search_mass_index,
    unpack_fingerprints,
)


def _record(
    candidate_id: str,
    key: str,
    mass: float,
    formula: str,
    source: str,
) -> CatalogRecord:
    return CatalogRecord(candidate_id, key, "C", mass, formula, (source,), (candidate_id,))


def test_registry_tracks_official_license_risk_and_scale() -> None:
    registry = {item.name: item for item in official_catalog_registry()}
    assert registry["COCONUT"].license_status == "compatible"
    assert registry["ChEBI"].license_name == "CC BY 4.0"
    assert registry["LIPID MAPS LMSD"].recommended_tier == 1
    assert registry["PubChem Compound"].license_status == "review_required"
    assert registry["PubChem Compound"].approximate_structure_count == 124_663_543


def test_catalog_deduplication_preserves_all_sources() -> None:
    records = (
        _record("A", "AAAAAAAAAAAAAA", 100.0, "C5H8O2", "train"),
        _record("A2", "AAAAAAAAAAAAAA", 100.0, "C5H8O2", "COCONUT"),
        _record("B", "BBBBBBBBBBBBBB", 101.0, "C5H10O2", "ChEBI"),
    )
    merged, report = deduplicate_catalog_records(records)
    assert len(merged) == 2
    first = next(item for item in merged if item.inchikey14 == "AAAAAAAAAAAAAA")
    assert first.sources == ("COCONUT", "train")
    assert first.source_ids == ("A", "A2")
    assert report.duplicate_records == 1
    assert report.source_counts_after == {"COCONUT": 1, "ChEBI": 1, "train": 1}


def test_mass_index_matches_window_formula_and_tie_breaking(tmp_path) -> None:
    records = (
        _record("B", "BBBBBBBBBBBBBB", 100.0004, "C5H8O2", "x"),
        _record("A", "AAAAAAAAAAAAAA", 99.9996, "C5H8O2", "x"),
        _record("C", "CCCCCCCCCCCCCC", 100.0004, "C6H12O", "x"),
        _record("D", "DDDDDDDDDDDDDD", 100.0020, "C5H8O2", "x"),
    )
    index = build_mass_index_arrays(records)
    assert search_mass_index(index, 100.0, tolerance_ppm=5) == ("A", "B", "C")
    assert search_mass_index(
        index, 100.0, tolerance_ppm=5, formula="C5H8O2"
    ) == ("A", "B")
    assert search_mass_index(index, 100.0, tolerance_ppm=50, limit=2) == ("A", "B")

    paths = save_mass_index(index, tmp_path)
    assert set(paths) == {"masses", "candidate_ids", "formulas"}
    restored = load_mass_index(tmp_path, mmap=True)
    assert isinstance(restored.masses, np.memmap)
    assert search_mass_index(restored, 100.0, tolerance_ppm=5) == ("A", "B", "C")


def test_holdout_filter_and_progressive_coverage() -> None:
    a = _record("A", "AAAAAAAAAAAAAA", 100.0, "C", "train")
    b = _record("B", "BBBBBBBBBBBBBB", 101.0, "C", "COCONUT")
    c = _record("C", "CCCCCCCCCCCCCC", 102.0, "C", "ChEBI")
    assert exclude_holdout_identities((a, b, c), ("BBBBBBBBBBBBBB",)) == (a, c)

    report = evaluate_catalog_coverage(
        {"train": (a,), "COCONUT": (a, b), "ChEBI": (c,)},
        ("AAAAAAAAAAAAAA", "BBBBBBBBBBBBBB", "ZZZZZZZZZZZZZZ"),
    )
    assert report["sources"]["COCONUT"]["recall"] == pytest.approx(2 / 3)
    assert report["sources"]["COCONUT"]["marginal_recovered_vs_previous_union"] == 1
    assert report["progressive_union"]["ChEBI"]["union_recall"] == pytest.approx(2 / 3)


def test_bitpacked_fingerprints_round_trip_and_storage_estimate() -> None:
    fingerprints = np.asarray([[1, 0, 1, 1, 0], [0, 1, 0, 0, 1]], dtype=np.uint8)
    packed = pack_fingerprints(fingerprints)
    assert packed.shape == (2, 1)
    np.testing.assert_array_equal(unpack_fingerprints(packed, n_bits=5), fingerprints)

    estimate = estimate_catalog_resources(1_000_000, fingerprint_bits=2048)
    assert estimate["fingerprint_bytes_per_record"] == 256
    assert estimate["estimated_columnar_bytes"] > 256_000_000


def test_invalid_fingerprints_fail_fast() -> None:
    with pytest.raises(ValueError):
        pack_fingerprints(np.asarray([0, 1]))
    with pytest.raises(ValueError):
        pack_fingerprints(np.asarray([[0, 2]]))

