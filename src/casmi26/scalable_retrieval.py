"""Scalable, deterministic catalog construction and candidate retrieval.

The module is deliberately structure-only: it never consults query identities or
labels.  It provides the C0/C1/external-tier substrate used before Goal 4's E6
reranker.  Exact mass remains the mandatory fallback and the first mass-ranked
candidate is recorded explicitly so E6's mass-anchor contract cannot change
silently.

Large inputs are streamed from Parquet in batches.  Memory use during catalog
construction is proportional to the number of unique structures, not the number
of spectra.  The on-disk index uses sorted NumPy arrays and compact UTF-8 blobs;
it can be opened with memory mapping in an offline Kaggle runtime.
"""

from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import time
from typing import Any
import copy

import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.MolStandardize import rdMolStandardize

from .candidate_catalogs import CatalogRecord, deduplicate_catalog_records
from .chemistry import rdkit_version
from .retrieval import FEATURE_NAMES
from .schemas import CandidateHit


INDEX_SCHEMA_VERSION = 1
INDEX_BACKEND = "numpy_sorted_mass_searchsorted"
_TAUTOMER_ENUMERATOR = rdMolStandardize.TautomerEnumerator()


def _text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if bool(value != value):  # NaN / pandas.NA-like values.
            return None
    except (TypeError, ValueError):
        pass
    output = str(value).strip()
    return output or None


def _identity(value: object) -> str | None:
    output = _text(value)
    if output is None:
        return None
    output = output.upper()[:14]
    return output if len(output) == 14 and output.isalpha() else None


def _canonical_structure(smiles: str) -> tuple[str, str, float, str] | None:
    """Canonicalize once and derive every structural field from the same mol."""

    try:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            return None
        canonical = _TAUTOMER_ENUMERATOR.Canonicalize(molecule)
        key = Chem.MolToInchiKey(canonical)[:14]
        normalized = Chem.MolToSmiles(canonical, canonical=True, isomericSmiles=True)
        mass = float(Descriptors.ExactMolWt(canonical))
        formula = rdMolDescriptors.CalcMolFormula(canonical)
        if not key or not normalized or not math.isfinite(mass) or not formula:
            return None
        return key, normalized, mass, formula
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class CatalogFieldMap:
    """Column mapping shared by Kaggle train and external structure tables."""

    smiles: str = "normalized_smiles"
    inchikey14: str = "inchikey14"
    formula: str = "molecular_formula"
    source: str = "ingest_lib"
    source_id: str = "molecule_id"


@dataclass(frozen=True, slots=True)
class StreamingCatalogReport:
    input_rows: int
    rows_with_smiles: int
    provisional_identity_count: int
    valid_structure_count_before_dedup: int
    unique_structure_count: int
    duplicate_structure_count: int
    missing_smiles_rows: int
    invalid_declared_identity_rows: int
    invalid_structure_count: int
    canonical_identity_mismatch_count: int
    excluded_holdout_count: int
    conflicting_smiles_identity_count: int
    conflicting_formula_identity_count: int
    provided_formula_mismatch_count: int
    source_row_counts: Mapping[str, int]
    source_unique_counts: Mapping[str, int]
    overlap_source_sets: Mapping[str, int]
    rdkit_version: str
    canonicalization_rule: str

    def to_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output["source_row_counts"] = dict(self.source_row_counts)
        output["source_unique_counts"] = dict(self.source_unique_counts)
        output["overlap_source_sets"] = dict(self.overlap_source_sets)
        return output


@dataclass(slots=True)
class _ProvisionalStructure:
    declared_identity: str | None
    smiles: str
    formula: str | None
    sources: set[str] = field(default_factory=set)
    source_ids: set[str] = field(default_factory=set)
    observed_smiles: set[str] = field(default_factory=set)
    observed_formulas: set[str] = field(default_factory=set)


def iter_parquet_structure_rows(
    path: str | Path,
    *,
    fields: CatalogFieldMap = CatalogFieldMap(),
    batch_size: int = 65_536,
) -> Iterator[Mapping[str, Any]]:
    """Yield only structure metadata from a Parquet file, one batch at a time.

    MS/MS peak arrays are intentionally not selected.  This makes C1 catalog
    extraction independent of the 2.5M-spectrum payload size.
    """

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(Path(path))
    available = set(parquet.schema_arrow.names)
    requested = (
        fields.smiles,
        fields.inchikey14,
        fields.formula,
        fields.source,
        fields.source_id,
    )
    required = (fields.smiles, fields.inchikey14)
    missing = [name for name in required if name not in available]
    if missing:
        raise ValueError(f"Parquet is missing required structure columns: {missing}")
    selected = list(dict.fromkeys(name for name in requested if name in available))
    for batch in parquet.iter_batches(batch_size=batch_size, columns=selected):
        for row in batch.to_pylist():
            yield row


def build_streaming_structure_catalog(
    rows: Iterable[Mapping[str, Any]],
    *,
    fields: CatalogFieldMap = CatalogFieldMap(),
    default_source: str = "train",
    excluded_inchikey14: Iterable[str] = (),
) -> tuple[tuple[CatalogRecord, ...], StreamingCatalogReport]:
    """Build a canonical unique catalog while consuming rows only once.

    Repeated spectra are collapsed by their declared InChIKey14 before RDKit
    canonicalization.  A malformed or mismatching declared identity is rejected
    rather than corrected from query/holdout information.  The excluded identity
    set is applied before records are emitted, supporting structure-absent
    validation without post-index filtering.
    """

    excluded = {
        key for value in excluded_inchikey14 if (key := _identity(value)) is not None
    }
    provisional: dict[str, _ProvisionalStructure] = {}
    input_rows = 0
    rows_with_smiles = 0
    missing_smiles_rows = 0
    invalid_declared_rows = 0
    source_rows: Counter[str] = Counter()

    for row in rows:
        input_rows += 1
        smiles = _text(row.get(fields.smiles))
        if smiles is None:
            missing_smiles_rows += 1
            continue
        rows_with_smiles += 1
        raw_declared = _text(row.get(fields.inchikey14))
        declared = _identity(raw_declared)
        if raw_declared is not None and declared is None:
            invalid_declared_rows += 1
        formula = _text(row.get(fields.formula))
        source = _text(row.get(fields.source)) or default_source
        source_id = _text(row.get(fields.source_id))
        source_rows[source] += 1

        # Train data has a declared identity.  External rows without one are
        # grouped by literal structure until canonical identity is available.
        group_key = declared if declared is not None else f"SMILES:{smiles}"
        item = provisional.get(group_key)
        if item is None:
            item = _ProvisionalStructure(declared, smiles, formula)
            provisional[group_key] = item
        elif (smiles, formula or "") < (item.smiles, item.formula or ""):
            item.smiles = smiles
            item.formula = formula
        item.sources.add(source)
        if source_id is not None:
            item.source_ids.add(source_id)
        item.observed_smiles.add(smiles)
        if formula is not None:
            item.observed_formulas.add(formula)

    records: list[CatalogRecord] = []
    invalid_structures = 0
    identity_mismatches = 0
    excluded_count = 0
    conflicting_smiles = 0
    conflicting_formulas = 0
    formula_mismatches = 0
    for group_key in sorted(provisional):
        item = provisional[group_key]
        if len(item.observed_smiles) > 1:
            conflicting_smiles += 1
        if len(item.observed_formulas) > 1:
            conflicting_formulas += 1
        canonical = _canonical_structure(item.smiles)
        if canonical is None:
            invalid_structures += 1
            continue
        key, normalized, mass, calculated_formula = canonical
        if item.declared_identity is not None and key != item.declared_identity:
            identity_mismatches += 1
            continue
        if key in excluded:
            excluded_count += 1
            continue
        if item.formula is not None and calculated_formula != item.formula:
            formula_mismatches += 1
        records.append(
            CatalogRecord(
                candidate_id=key,
                inchikey14=key,
                smiles=normalized,
                exact_mass=float(mass),
                formula=calculated_formula,
                sources=tuple(sorted(item.sources)),
                source_ids=tuple(sorted(item.source_ids)),
            )
        )

    merged, merge_report = deduplicate_catalog_records(records)
    report = StreamingCatalogReport(
        input_rows=input_rows,
        rows_with_smiles=rows_with_smiles,
        provisional_identity_count=len(provisional),
        valid_structure_count_before_dedup=len(records),
        unique_structure_count=len(merged),
        duplicate_structure_count=merge_report.duplicate_records,
        missing_smiles_rows=missing_smiles_rows,
        invalid_declared_identity_rows=invalid_declared_rows,
        invalid_structure_count=invalid_structures,
        canonical_identity_mismatch_count=identity_mismatches,
        excluded_holdout_count=excluded_count,
        conflicting_smiles_identity_count=conflicting_smiles,
        conflicting_formula_identity_count=conflicting_formulas,
        provided_formula_mismatch_count=formula_mismatches,
        source_row_counts=dict(sorted(source_rows.items())),
        source_unique_counts=dict(sorted(merge_report.source_counts_after.items())),
        overlap_source_sets=dict(sorted(merge_report.overlap_source_sets.items())),
        rdkit_version=rdkit_version(),
        canonicalization_rule="rdkit_tautomer_canonical_inchikey14",
    )
    return merged, report


def _pack_utf8(values: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    encoded = [value.encode("utf-8") for value in values]
    offsets = np.empty(len(encoded) + 1, dtype=np.int64)
    offsets[0] = 0
    if encoded:
        np.cumsum(np.asarray([len(value) for value in encoded], dtype=np.int64), out=offsets[1:])
        payload = np.frombuffer(b"".join(encoded), dtype=np.uint8).copy()
    else:
        offsets[1:] = 0
        payload = np.empty(0, dtype=np.uint8)
    return payload, offsets


def _unpack_utf8(payload: np.ndarray, offsets: np.ndarray, position: int) -> str:
    left = int(offsets[position])
    right = int(offsets[position + 1])
    return bytes(memoryview(payload)[left:right]).decode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class MassFormulaIndexManifest:
    schema_version: int
    tier_name: str
    structure_count: int
    sources: tuple[str, ...]
    backend: str
    rdkit_version: str
    files: Mapping[str, Mapping[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output["sources"] = list(self.sources)
        output["files"] = {key: dict(value) for key, value in self.files.items()}
        return output


class ScalableMassFormulaIndex:
    """Sorted exact-mass index with a secondary formula posting list."""

    _ARRAY_NAMES = (
        "masses",
        "candidate_ids",
        "formulas",
        "formula_names",
        "formula_offsets",
        "formula_positions",
        "smiles_payload",
        "smiles_offsets",
        "sources_payload",
        "sources_offsets",
        "source_ids_payload",
        "source_ids_offsets",
    )

    def __init__(
        self,
        *,
        masses: np.ndarray,
        candidate_ids: np.ndarray,
        formulas: np.ndarray,
        formula_names: np.ndarray,
        formula_offsets: np.ndarray,
        formula_positions: np.ndarray,
        smiles_payload: np.ndarray,
        smiles_offsets: np.ndarray,
        sources_payload: np.ndarray,
        sources_offsets: np.ndarray,
        source_ids_payload: np.ndarray,
        source_ids_offsets: np.ndarray,
        tier_name: str,
        sources: Sequence[str],
    ) -> None:
        self.masses = masses
        self.candidate_ids = candidate_ids
        self.formulas = formulas
        self.formula_names = formula_names
        self.formula_offsets = formula_offsets
        self.formula_positions = formula_positions
        self.smiles_payload = smiles_payload
        self.smiles_offsets = smiles_offsets
        self.sources_payload = sources_payload
        self.sources_offsets = sources_offsets
        self.source_ids_payload = source_ids_payload
        self.source_ids_offsets = source_ids_offsets
        self.tier_name = str(tier_name)
        self.sources = tuple(sorted(set(map(str, sources))))
        self._formula_lookup: dict[str, int] | None = None
        self._validate()

    def _validate(self) -> None:
        count = len(self.masses)
        if count == 0:
            raise ValueError("The index requires at least one structure")
        if len(self.candidate_ids) != count or len(self.formulas) != count:
            raise ValueError("Primary index arrays have inconsistent lengths")
        for name in ("smiles_offsets", "sources_offsets", "source_ids_offsets"):
            if len(getattr(self, name)) != count + 1:
                raise ValueError(f"{name} has an inconsistent length")
        if np.any(~np.isfinite(self.masses)) or np.any(self.masses <= 0):
            raise ValueError("Index masses must be finite and positive")
        if np.any(np.diff(self.masses) < 0):
            raise ValueError("Index masses must be sorted")
        if len(self.formula_offsets) != len(self.formula_names) + 1:
            raise ValueError("Formula offsets do not match formula names")
        if int(self.formula_offsets[-1]) != len(self.formula_positions):
            raise ValueError("Formula postings have an inconsistent terminal offset")
        if len(self.formula_positions) != count:
            raise ValueError("Every structure must occur in exactly one formula posting list")

    @classmethod
    def build(
        cls,
        records: Sequence[CatalogRecord],
        *,
        tier_name: str,
    ) -> "ScalableMassFormulaIndex":
        if not records:
            raise ValueError("records must not be empty")
        unique, _ = deduplicate_catalog_records(records)
        ordered = sorted(unique, key=lambda item: (item.exact_mass, item.inchikey14))
        masses = np.asarray([item.exact_mass for item in ordered], dtype=np.float64)
        max_id = max(14, max(len(item.inchikey14) for item in ordered))
        candidate_ids = np.asarray([item.inchikey14 for item in ordered], dtype=f"S{max_id}")
        formula_values = [item.formula or "" for item in ordered]
        max_formula = max(1, max(map(len, formula_values)))
        formulas = np.asarray(formula_values, dtype=f"S{max_formula}")

        grouped: dict[str, list[int]] = defaultdict(list)
        for position, formula in enumerate(formula_values):
            grouped[formula].append(position)
        names = sorted(grouped)
        max_name = max(1, max(map(len, names)))
        formula_names = np.asarray(names, dtype=f"S{max_name}")
        formula_offsets = np.zeros(len(names) + 1, dtype=np.int64)
        formula_positions_values: list[int] = []
        for index, formula in enumerate(names):
            formula_positions_values.extend(grouped[formula])
            formula_offsets[index + 1] = len(formula_positions_values)
        formula_positions = np.asarray(formula_positions_values, dtype=np.int64)

        smiles_payload, smiles_offsets = _pack_utf8([item.smiles for item in ordered])
        sources_payload, sources_offsets = _pack_utf8(
            ["\x1f".join(item.sources) for item in ordered]
        )
        source_ids_payload, source_ids_offsets = _pack_utf8(
            ["\x1f".join(item.source_ids) for item in ordered]
        )
        all_sources = sorted({source for item in ordered for source in item.sources})
        return cls(
            masses=masses,
            candidate_ids=candidate_ids,
            formulas=formulas,
            formula_names=formula_names,
            formula_offsets=formula_offsets,
            formula_positions=formula_positions,
            smiles_payload=smiles_payload,
            smiles_offsets=smiles_offsets,
            sources_payload=sources_payload,
            sources_offsets=sources_offsets,
            source_ids_payload=source_ids_payload,
            source_ids_offsets=source_ids_offsets,
            tier_name=tier_name,
            sources=all_sources,
        )

    def __len__(self) -> int:
        return len(self.masses)

    @staticmethod
    def _decode_scalar(value: np.bytes_ | bytes | str) -> str:
        return value.decode("utf-8") if isinstance(value, (np.bytes_, bytes)) else str(value)

    def candidate_id_at(self, position: int) -> str:
        return self._decode_scalar(self.candidate_ids[position])

    def formula_at(self, position: int) -> str:
        return self._decode_scalar(self.formulas[position])

    def smiles_at(self, position: int) -> str:
        return _unpack_utf8(self.smiles_payload, self.smiles_offsets, position)

    def sources_at(self, position: int) -> tuple[str, ...]:
        value = _unpack_utf8(self.sources_payload, self.sources_offsets, position)
        return tuple(part for part in value.split("\x1f") if part)

    def source_ids_at(self, position: int) -> tuple[str, ...]:
        value = _unpack_utf8(self.source_ids_payload, self.source_ids_offsets, position)
        return tuple(part for part in value.split("\x1f") if part)

    def to_catalog_records(self) -> tuple[CatalogRecord, ...]:
        """Materialize the verified index as catalog records without chemistry work."""

        return tuple(
            CatalogRecord(
                candidate_id=self.candidate_id_at(position),
                inchikey14=self.candidate_id_at(position),
                smiles=self.smiles_at(position),
                exact_mass=float(self.masses[position]),
                formula=self.formula_at(position) or None,
                sources=self.sources_at(position),
                source_ids=self.source_ids_at(position),
            )
            for position in range(len(self))
        )

    def _positions_for_formula(self, formula: str) -> np.ndarray:
        if self._formula_lookup is None:
            self._formula_lookup = {
                self._decode_scalar(value): index
                for index, value in enumerate(self.formula_names)
            }
        formula_index = self._formula_lookup.get(formula)
        if formula_index is None:
            return np.empty(0, dtype=np.int64)
        left = int(self.formula_offsets[formula_index])
        right = int(self.formula_offsets[formula_index + 1])
        return self.formula_positions[left:right]

    def _window_positions(
        self,
        neutral_mass: float,
        tolerance_ppm: float | None,
        formula: str | None,
    ) -> np.ndarray:
        if formula is None:
            universe: np.ndarray | None = None
            mass_values = self.masses
        else:
            universe = self._positions_for_formula(formula)
            mass_values = self.masses[universe]
        if tolerance_ppm is None:
            if universe is None:
                return np.arange(len(self), dtype=np.int64)
            return universe.copy()
        if not math.isfinite(tolerance_ppm) or tolerance_ppm <= 0:
            raise ValueError("tolerance_ppm must be finite and positive")
        delta = neutral_mass * tolerance_ppm * 1e-6
        left = int(np.searchsorted(mass_values, neutral_mass - delta, side="left"))
        right = int(np.searchsorted(mass_values, neutral_mass + delta, side="right"))
        if universe is None:
            return np.arange(left, right, dtype=np.int64)
        return universe[left:right]

    def retrieve(
        self,
        neutral_mass: float,
        *,
        top_k: int,
        tolerance_ppm: float | None = None,
        formula: str | None = None,
        channel: str = "mass",
    ) -> list[CandidateHit]:
        if not math.isfinite(neutral_mass) or neutral_mass <= 0:
            raise ValueError("neutral_mass must be finite and positive")
        if top_k <= 0:
            return []
        positions = self._window_positions(neutral_mass, tolerance_ppm, formula)
        if tolerance_ppm is None and len(positions) > top_k:
            # argpartition avoids sorting a million-entry catalog for fallback.
            errors_all = np.abs(self.masses[positions] - neutral_mass)
            boundary = float(np.partition(errors_all, top_k - 1)[top_k - 1])
            positions = positions[errors_all <= boundary]
        errors = np.abs(self.masses[positions] - neutral_mass) / neutral_mass * 1e6
        ids = self.candidate_ids[positions]
        order = np.lexsort((ids, errors))
        positions = positions[order][:top_k]
        errors = errors[order][:top_k]

        output: list[CandidateHit] = []
        for rank, (position_value, error_value) in enumerate(zip(positions, errors), start=1):
            position = int(position_value)
            error = float(error_value)
            sources = self.sources_at(position)
            source_ids = self.source_ids_at(position)
            features = {name: 0.0 for name in FEATURE_NAMES}
            features.update(
                {
                    "mass_error_ppm": error,
                    "abs_precursor_delta": abs(float(self.masses[position]) - neutral_mass),
                    "retrieval_score": 1.0 / (1.0 + error),
                }
            )
            output.append(
                CandidateHit(
                    candidate_id=self.candidate_id_at(position),
                    smiles=self.smiles_at(position),
                    source="+".join(sources),
                    source_rank=rank,
                    retrieval_score=features["retrieval_score"],
                    features=features,
                    metadata={
                        "inchikey14": self.candidate_id_at(position),
                        "formula": self.formula_at(position) or None,
                        "exact_mass": float(self.masses[position]),
                        "sources": list(sources),
                        "source_ids": list(source_ids),
                        "catalog_tier": self.tier_name,
                        "candidate_channel": channel,
                    },
                )
            )
        return output

    def save(self, directory: str | Path) -> MassFormulaIndexManifest:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        files: dict[str, dict[str, Any]] = {}
        for name in self._ARRAY_NAMES:
            path = target / f"{name}.npy"
            array = getattr(self, name)
            np.save(path, array, allow_pickle=False)
            files[name] = {
                "filename": path.name,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
                "dtype": str(array.dtype),
                "shape": list(array.shape),
            }
        manifest = MassFormulaIndexManifest(
            schema_version=INDEX_SCHEMA_VERSION,
            tier_name=self.tier_name,
            structure_count=len(self),
            sources=self.sources,
            backend=INDEX_BACKEND,
            rdkit_version=rdkit_version(),
            files=files,
        )
        (target / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    @classmethod
    def load(
        cls,
        directory: str | Path,
        *,
        mmap: bool = True,
        verify_hashes: bool = True,
    ) -> "ScalableMassFormulaIndex":
        target = Path(directory)
        payload = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if int(payload["schema_version"]) != INDEX_SCHEMA_VERSION:
            raise ValueError("Unsupported mass/formula index schema")
        if payload["backend"] != INDEX_BACKEND:
            raise ValueError("Unexpected retrieval backend")
        arrays: dict[str, np.ndarray] = {}
        for name in cls._ARRAY_NAMES:
            metadata = payload["files"][name]
            path = target / metadata["filename"]
            if verify_hashes and _sha256_file(path) != metadata["sha256"]:
                raise ValueError(f"Index checksum mismatch for {name}")
            arrays[name] = np.load(path, mmap_mode="r" if mmap else None, allow_pickle=False)
        index = cls(
            **arrays,
            tier_name=payload["tier_name"],
            sources=payload["sources"],
        )
        if len(index) != int(payload["structure_count"]):
            raise ValueError("Index structure count differs from manifest")
        return index


@dataclass(frozen=True, slots=True)
class DynamicPoolConfig:
    ppm_schedule: tuple[float, ...] = (5.0, 10.0, 20.0, 50.0)
    target_pool_size: int = 100
    maximum_pool_size: int = 1_000
    cheap_stage_size: int = 300
    expensive_stage_size: int = 100

    def __post_init__(self) -> None:
        if not self.ppm_schedule or any(
            not math.isfinite(value) or value <= 0 for value in self.ppm_schedule
        ):
            raise ValueError("ppm_schedule must contain finite positive values")
        if tuple(sorted(set(self.ppm_schedule))) != self.ppm_schedule:
            raise ValueError("ppm_schedule must be strictly increasing")
        if not 0 < self.target_pool_size <= self.maximum_pool_size:
            raise ValueError("target_pool_size must be within maximum_pool_size")
        if not 0 < self.expensive_stage_size <= self.cheap_stage_size:
            raise ValueError("stage sizes must be positive and ordered")
        if self.cheap_stage_size > self.maximum_pool_size:
            raise ValueError("cheap_stage_size cannot exceed maximum_pool_size")


@dataclass(frozen=True, slots=True)
class StagedCandidatePool:
    hits: tuple[CandidateHit, ...]
    mass_anchor_candidate_id: str
    selected_ppm: float
    candidate_counts_by_ppm: Mapping[str, int]
    used_nearest_mass_fallback: bool
    formula_hint: str | None
    formula_match_count: int
    cheap_stage_candidate_ids: tuple[str, ...]
    expensive_stage_candidate_ids: tuple[str, ...]


def _clone_hit(hit: CandidateHit) -> CandidateHit:
    return CandidateHit(
        candidate_id=hit.candidate_id,
        smiles=hit.smiles,
        source=hit.source,
        source_rank=hit.source_rank,
        retrieval_score=hit.retrieval_score,
        features=dict(hit.features),
        references_seen=hit.references_seen,
        metadata=copy.deepcopy(hit.metadata),
    )


def retrieve_dynamic_pool(
    index: ScalableMassFormulaIndex,
    neutral_mass: float,
    *,
    config: DynamicPoolConfig = DynamicPoolConfig(),
    formula_hint: str | None = None,
) -> StagedCandidatePool:
    """Choose the smallest measured ppm window that reaches the target size.

    If even the widest window is sparse, nearest-mass fallback fills the pool.
    A formula hint is annotated but never removes mass candidates.  This avoids
    turning an uncertain formula into a recall-destroying hard filter.
    """

    counts: dict[str, int] = {}
    selected_ppm = config.ppm_schedule[-1]
    selected: list[CandidateHit] = []
    for ppm in config.ppm_schedule:
        hits = index.retrieve(
            neutral_mass,
            top_k=config.maximum_pool_size,
            tolerance_ppm=ppm,
            channel="mass_window",
        )
        counts[f"{ppm:g}"] = len(hits)
        selected = hits
        selected_ppm = ppm
        if len(hits) >= config.target_pool_size:
            break

    used_fallback = len(selected) < config.target_pool_size
    if used_fallback:
        selected = index.retrieve(
            neutral_mass,
            top_k=config.target_pool_size,
            tolerance_ppm=None,
            channel="mass_fallback",
        )
    selected = selected[: config.maximum_pool_size]
    if not selected:
        raise RuntimeError("Mass retrieval unexpectedly returned an empty pool")
    for hit in selected:
        hit.metadata["formula_hint_match"] = bool(
            formula_hint is not None and hit.metadata.get("formula") == formula_hint
        )
    formula_match_count = sum(
        bool(hit.metadata["formula_hint_match"]) for hit in selected
    )
    identifiers = tuple(hit.candidate_id for hit in selected)
    return StagedCandidatePool(
        hits=tuple(selected),
        mass_anchor_candidate_id=identifiers[0],
        selected_ppm=selected_ppm,
        candidate_counts_by_ppm=counts,
        used_nearest_mass_fallback=used_fallback,
        formula_hint=formula_hint,
        formula_match_count=formula_match_count,
        cheap_stage_candidate_ids=identifiers[: config.cheap_stage_size],
        expensive_stage_candidate_ids=identifiers[: config.expensive_stage_size],
    )


@dataclass(frozen=True, slots=True)
class CandidateChannel:
    name: str
    hits: Sequence[CandidateHit]
    weight: float = 1.0


def union_candidate_channels(
    channels: Sequence[CandidateChannel],
    *,
    limit: int | None = None,
    rrf_constant: float = 60.0,
) -> list[CandidateHit]:
    """Union channels by canonical identity with deterministic weighted RRF."""

    if not channels:
        return []
    if not math.isfinite(rrf_constant) or rrf_constant <= 0:
        raise ValueError("rrf_constant must be finite and positive")
    if limit is not None and limit <= 0:
        return []
    merged: dict[str, CandidateHit] = {}
    fusion_score: Counter[str] = Counter()
    channel_ranks: dict[str, dict[str, int]] = defaultdict(dict)
    lower_is_better = {"mass_error_ppm", "abs_precursor_delta"}
    for channel in channels:
        if not channel.name or not math.isfinite(channel.weight) or channel.weight < 0:
            raise ValueError("Channel names are required and weights must be non-negative")
        seen_in_channel: set[str] = set()
        for position, hit in enumerate(channel.hits, start=1):
            key = _identity(hit.metadata.get("inchikey14")) or hit.candidate_id
            if key in seen_in_channel:
                continue
            seen_in_channel.add(key)
            fusion_score[key] += channel.weight / (rrf_constant + position)
            channel_ranks[key][channel.name] = position
            current = merged.get(key)
            if current is None:
                current = _clone_hit(hit)
                current.candidate_id = key
                current.metadata["inchikey14"] = key
                merged[key] = current
                continue
            current.retrieval_score = max(current.retrieval_score, hit.retrieval_score)
            current.references_seen += hit.references_seen
            for name, value in hit.features.items():
                previous = current.features.get(name)
                if previous is None:
                    current.features[name] = value
                elif name in lower_is_better:
                    current.features[name] = min(previous, value)
                else:
                    current.features[name] = max(previous, value)
            previous_sources = set(current.metadata.get("sources", []))
            previous_sources.update(hit.metadata.get("sources", []))
            if hit.source:
                previous_sources.update(part for part in hit.source.split("+") if part)
            current.metadata["sources"] = sorted(previous_sources)

    ordered_keys = sorted(
        merged,
        key=lambda key: (
            -fusion_score[key],
            min(channel_ranks[key].values()),
            key,
        ),
    )
    if limit is not None:
        ordered_keys = ordered_keys[:limit]
    output: list[CandidateHit] = []
    for rank, key in enumerate(ordered_keys, start=1):
        hit = merged[key]
        hit.source_rank = rank
        hit.metadata["candidate_channels"] = sorted(channel_ranks[key])
        hit.metadata["channel_ranks"] = dict(sorted(channel_ranks[key].items()))
        hit.metadata["fusion_score"] = float(fusion_score[key])
        hit.source = "+".join(hit.metadata.get("sources", [])) or hit.source
        output.append(hit)
    return output


class RetrievalCache:
    """Small in-process LRU cache; returned objects are defensive copies."""

    def __init__(self, max_entries: int = 4_096) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._values: OrderedDict[tuple[Any, ...], StagedCandidatePool] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(
        neutral_mass: float,
        formula_hint: str | None,
        config: DynamicPoolConfig,
        tier_name: str,
    ) -> tuple[Any, ...]:
        return (float(neutral_mass).hex(), formula_hint, config, tier_name)

    @staticmethod
    def _clone(pool: StagedCandidatePool) -> StagedCandidatePool:
        return StagedCandidatePool(
            hits=tuple(_clone_hit(hit) for hit in pool.hits),
            mass_anchor_candidate_id=pool.mass_anchor_candidate_id,
            selected_ppm=pool.selected_ppm,
            candidate_counts_by_ppm=dict(pool.candidate_counts_by_ppm),
            used_nearest_mass_fallback=pool.used_nearest_mass_fallback,
            formula_hint=pool.formula_hint,
            formula_match_count=pool.formula_match_count,
            cheap_stage_candidate_ids=pool.cheap_stage_candidate_ids,
            expensive_stage_candidate_ids=pool.expensive_stage_candidate_ids,
        )

    def get(self, key: tuple[Any, ...]) -> StagedCandidatePool | None:
        value = self._values.get(key)
        if value is None:
            self.misses += 1
            return None
        self.hits += 1
        self._values.move_to_end(key)
        return self._clone(value)

    def put(self, key: tuple[Any, ...], value: StagedCandidatePool) -> None:
        self._values[key] = self._clone(value)
        self._values.move_to_end(key)
        while len(self._values) > self.max_entries:
            self._values.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._values)


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    query_id: str
    neutral_mass: float
    formula_hint: str | None = None


@dataclass(frozen=True, slots=True)
class BatchRetrievalReport:
    query_count: int
    total_candidate_count: int
    mean_candidate_count: float
    maximum_candidate_count: int
    fallback_query_count: int
    elapsed_seconds: float
    queries_per_second: float
    rss_before_bytes: int | None
    rss_after_bytes: int | None
    peak_rss_bytes: int | None
    cache_hits_delta: int
    cache_misses_delta: int
    index_structure_count: int
    index_array_bytes: int
    backend: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rss_snapshot() -> tuple[int | None, int | None]:
    rss: int | None = None
    peak: int | None = None
    try:
        import psutil

        rss = int(psutil.Process(os.getpid()).memory_info().rss)
    except ImportError:
        pass
    try:
        import resource

        raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        peak = raw * 1024 if raw < 10**10 else raw
    except ImportError:
        pass
    return rss, peak


def _index_array_bytes(index: ScalableMassFormulaIndex) -> int:
    return int(sum(getattr(index, name).nbytes for name in index._ARRAY_NAMES))


def batch_retrieve_dynamic_pools(
    index: ScalableMassFormulaIndex,
    requests: Sequence[RetrievalRequest],
    *,
    config: DynamicPoolConfig = DynamicPoolConfig(),
    cache: RetrievalCache | None = None,
) -> tuple[dict[str, StagedCandidatePool], BatchRetrievalReport]:
    """Retrieve a deterministic batch and return measured CPU/RAM accounting."""

    if len({request.query_id for request in requests}) != len(requests):
        raise ValueError("query_id values must be unique within a batch")
    rss_before, peak_before = _rss_snapshot()
    hits_before = cache.hits if cache is not None else 0
    misses_before = cache.misses if cache is not None else 0
    started = time.perf_counter()
    pools: dict[str, StagedCandidatePool] = {}
    for request in requests:
        key = RetrievalCache.key(
            request.neutral_mass, request.formula_hint, config, index.tier_name
        )
        pool = cache.get(key) if cache is not None else None
        if pool is None:
            pool = retrieve_dynamic_pool(
                index,
                request.neutral_mass,
                config=config,
                formula_hint=request.formula_hint,
            )
            if cache is not None:
                cache.put(key, pool)
        pools[request.query_id] = pool
    elapsed = time.perf_counter() - started
    rss_after, peak_after = _rss_snapshot()
    counts = [len(pool.hits) for pool in pools.values()]
    report = BatchRetrievalReport(
        query_count=len(requests),
        total_candidate_count=sum(counts),
        mean_candidate_count=float(np.mean(counts)) if counts else 0.0,
        maximum_candidate_count=max(counts, default=0),
        fallback_query_count=sum(pool.used_nearest_mass_fallback for pool in pools.values()),
        elapsed_seconds=elapsed,
        queries_per_second=len(requests) / elapsed if elapsed > 0 else math.inf,
        rss_before_bytes=rss_before,
        rss_after_bytes=rss_after,
        peak_rss_bytes=max(
            (value for value in (peak_before, peak_after) if value is not None),
            default=None,
        ),
        cache_hits_delta=(cache.hits - hits_before) if cache is not None else 0,
        cache_misses_delta=(cache.misses - misses_before) if cache is not None else 0,
        index_structure_count=len(index),
        index_array_bytes=_index_array_bytes(index),
        backend=INDEX_BACKEND,
    )
    return pools, report


@dataclass(frozen=True, slots=True)
class StagedRankingResult:
    ranking: tuple[str, ...]
    cheap_scored_count: int
    expensive_scored_count: int
    mass_anchor_candidate_id: str


def apply_staged_reranking(
    pool: StagedCandidatePool,
    *,
    cheap_score: Callable[[CandidateHit], float],
    expensive_score: Callable[[CandidateHit], float],
    cheap_stage_size: int | None = None,
    expensive_stage_size: int | None = None,
) -> StagedRankingResult:
    """Apply an economical scorer before a bounded expensive scorer.

    Candidates not reaching a stage are retained after scored candidates, so
    evaluation can distinguish ranking loss from retrieval loss.
    """

    cheap_count = min(cheap_stage_size or len(pool.cheap_stage_candidate_ids), len(pool.hits))
    expensive_count = min(
        expensive_stage_size or len(pool.expensive_stage_candidate_ids), cheap_count
    )
    if cheap_count <= 0 or expensive_count <= 0:
        raise ValueError("stage sizes must be positive")
    original_order = {hit.candidate_id: rank for rank, hit in enumerate(pool.hits)}
    cheap_subset = list(pool.hits[:cheap_count])
    cheap_ranked = sorted(
        cheap_subset,
        key=lambda hit: (-float(cheap_score(hit)), original_order[hit.candidate_id], hit.candidate_id),
    )
    expensive_subset = cheap_ranked[:expensive_count]
    cheap_order = {hit.candidate_id: rank for rank, hit in enumerate(cheap_ranked)}
    expensive_ranked = sorted(
        expensive_subset,
        key=lambda hit: (
            -float(expensive_score(hit)),
            cheap_order[hit.candidate_id],
            hit.candidate_id,
        ),
    )
    expensive_ids = {hit.candidate_id for hit in expensive_ranked}
    cheap_tail = [hit for hit in cheap_ranked if hit.candidate_id not in expensive_ids]
    cheap_ids = {hit.candidate_id for hit in cheap_ranked}
    untouched = [hit for hit in pool.hits if hit.candidate_id not in cheap_ids]
    ranking = tuple(
        hit.candidate_id for hit in (*expensive_ranked, *cheap_tail, *untouched)
    )
    return StagedRankingResult(
        ranking=ranking,
        cheap_scored_count=cheap_count,
        expensive_scored_count=expensive_count,
        mass_anchor_candidate_id=pool.mass_anchor_candidate_id,
    )
