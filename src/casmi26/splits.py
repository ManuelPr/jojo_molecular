from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from .chemistry import canonical_inchikey14
from .schemas import ProcessedSpectrum
from .validation_contracts import SplitManifest, ValidationProtocol


DEFAULT_SPLIT_SEED = 2026


def _identity_key(spectrum: ProcessedSpectrum) -> str:
    provided = None if spectrum.inchikey14 is None else str(spectrum.inchikey14).strip().upper()
    computed = (
        canonical_inchikey14(spectrum.normalized_smiles)
        if spectrum.normalized_smiles is not None
        else None
    )
    if provided and computed and provided != computed:
        raise ValueError(
            f"Spectrum {spectrum.spectrum_id!r} has inconsistent provided/canonical InChIKey14"
        )
    key = computed or provided
    if key is None or not str(key).strip():
        raise ValueError(
            f"Spectrum {spectrum.spectrum_id!r} has no normalized chemical identity"
        )
    normalized = str(key).strip().upper()
    if len(normalized) != 14 or not normalized.isalpha():
        raise ValueError(
            f"Spectrum {spectrum.spectrum_id!r} has invalid InChIKey14 {normalized!r}"
        )
    return normalized


def _canonical_float_array(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype="<f8").reshape(-1).copy()
    # Canonicalize representations whose IEEE payload may otherwise differ.
    array[array == 0.0] = 0.0
    array[np.isnan(array)] = np.nan
    return array


def _float_token(value: float | None) -> str | None:
    if value is None:
        return None
    number = float(value)
    if math.isnan(number):
        return "nan"
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    if number == 0.0:
        number = 0.0
    return number.hex()


def spectrum_fingerprint(spectrum: ProcessedSpectrum) -> str:
    """Hash acquisition content without using IDs or target identity.

    The precursor/adduct/acquisition context is included alongside peak arrays.
    Consequently, replicated acquisitions with a renamed ``spectrum_id`` have
    the same fingerprint, while genuinely different collision-energy spectra do
    not get collapsed merely because their peak arrays happen to match.
    """

    mz = _canonical_float_array(spectrum.mz)
    intensity = _canonical_float_array(spectrum.intensity)
    if mz.size != intensity.size:
        raise ValueError(f"Misaligned peak arrays for spectrum {spectrum.spectrum_id!r}")

    header = {
        "adduct": spectrum.adduct,
        "collision_energy_ev": [_float_token(value) for value in spectrum.collision_energy_ev],
        "ion_mode": spectrum.ion_mode,
        "neutral_mass": _float_token(spectrum.neutral_mass),
        "precursor_mz": _float_token(spectrum.precursor_mz),
    }
    digest = hashlib.sha256(
        json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest.update(mz.size.to_bytes(8, byteorder="little", signed=False))
    digest.update(mz.tobytes(order="C"))
    digest.update(intensity.tobytes(order="C"))
    return digest.hexdigest()


def dataset_fingerprint(spectra: Iterable[ProcessedSpectrum]) -> str:
    """Return an order-independent fingerprint of split-relevant dataset state."""

    ordered = _validated_spectra(spectra)
    return _dataset_fingerprint_from_validated(ordered)


def _dataset_fingerprint_from_validated(
    ordered: Sequence[ProcessedSpectrum],
) -> str:
    digest = hashlib.sha256()
    for spectrum in ordered:
        metadata = {
            "formula": spectrum.molecular_formula,
            "identity": _identity_key(spectrum),
            "ingest_lib": spectrum.ingest_lib,
            "instrument": spectrum.instrument,
            "molecule_id": spectrum.molecule_id,
            "normalized_smiles": spectrum.normalized_smiles,
            "quality": {
                str(key): _float_token(value)
                for key, value in sorted(spectrum.quality.items())
            },
            "spectrum_fingerprint": spectrum_fingerprint(spectrum),
            "spectrum_id": spectrum.spectrum_id,
        }
        payload = json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(len(payload).to_bytes(8, byteorder="little", signed=False))
        digest.update(payload)
    return digest.hexdigest()


def spectrum_identity_mapping(
    spectra: Iterable[ProcessedSpectrum],
) -> dict[str, str]:
    """Materialize the identity evidence required by leakage audits."""

    return {
        spectrum.spectrum_id: _identity_key(spectrum)
        for spectrum in _validated_spectra(spectra)
    }


def spectrum_hash_mapping(
    spectra: Iterable[ProcessedSpectrum],
) -> dict[str, str]:
    """Materialize acquisition hashes without inflating every saved manifest."""

    return {
        spectrum.spectrum_id: spectrum_fingerprint(spectrum)
        for spectrum in _validated_spectra(spectra)
    }


def _validated_spectra(spectra: Iterable[ProcessedSpectrum]) -> list[ProcessedSpectrum]:
    records = sorted(list(spectra), key=lambda item: item.spectrum_id)
    if not records:
        raise ValueError("Cannot generate a split from an empty spectrum collection")
    ids = [item.spectrum_id for item in records]
    duplicate_ids = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        raise ValueError(f"Duplicate spectrum_id values: {duplicate_ids[:5]}")
    for spectrum in records:
        _identity_key(spectrum)
        if len(spectrum.mz) != len(spectrum.intensity):
            raise ValueError(f"Misaligned peak arrays for spectrum {spectrum.spectrum_id!r}")
    return records


def _deduplicate_spectra(
    records: Sequence[ProcessedSpectrum],
) -> tuple[list[ProcessedSpectrum], tuple[str, ...]]:
    retained: list[ProcessedSpectrum] = []
    excluded: list[str] = []
    seen: set[str] = set()
    for spectrum in records:
        fingerprint = spectrum_fingerprint(spectrum)
        if fingerprint in seen:
            excluded.append(spectrum.spectrum_id)
            continue
        seen.add(fingerprint)
        retained.append(spectrum)
    return retained, tuple(sorted(excluded))


def _validate_fraction(validation_fraction: float) -> float:
    fraction = float(validation_fraction)
    if not math.isfinite(fraction) or not 0.0 < fraction < 1.0:
        raise ValueError("validation_fraction must be finite and strictly between 0 and 1")
    return fraction


def _validation_count(item_count: int, fraction: float, *, minimum: int = 1) -> int:
    if item_count < 2:
        raise ValueError("At least two independent groups are required for a holdout")
    return min(item_count - 1, max(minimum, math.floor(item_count * fraction)))


def _seeded_order(values: Iterable[str], *, seed: int, namespace: str) -> list[str]:
    def key(value: str) -> tuple[bytes, str]:
        payload = f"{namespace}\0{seed}\0{value}".encode("utf-8")
        return hashlib.sha256(payload).digest(), value

    return sorted(set(values), key=key)


def _candidate_keys(
    dataset_keys: set[str], external_keys: Iterable[str] | None
) -> set[str]:
    result = set(dataset_keys)
    if external_keys is not None:
        result.update(
            str(key).strip().upper()
            for key in external_keys
            if key is not None and str(key).strip()
        )
    return result


def _numeric_summary(values: Iterable[float | int | None]) -> dict[str, float | int | None]:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": len(finite),
        "min": min(finite),
        "max": max(finite),
        "mean": math.fsum(finite) / len(finite),
    }


def _category_counts(values: Iterable[str | None]) -> dict[str, int]:
    counts = Counter(value if value else "<missing>" for value in values)
    return dict(sorted(counts.items()))


def _domain_summary(records: Sequence[ProcessedSpectrum]) -> dict[str, Any]:
    identities = {_identity_key(record) for record in records}
    return {
        "spectrum_count": len(records),
        "identity_count": len(identities),
        "source_counts": _category_counts(record.ingest_lib for record in records),
        "instrument_counts": _category_counts(record.instrument for record in records),
        "adduct_counts": _category_counts(record.adduct for record in records),
        "neutral_mass": _numeric_summary(record.neutral_mass for record in records),
        "peak_count": _numeric_summary(len(record.mz) for record in records),
    }


def _records_for_ids(
    records: Sequence[ProcessedSpectrum], spectrum_ids: Iterable[str]
) -> list[ProcessedSpectrum]:
    selected = set(spectrum_ids)
    return [record for record in records if record.spectrum_id in selected]


def _metadata(
    *,
    records: Sequence[ProcessedSpectrum],
    train_ids: tuple[str, ...],
    reference_ids: tuple[str, ...],
    validation_ids: tuple[str, ...],
    excluded_duplicate_ids: tuple[str, ...],
    validation_fraction: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "split_parameters": {"validation_fraction": validation_fraction},
        "input_spectrum_count": len(records) + len(excluded_duplicate_ids),
        "retained_spectrum_count": len(records),
        "deduplication": {
            "strategy": "sha256_acquisition_content_keep_lexicographically_first_id",
            "excluded_count": len(excluded_duplicate_ids),
            "excluded_spectrum_ids": list(excluded_duplicate_ids),
        },
        "domain_summary": {
            "train": _domain_summary(_records_for_ids(records, train_ids)),
            "reference": _domain_summary(_records_for_ids(records, reference_ids)),
            "validation": _domain_summary(_records_for_ids(records, validation_ids)),
        },
        "audit_evidence": {
            "identity_mapping_factory": "casmi26.splits.spectrum_identity_mapping",
            "spectrum_hash_mapping_factory": "casmi26.splits.spectrum_hash_mapping",
        },
    }
    if extra:
        metadata.update(extra)
    return metadata


def _base_records(
    spectra: Iterable[ProcessedSpectrum],
) -> tuple[list[ProcessedSpectrum], list[ProcessedSpectrum], tuple[str, ...], str]:
    original = _validated_spectra(spectra)
    fingerprint = _dataset_fingerprint_from_validated(original)
    retained, excluded = _deduplicate_spectra(original)
    return original, retained, excluded, fingerprint


def _validation_stage_partition(
    validation_keys: Iterable[str], *, seed: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split validation identities into disjoint model-selection/final stages."""

    ordered = _seeded_order(
        validation_keys, seed=seed, namespace="validation_stage_partition"
    )
    cut = len(ordered) // 2
    if len(ordered) > 1:
        cut = max(1, cut)
    return tuple(sorted(ordered[:cut])), tuple(sorted(ordered[cut:]))


def make_library_holdout(
    spectra: Iterable[ProcessedSpectrum],
    *,
    validation_fraction: float = 0.2,
    seed: int = DEFAULT_SPLIT_SEED,
    candidate_identity_keys: Iterable[str] | None = None,
) -> SplitManifest:
    """Split distinct acquisitions of eligible identities into reference/query.

    Exact replicated acquisitions are removed before splitting. Identities with
    fewer than two distinct acquisitions remain reference-only because a valid
    library holdout cannot be formed for them.
    """

    fraction = _validate_fraction(validation_fraction)
    original, retained, excluded, fingerprint = _base_records(spectra)
    grouped: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    for spectrum in retained:
        grouped[_identity_key(spectrum)].append(spectrum)

    eligible_keys = sorted(key for key, values in grouped.items() if len(values) >= 2)
    if not eligible_keys:
        raise ValueError("Library holdout requires an identity with two distinct acquisitions")

    validation_ids: set[str] = set()
    reference_ids: set[str] = set()
    for identity, values in sorted(grouped.items()):
        ids = [value.spectrum_id for value in values]
        if len(ids) < 2:
            reference_ids.update(ids)
            continue
        ordered = _seeded_order(ids, seed=seed, namespace=f"library:{identity}")
        count = _validation_count(len(ordered), fraction)
        validation_ids.update(ordered[:count])
        reference_ids.update(ordered[count:])

    validation_keys = {_identity_key(item) for item in retained if item.spectrum_id in validation_ids}
    reference_keys = {_identity_key(item) for item in retained if item.spectrum_id in reference_ids}
    if not validation_keys <= reference_keys:
        raise AssertionError("Each library query identity must retain a reference acquisition")

    # A reference acquisition must not also be used as a ranker-training
    # query. The library holdout remains usable even for two-acquisition
    # identities: those contribute reference + validation, but no ranker row.
    train_ids: set[str] = set()
    distinct_reference_ids: set[str] = set()
    for identity, values in sorted(grouped.items()):
        available_ids = sorted(
            value.spectrum_id
            for value in values
            if value.spectrum_id in reference_ids
        )
        if not available_ids:
            continue
        ordered = _seeded_order(
            available_ids, seed=seed, namespace=f"library-reference:{identity}"
        )
        distinct_reference_ids.add(ordered[0])
        train_ids.update(ordered[1:])

    train_tuple = tuple(sorted(train_ids))
    reference_tuple = tuple(sorted(distinct_reference_ids))
    validation_tuple = tuple(sorted(validation_ids))
    all_keys = {_identity_key(item) for item in original}
    candidates = _candidate_keys(all_keys, candidate_identity_keys)
    ranker_train_keys = {
        _identity_key(item) for item in retained if item.spectrum_id in train_ids
    }
    model_selection_keys, final_evaluation_keys = _validation_stage_partition(
        validation_keys, seed=seed
    )
    metadata = _metadata(
        records=retained,
        train_ids=train_tuple,
        reference_ids=reference_tuple,
        validation_ids=validation_tuple,
        excluded_duplicate_ids=excluded,
        validation_fraction=fraction,
        extra={
            "protocol_semantics": "same_identity_distinct_acquisition",
            "eligible_validation_identity_count": len(eligible_keys),
            "model_selection_identity_keys": list(model_selection_keys),
            "final_evaluation_identity_keys": list(final_evaluation_keys),
        },
    )
    metadata["input_spectrum_count"] = len(original)
    return SplitManifest(
        protocol="library_holdout",
        seed=int(seed),
        dataset_fingerprint=fingerprint,
        train_spectrum_ids=train_tuple,
        reference_spectrum_ids=reference_tuple,
        validation_spectrum_ids=validation_tuple,
        ranker_train_identity_keys=tuple(sorted(ranker_train_keys)),
        validation_identity_keys=tuple(sorted(validation_keys)),
        candidate_identity_keys=tuple(sorted(candidates)),
        metadata=metadata,
    )


def _make_identity_holdout(
    spectra: Iterable[ProcessedSpectrum],
    *,
    protocol: ValidationProtocol,
    validation_fraction: float,
    seed: int,
    candidate_identity_keys: Iterable[str] | None,
) -> SplitManifest:
    fraction = _validate_fraction(validation_fraction)
    original, retained, excluded, fingerprint = _base_records(spectra)
    grouped: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    for spectrum in retained:
        grouped[_identity_key(spectrum)].append(spectrum)
    identities = set(grouped)
    dataset_identities = {_identity_key(item) for item in original}
    # Reserve both model-selection and final-evaluation identities whenever the
    # collection is large enough, while always retaining a training identity.
    minimum_validation_identities = 2 if len(identities) >= 3 else 1
    validation_count = _validation_count(
        len(identities), fraction, minimum=minimum_validation_identities
    )
    # Molecule-disjoint and novelty protocols intentionally share membership;
    # the paired comparison differs only in candidate availability.
    ordered_keys = _seeded_order(identities, seed=seed, namespace="identity_holdout")
    validation_keys = set(ordered_keys[:validation_count])
    train_keys = identities - validation_keys

    validation_ids = tuple(
        sorted(
            spectrum.spectrum_id
            for key in validation_keys
            for spectrum in grouped[key]
        )
    )
    train_query_ids: set[str] = set()
    reference_ids: set[str] = set()
    ranker_train_keys: set[str] = set()
    for identity in sorted(train_keys):
        ordered_ids = _seeded_order(
            (spectrum.spectrum_id for spectrum in grouped[identity]),
            seed=seed,
            namespace=f"identity-reference:{identity}",
        )
        reference_ids.add(ordered_ids[0])
        if len(ordered_ids) > 1:
            train_query_ids.update(ordered_ids[1:])
            ranker_train_keys.add(identity)
    train_ids = tuple(sorted(train_query_ids))
    reference_tuple = tuple(sorted(reference_ids))
    candidates = _candidate_keys(dataset_identities, candidate_identity_keys)
    if protocol == "novelty_holdout":
        candidates.difference_update(validation_keys)
        semantics = "validation_identity_absent_from_labels_spectra_and_candidates"
    else:
        candidates.update(validation_keys)
        semantics = "validation_identity_absent_from_labels_and_spectra_but_candidate_available"

    model_selection_keys, final_evaluation_keys = _validation_stage_partition(
        validation_keys, seed=seed
    )
    metadata = _metadata(
        records=retained,
        train_ids=train_ids,
        reference_ids=reference_tuple,
        validation_ids=validation_ids,
        excluded_duplicate_ids=excluded,
        validation_fraction=fraction,
        extra={
            "protocol_semantics": semantics,
            "model_selection_identity_keys": list(model_selection_keys),
            "final_evaluation_identity_keys": list(final_evaluation_keys),
        },
    )
    metadata["input_spectrum_count"] = len(original)
    return SplitManifest(
        protocol=protocol,
        seed=int(seed),
        dataset_fingerprint=fingerprint,
        train_spectrum_ids=train_ids,
        reference_spectrum_ids=reference_tuple,
        validation_spectrum_ids=validation_ids,
        ranker_train_identity_keys=tuple(sorted(ranker_train_keys)),
        validation_identity_keys=tuple(sorted(validation_keys)),
        candidate_identity_keys=tuple(sorted(candidates)),
        metadata=metadata,
    )


def make_molecule_disjoint_split(
    spectra: Iterable[ProcessedSpectrum],
    *,
    validation_fraction: float = 0.2,
    seed: int = DEFAULT_SPLIT_SEED,
    candidate_identity_keys: Iterable[str] | None = None,
) -> SplitManifest:
    """Hold out normalized identities while retaining them as known candidates."""

    return _make_identity_holdout(
        spectra,
        protocol="molecule_disjoint",
        validation_fraction=validation_fraction,
        seed=seed,
        candidate_identity_keys=candidate_identity_keys,
    )


def make_novelty_holdout_split(
    spectra: Iterable[ProcessedSpectrum],
    *,
    validation_fraction: float = 0.2,
    seed: int = DEFAULT_SPLIT_SEED,
    candidate_identity_keys: Iterable[str] | None = None,
) -> SplitManifest:
    """Hold out normalized identities from labels, spectra, and candidates."""

    return _make_identity_holdout(
        spectra,
        protocol="novelty_holdout",
        validation_fraction=validation_fraction,
        seed=seed,
        candidate_identity_keys=candidate_identity_keys,
    )


def generate_split(
    protocol: ValidationProtocol,
    spectra: Iterable[ProcessedSpectrum],
    *,
    validation_fraction: float = 0.2,
    seed: int = DEFAULT_SPLIT_SEED,
    candidate_identity_keys: Iterable[str] | None = None,
) -> SplitManifest:
    """Dispatch to a validation protocol using one stable integration API."""

    functions = {
        "library_holdout": make_library_holdout,
        "molecule_disjoint": make_molecule_disjoint_split,
        "novelty_holdout": make_novelty_holdout_split,
    }
    try:
        function = functions[protocol]
    except KeyError as error:
        raise ValueError(f"Unsupported validation protocol: {protocol!r}") from error
    return function(
        spectra,
        validation_fraction=validation_fraction,
        seed=seed,
        candidate_identity_keys=candidate_identity_keys,
    )


def save_split_manifest(manifest: SplitManifest, path: str | Path) -> None:
    """Named persistence adapter for callers that should not depend on internals."""

    manifest.save(path)


def load_split_manifest(path: str | Path) -> SplitManifest:
    return SplitManifest.load(path)
