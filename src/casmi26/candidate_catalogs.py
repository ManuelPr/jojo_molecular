"""Catalog expansion contracts, coverage accounting and compact mass indices.

No network access occurs in this module.  Source metadata records the official
download and licensing evidence that must be rechecked when an artifact is
built.  Large catalogs are expected to be streamed, canonicalised with the
competition RDKit version and stored as columnar/memory-mapped artifacts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Literal

import numpy as np


LicenseStatus = Literal["compatible", "review_required", "incompatible"]


@dataclass(frozen=True, slots=True)
class CatalogSourceSpec:
    name: str
    official_url: str
    download_url: str
    license_name: str
    license_status: LicenseStatus
    approximate_structure_count: int | None
    observed_date: str
    scope: str
    recommended_tier: int
    notes: str = ""

    def __post_init__(self) -> None:
        if self.license_status not in ("compatible", "review_required", "incompatible"):
            raise ValueError(f"Invalid license status: {self.license_status!r}")
        if self.recommended_tier < 0:
            raise ValueError("recommended_tier must be non-negative")


def official_catalog_registry() -> tuple[CatalogSourceSpec, ...]:
    """Return the dated, source-specific expansion registry.

    ``PubChem`` is deliberately marked ``review_required``.  PubChem Compound
    records are broadly downloadable, but contributed annotations can carry
    source-specific terms.  A competition artifact should therefore keep only
    the structural fields needed for retrieval and retain depositor provenance.
    """

    return (
        CatalogSourceSpec(
            name="COCONUT",
            official_url="https://coconut.naturalproducts.net/about",
            download_url="https://coconut.naturalproducts.net/download",
            license_name="CC0 curated dataset",
            license_status="compatible",
            approximate_structure_count=None,
            observed_date="2026-10-09",
            scope="curated natural products aggregated from open sources",
            recommended_tier=1,
            notes="High domain relevance; canonicalize and measure overlap before union.",
        ),
        CatalogSourceSpec(
            name="ChEBI",
            official_url="https://www.ebi.ac.uk/chebi/about",
            download_url="https://www.ebi.ac.uk/chebi/downloads",
            license_name="CC BY 4.0",
            license_status="compatible",
            approximate_structure_count=195_000,
            observed_date="2026-10-09",
            scope="biologically relevant chemical entities; mixed entity/ontology records",
            recommended_tier=1,
            notes="Prefer SDF FULL or CORE-like structural fields; retain attribution.",
        ),
        CatalogSourceSpec(
            name="LIPID MAPS LMSD",
            official_url="https://www.lipidmaps.org/databases",
            download_url="https://www.lipidmaps.org/databases/lmsd/download",
            license_name="CC BY 4.0 SDF; CC0 ID/InChIKey/SMILES TSV",
            license_status="compatible",
            approximate_structure_count=50_586,
            observed_date="2026-10-09",
            scope="curated biologically relevant lipids",
            recommended_tier=1,
            notes="Small enough for early ablation; use exact structures, not bulk sums.",
        ),
        CatalogSourceSpec(
            name="PubChem Compound",
            official_url="https://pubchem.ncbi.nlm.nih.gov/docs/statistics",
            download_url="https://pubchem.ncbi.nlm.nih.gov/docs/downloads",
            license_name="NCBI/NLM terms plus contributor-specific provenance",
            license_status="review_required",
            approximate_structure_count=124_663_543,
            observed_date="2026-09-06",
            scope="broad unique standardized chemical structures",
            recommended_tier=2,
            notes=(
                "Do not bulk-attach the full archive to Kaggle. Build a mass/formula-filtered "
                "structure-only tier offline after rules and source terms are reviewed."
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    candidate_id: str
    inchikey14: str
    smiles: str
    exact_mass: float
    formula: str | None
    sources: tuple[str, ...]
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.inchikey14 or not self.smiles:
            raise ValueError("candidate_id, inchikey14 and smiles are required")
        if not math.isfinite(self.exact_mass) or self.exact_mass <= 0:
            raise ValueError("exact_mass must be finite and positive")
        if not self.sources:
            raise ValueError("At least one source is required")


@dataclass(frozen=True, slots=True)
class CatalogMergeReport:
    input_records: int
    unique_records: int
    duplicate_records: int
    source_counts_before: Mapping[str, int]
    source_counts_after: Mapping[str, int]
    overlap_source_sets: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_records": self.input_records,
            "unique_records": self.unique_records,
            "duplicate_records": self.duplicate_records,
            "source_counts_before": dict(self.source_counts_before),
            "source_counts_after": dict(self.source_counts_after),
            "overlap_source_sets": dict(self.overlap_source_sets),
        }


def deduplicate_catalog_records(
    records: Iterable[CatalogRecord],
) -> tuple[tuple[CatalogRecord, ...], CatalogMergeReport]:
    """Deduplicate by InChIKey14 while preserving all provenance."""

    materialized = tuple(records)
    grouped: dict[str, list[CatalogRecord]] = defaultdict(list)
    before = Counter(source for record in materialized for source in record.sources)
    for record in materialized:
        grouped[record.inchikey14.upper()[:14]].append(record)

    output: list[CatalogRecord] = []
    after: Counter[str] = Counter()
    overlaps: Counter[str] = Counter()
    for key in sorted(grouped):
        members = grouped[key]
        representative = min(members, key=lambda item: (item.candidate_id, item.smiles))
        sources = tuple(sorted({source for item in members for source in item.sources}))
        source_ids = tuple(sorted({value for item in members for value in item.source_ids}))
        after.update(sources)
        overlaps["+".join(sources)] += 1
        output.append(
            CatalogRecord(
                candidate_id=representative.candidate_id,
                inchikey14=key,
                smiles=representative.smiles,
                exact_mass=representative.exact_mass,
                formula=representative.formula,
                sources=sources,
                source_ids=source_ids,
            )
        )
    report = CatalogMergeReport(
        input_records=len(materialized),
        unique_records=len(output),
        duplicate_records=len(materialized) - len(output),
        source_counts_before=dict(sorted(before.items())),
        source_counts_after=dict(sorted(after.items())),
        overlap_source_sets=dict(sorted(overlaps.items())),
    )
    return tuple(output), report


def exclude_holdout_identities(
    records: Sequence[CatalogRecord],
    excluded_inchikey14: Sequence[str],
) -> tuple[CatalogRecord, ...]:
    """Remove novelty-holdout identities before index construction."""

    excluded = {str(value).upper()[:14] for value in excluded_inchikey14}
    return tuple(record for record in records if record.inchikey14.upper()[:14] not in excluded)


@dataclass(frozen=True, slots=True)
class MassIndexArrays:
    masses: np.ndarray
    candidate_ids: np.ndarray
    formulas: np.ndarray

    def __post_init__(self) -> None:
        if not (len(self.masses) == len(self.candidate_ids) == len(self.formulas)):
            raise ValueError("Mass index arrays must have equal lengths")
        if self.masses.ndim != 1:
            raise ValueError("Mass index arrays must be one-dimensional")
        if len(self.masses) and np.any(np.diff(self.masses) < 0):
            raise ValueError("Masses must be sorted")


def build_mass_index_arrays(records: Sequence[CatalogRecord]) -> MassIndexArrays:
    """Build deterministic compact arrays suitable for ``numpy.save``/mmap."""

    ordered = sorted(records, key=lambda item: (item.exact_mass, item.inchikey14))
    max_id = max((len(item.candidate_id) for item in ordered), default=1)
    max_formula = max((len(item.formula or "") for item in ordered), default=1)
    return MassIndexArrays(
        masses=np.asarray([item.exact_mass for item in ordered], dtype=np.float64),
        candidate_ids=np.asarray(
            [item.candidate_id for item in ordered], dtype=f"U{max_id}"
        ),
        formulas=np.asarray(
            [item.formula or "" for item in ordered], dtype=f"U{max_formula}"
        ),
    )


def search_mass_index(
    index: MassIndexArrays,
    neutral_mass: float,
    *,
    tolerance_ppm: float,
    formula: str | None = None,
    limit: int | None = None,
) -> tuple[str, ...]:
    """Search a sorted exact-mass index with deterministic ppm/id ordering."""

    if not math.isfinite(neutral_mass) or neutral_mass <= 0:
        raise ValueError("neutral_mass must be finite and positive")
    if not math.isfinite(tolerance_ppm) or tolerance_ppm <= 0:
        raise ValueError("tolerance_ppm must be finite and positive")
    if limit is not None and limit <= 0:
        return ()
    delta = neutral_mass * tolerance_ppm * 1e-6
    left = int(np.searchsorted(index.masses, neutral_mass - delta, side="left"))
    right = int(np.searchsorted(index.masses, neutral_mass + delta, side="right"))
    positions = np.arange(left, right)
    if formula is not None:
        positions = positions[index.formulas[positions] == formula]
    positions = positions[
        np.lexsort(
            (
                index.candidate_ids[positions],
                np.abs(index.masses[positions] - neutral_mass),
            )
        )
    ]
    if limit is not None:
        positions = positions[:limit]
    return tuple(str(value) for value in index.candidate_ids[positions])


def save_mass_index(index: MassIndexArrays, directory: str | Path) -> dict[str, str]:
    """Persist independent arrays that can later be opened with mmap_mode='r'."""

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "masses": target / "masses.npy",
        "candidate_ids": target / "candidate_ids.npy",
        "formulas": target / "formulas.npy",
    }
    np.save(paths["masses"], index.masses, allow_pickle=False)
    np.save(paths["candidate_ids"], index.candidate_ids, allow_pickle=False)
    np.save(paths["formulas"], index.formulas, allow_pickle=False)
    return {name: str(path) for name, path in paths.items()}


def load_mass_index(directory: str | Path, *, mmap: bool = True) -> MassIndexArrays:
    target = Path(directory)
    mode = "r" if mmap else None
    return MassIndexArrays(
        masses=np.load(target / "masses.npy", mmap_mode=mode, allow_pickle=False),
        candidate_ids=np.load(
            target / "candidate_ids.npy", mmap_mode=mode, allow_pickle=False
        ),
        formulas=np.load(target / "formulas.npy", mmap_mode=mode, allow_pickle=False),
    )


def pack_fingerprints(fingerprints: np.ndarray) -> np.ndarray:
    values = np.asarray(fingerprints)
    if values.ndim != 2:
        raise ValueError("fingerprints must be a two-dimensional array")
    if not np.all((values == 0) | (values == 1)):
        raise ValueError("fingerprints must be binary")
    return np.packbits(values.astype(np.uint8), axis=1, bitorder="little")


def unpack_fingerprints(packed: np.ndarray, *, n_bits: int) -> np.ndarray:
    if n_bits <= 0:
        raise ValueError("n_bits must be positive")
    values = np.asarray(packed, dtype=np.uint8)
    if values.ndim != 2:
        raise ValueError("packed fingerprints must be two-dimensional")
    return np.unpackbits(values, axis=1, count=n_bits, bitorder="little")


def estimate_catalog_resources(
    structure_count: int,
    *,
    fingerprint_bits: int = 2048,
    mean_smiles_bytes: int = 64,
    mean_formula_bytes: int = 20,
    metadata_overhead_bytes: int = 32,
) -> dict[str, Any]:
    """Estimate lower-bound columnar storage, not Python-object memory."""

    if structure_count < 0 or fingerprint_bits <= 0:
        raise ValueError("Invalid structure count or fingerprint size")
    fingerprint_bytes = math.ceil(fingerprint_bits / 8)
    per_record = (
        8  # exact mass float64
        + 14  # InChIKey14 ASCII
        + fingerprint_bytes
        + mean_smiles_bytes
        + mean_formula_bytes
        + metadata_overhead_bytes
    )
    total = structure_count * per_record
    return {
        "structure_count": structure_count,
        "fingerprint_bits": fingerprint_bits,
        "fingerprint_bytes_per_record": fingerprint_bytes,
        "estimated_columnar_bytes_per_record": per_record,
        "estimated_columnar_bytes": total,
        "estimated_columnar_gib": total / (1024**3),
        "caveat": (
            "Lower-bound artifact estimate; parse/build intermediates and Python/RDKit "
            "objects can require several times more RAM."
        ),
    }


def evaluate_catalog_coverage(
    catalogs: Mapping[str, Sequence[CatalogRecord]],
    truth_keys: Sequence[str],
) -> dict[str, Any]:
    """Measure per-source and progressive-union identity coverage."""

    truths = {str(value).upper()[:14] for value in truth_keys}
    union: set[str] = set()
    sources: dict[str, Any] = {}
    progressive: dict[str, Any] = {}
    for name, records in catalogs.items():
        identities = {record.inchikey14.upper()[:14] for record in records}
        recovered = identities & truths
        sources[name] = {
            "structure_count": len(identities),
            "recovered_count": len(recovered),
            "recall": len(recovered) / len(truths) if truths else 0.0,
            "marginal_recovered_vs_previous_union": len(recovered - union),
        }
        union |= identities
        progressive[name] = {
            "union_structure_count": len(union),
            "union_recovered_count": len(union & truths),
            "union_recall": len(union & truths) / len(truths) if truths else 0.0,
        }
    return {
        "truth_count": len(truths),
        "sources": sources,
        "progressive_union": progressive,
    }
