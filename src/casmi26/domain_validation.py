"""Leakage-safe domain validation for the three CASMI visibility regimes.

The module deliberately keeps domain membership, spectral visibility and
structural visibility as separate contracts.  A model-selection run may use
only the ``development`` stage.  Access to the newly sealed stage is explicit
and is intended for a single, pre-registered evaluation after all choices are
frozen.

No function in this module consults ranks, labels beyond normalized chemical
identity, or test targets.  Query selection depends only on provenance,
instrument and a deterministic hash order.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable, Literal, Mapping, Sequence

import numpy as np

from .analog_propagation import spectrum_content_hash
from .chemistry import canonical_inchikey14
from .schemas import ProcessedSpectrum
from .splits import dataset_fingerprint, spectrum_fingerprint


DomainCondition = Literal[
    "A_library_visible",
    "B_structure_known_spectra_hidden",
    "C_structure_absent",
]
DomainStage = Literal["development", "sealed"]

CONDITIONS: tuple[DomainCondition, ...] = (
    "A_library_visible",
    "B_structure_known_spectra_hidden",
    "C_structure_absent",
)
STAGES: tuple[DomainStage, ...] = ("development", "sealed")

_INCHIKEY14_RE = re.compile(r"^[A-Z]{14}$")


class DomainValidationError(ValueError):
    """Raised when a domain-validation contract cannot be made truthful."""


class SealedHoldoutAccessError(RuntimeError):
    """Raised when a caller tries to inspect the sealed stage implicitly."""


@dataclass(frozen=True, slots=True)
class DomainConditionManifest:
    """One visibility condition over one fixed query stage."""

    condition: DomainCondition
    stage: DomainStage
    query_spectrum_ids: tuple[str, ...]
    reference_spectrum_ids: tuple[str, ...]
    validation_identity_keys: tuple[str, ...]
    candidate_identity_keys: tuple[str, ...]
    structure_visible: bool
    same_identity_reference_allowed: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for name in (
            "query_spectrum_ids",
            "reference_spectrum_ids",
            "validation_identity_keys",
            "candidate_identity_keys",
        ):
            payload[name] = list(payload[name])
        return payload


@dataclass(frozen=True, slots=True)
class DomainValidationPlan:
    """Versioned plan containing paired development and sealed conditions.

    The sealed membership is stored for reproducibility, but ``manifest``
    refuses to return it unless ``allow_sealed=True``.  This is an operational
    guard, not cryptographic access control; experiment orchestration must also
    keep the sealed metrics out of tuning logs.
    """

    seed: int
    dataset_fingerprint: str
    query_source: str
    required_instrument: str | None
    development_identity_keys: tuple[str, ...]
    sealed_identity_keys: tuple[str, ...]
    prior_final_identity_keys: tuple[str, ...]
    manifests: tuple[DomainConditionManifest, ...]
    excluded_query_identity_keys: tuple[str, ...]
    excluded_duplicate_reference_ids: tuple[str, ...]
    metadata: Mapping[str, Any]
    schema_version: int = 1

    def manifest(
        self,
        condition: DomainCondition,
        *,
        stage: DomainStage = "development",
        allow_sealed: bool = False,
    ) -> DomainConditionManifest:
        if stage == "sealed" and not allow_sealed:
            raise SealedHoldoutAccessError(
                "The sealed domain holdout requires allow_sealed=True after model choices are frozen"
            )
        for manifest in self.manifests:
            if manifest.condition == condition and manifest.stage == stage:
                return manifest
        raise KeyError(f"Unknown domain manifest: stage={stage!r}, condition={condition!r}")

    @property
    def sealed_holdout_commitment(self) -> str:
        payload = "\n".join(self.sealed_identity_keys).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self, *, include_sealed_membership: bool = False) -> dict[str, Any]:
        manifests = []
        for manifest in self.manifests:
            item = manifest.to_dict()
            if manifest.stage == "sealed" and not include_sealed_membership:
                item["query_spectrum_ids"] = []
                item["validation_identity_keys"] = []
                item["reference_spectrum_ids"] = []
                item["candidate_identity_keys"] = []
                item["sealed_membership_redacted"] = True
            manifests.append(item)
        return {
            "schema_version": self.schema_version,
            "seed": self.seed,
            "dataset_fingerprint": self.dataset_fingerprint,
            "query_source": self.query_source,
            "required_instrument": self.required_instrument,
            "development_identity_keys": list(self.development_identity_keys),
            "sealed_identity_keys": (
                list(self.sealed_identity_keys) if include_sealed_membership else []
            ),
            "sealed_holdout_commitment": self.sealed_holdout_commitment,
            "prior_final_identity_keys": list(self.prior_final_identity_keys),
            "manifests": manifests,
            "excluded_query_identity_keys": list(self.excluded_query_identity_keys),
            "excluded_duplicate_reference_ids": list(
                self.excluded_duplicate_reference_ids
            ),
            "metadata": dict(self.metadata),
        }

    def canonical_json(self, *, include_sealed_membership: bool = True) -> str:
        return json.dumps(
            self.to_dict(include_sealed_membership=include_sealed_membership),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def manifest_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DomainAuditIssue:
    code: str
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DomainAuditReport:
    passed: bool
    issues: tuple[DomainAuditIssue, ...]
    checks: Mapping[str, int | bool | str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [asdict(issue) for issue in self.issues],
            "checks": dict(self.checks),
        }


def make_domain_validation_plan(
    spectra: Iterable[ProcessedSpectrum],
    *,
    candidate_identity_keys: Iterable[str],
    prior_final_identity_keys: Iterable[str],
    query_source: str = "enveda-np-examples",
    required_instrument: str | None = "timsTOF",
    sealed_fraction: float = 0.2,
    seed: int = 2027,
) -> DomainValidationPlan:
    """Build paired A/B/C manifests over a newly sealed domain cohort.

    Query spectra come from ``query_source`` and, when supplied,
    ``required_instrument``.  A same-identity reference with different spectral
    content is required for every eligible identity.  Conditions B and C
    remove *all* spectra of the query identities from the reference library;
    condition C additionally removes their canonical identities from the
    structural catalog.

    ``prior_final_identity_keys`` is mandatory and those identities are removed
    from both the new query cohort and every reference library.  This prevents
    the already-consulted Goal 4 final holdout from becoming development data.
    """

    records = _validated_records(spectra, require_identity=True)
    fraction = float(sealed_fraction)
    if not math.isfinite(fraction) or not 0.0 < fraction < 1.0:
        raise DomainValidationError("sealed_fraction must be finite and between 0 and 1")
    if not str(query_source).strip():
        raise DomainValidationError("query_source must be non-empty")

    prior_final = _normalized_identity_set(
        prior_final_identity_keys, name="prior_final_identity_keys"
    )
    if not prior_final:
        raise DomainValidationError(
            "prior_final_identity_keys must be supplied to prove holdout independence"
        )
    candidates = _normalized_identity_set(
        candidate_identity_keys, name="candidate_identity_keys"
    )
    if not candidates:
        raise DomainValidationError("candidate_identity_keys must be non-empty")

    identities = {record.spectrum_id: _identity_key(record) for record in records}
    content_hashes = {
        record.spectrum_id: spectrum_content_hash(record) for record in records
    }
    by_identity: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    by_id = {record.spectrum_id: record for record in records}
    for record in records:
        by_identity[identities[record.spectrum_id]].append(record)

    expected_source = _normalized_label(query_source)
    expected_instrument = (
        None if required_instrument is None else _normalized_label(required_instrument)
    )
    domain_by_identity: dict[str, list[ProcessedSpectrum]] = defaultdict(list)
    for record in records:
        if _normalized_label(record.ingest_lib) != expected_source:
            continue
        if (
            expected_instrument is not None
            and _normalized_label(record.instrument) != expected_instrument
        ):
            continue
        domain_by_identity[identities[record.spectrum_id]].append(record)

    eligible: dict[str, dict[str, tuple[str, ...] | str]] = {}
    excluded: set[str] = set()
    excluded_duplicate_references: set[str] = set()
    for identity, domain_records in sorted(domain_by_identity.items()):
        if identity in prior_final or identity not in candidates:
            excluded.add(identity)
            continue

        query_records = _deduplicate_by_content(domain_records, content_hashes)
        query_ids = tuple(sorted(record.spectrum_id for record in query_records))
        query_hash_set = {content_hashes[spectrum_id] for spectrum_id in query_ids}

        external_references = [
            record
            for record in by_identity[identity]
            if record.spectrum_id not in query_ids
            and content_hashes[record.spectrum_id] not in query_hash_set
        ]
        duplicate_external = [
            record.spectrum_id
            for record in by_identity[identity]
            if record.spectrum_id not in query_ids
            and content_hashes[record.spectrum_id] in query_hash_set
        ]
        excluded_duplicate_references.update(duplicate_external)

        # A source with a single acquisition may still contribute if another
        # source supplies an independent same-identity reference.  If it does
        # not, reserve one domain acquisition and retain the others as queries.
        if not external_references and len(query_records) >= 2:
            ordered = _seeded_order(
                (record.spectrum_id for record in query_records),
                seed=seed,
                namespace=f"domain-reference:{identity}",
            )
            reserved_id = ordered[0]
            query_ids = tuple(sorted(value for value in query_ids if value != reserved_id))
            external_references = [by_id[reserved_id]]

        if not query_ids or not external_references:
            excluded.add(identity)
            continue

        reference_id = _seeded_order(
            (record.spectrum_id for record in external_references),
            seed=seed,
            namespace=f"library-visible-reference:{identity}",
        )[0]
        eligible[identity] = {
            "query_ids": query_ids,
            "library_reference_id": reference_id,
        }

    if len(eligible) < 2:
        raise DomainValidationError(
            "At least two eligible domain identities with independent references are required"
        )

    ordered_identities = _seeded_order(
        eligible, seed=seed, namespace="goal5-domain-sealed-holdout"
    )
    sealed_count = min(
        len(ordered_identities) - 1,
        max(1, math.floor(len(ordered_identities) * fraction)),
    )
    sealed_keys = tuple(sorted(ordered_identities[:sealed_count]))
    development_keys = tuple(sorted(ordered_identities[sealed_count:]))

    all_query_ids = {
        spectrum_id
        for values in eligible.values()
        for spectrum_id in values["query_ids"]
    }
    all_query_hashes = {content_hashes[spectrum_id] for spectrum_id in all_query_ids}
    reusable_references: list[str] = []
    for record in records:
        identity = identities[record.spectrum_id]
        if record.spectrum_id in all_query_ids or identity in prior_final:
            continue
        if content_hashes[record.spectrum_id] in all_query_hashes:
            excluded_duplicate_references.add(record.spectrum_id)
            continue
        reusable_references.append(record.spectrum_id)

    manifests: list[DomainConditionManifest] = []
    for stage, stage_keys in (
        ("development", development_keys),
        ("sealed", sealed_keys),
    ):
        stage_key_set = set(stage_keys)
        query_ids = tuple(
            sorted(
                spectrum_id
                for identity in stage_keys
                for spectrum_id in eligible[identity]["query_ids"]
            )
        )

        # Sealed identities cannot enter development spectra at all.  At the
        # sealed evaluation, development identities may legitimately be part
        # of the already-frozen training/reference universe.
        reference_base = [
            spectrum_id
            for spectrum_id in reusable_references
            if not (
                stage == "development"
                and identities[spectrum_id] in set(sealed_keys)
            )
        ]
        visible_refs = tuple(sorted(reference_base))
        hidden_refs = tuple(
            sorted(
                spectrum_id
                for spectrum_id in reference_base
                if identities[spectrum_id] not in stage_key_set
            )
        )

        manifests.extend(
            (
                DomainConditionManifest(
                    condition="A_library_visible",
                    stage=stage,  # type: ignore[arg-type]
                    query_spectrum_ids=query_ids,
                    reference_spectrum_ids=visible_refs,
                    validation_identity_keys=stage_keys,
                    candidate_identity_keys=tuple(sorted(candidates)),
                    structure_visible=True,
                    same_identity_reference_allowed=True,
                    description=(
                        "Independent same-identity reference spectra and the structure "
                        "are available; query content is never a reference."
                    ),
                ),
                DomainConditionManifest(
                    condition="B_structure_known_spectra_hidden",
                    stage=stage,  # type: ignore[arg-type]
                    query_spectrum_ids=query_ids,
                    reference_spectrum_ids=hidden_refs,
                    validation_identity_keys=stage_keys,
                    candidate_identity_keys=tuple(sorted(candidates)),
                    structure_visible=True,
                    same_identity_reference_allowed=False,
                    description=(
                        "All spectra of validation identities are hidden while the "
                        "canonical structure remains in the candidate database."
                    ),
                ),
                DomainConditionManifest(
                    condition="C_structure_absent",
                    stage=stage,  # type: ignore[arg-type]
                    query_spectrum_ids=query_ids,
                    reference_spectrum_ids=hidden_refs,
                    validation_identity_keys=stage_keys,
                    candidate_identity_keys=tuple(
                        sorted(candidates - stage_key_set)
                    ),
                    structure_visible=False,
                    same_identity_reference_allowed=False,
                    description=(
                        "Validation spectra and canonical structures are absent; this "
                        "measures retrieval impossibility and novelty-channel need."
                    ),
                ),
            )
        )

    metadata: dict[str, Any] = {
        "selection_rule": (
            "source+instrument, canonical identity, independent same-identity reference, "
            "sha256 seed order"
        ),
        "sealed_fraction": fraction,
        "domain_identity_count_before_exclusions": len(domain_by_identity),
        "eligible_identity_count": len(eligible),
        "development_identity_count": len(development_keys),
        "sealed_identity_count": len(sealed_keys),
        "domain_query_spectrum_count": len(all_query_ids),
        "reference_spectrum_count_before_condition_masks": len(reusable_references),
        "query_source_counts": _category_counts(
            by_id[spectrum_id].ingest_lib for spectrum_id in all_query_ids
        ),
        "query_instrument_counts": _category_counts(
            by_id[spectrum_id].instrument for spectrum_id in all_query_ids
        ),
        "content_hash": "casmi26.analog_propagation.spectrum_content_hash:v1",
        "acquisition_hash": "casmi26.splits.spectrum_fingerprint:v1",
        "identity_rule": "canonical InChIKey14",
        "sealed_policy": (
            "Do not call manifest(..., stage='sealed', allow_sealed=True) until "
            "features, hyperparameters and candidate tiers are frozen."
        ),
    }

    plan = DomainValidationPlan(
        seed=int(seed),
        dataset_fingerprint=dataset_fingerprint(records),
        query_source=str(query_source),
        required_instrument=required_instrument,
        development_identity_keys=development_keys,
        sealed_identity_keys=sealed_keys,
        prior_final_identity_keys=tuple(sorted(prior_final)),
        manifests=tuple(manifests),
        excluded_query_identity_keys=tuple(sorted(excluded)),
        excluded_duplicate_reference_ids=tuple(
            sorted(excluded_duplicate_references)
        ),
        metadata=metadata,
    )
    audit_domain_validation_plan(plan, records, raise_on_error=True)
    return plan


def audit_domain_validation_plan(
    plan: DomainValidationPlan,
    spectra: Iterable[ProcessedSpectrum],
    *,
    raise_on_error: bool = False,
) -> DomainAuditReport:
    """Fail-closed audit of identity, content, provenance and visibility."""

    records = _validated_records(spectra, require_identity=True)
    by_id = {record.spectrum_id: record for record in records}
    identity = {record.spectrum_id: _identity_key(record) for record in records}
    content = {record.spectrum_id: spectrum_content_hash(record) for record in records}
    acquisition = {record.spectrum_id: spectrum_fingerprint(record) for record in records}
    issues: list[DomainAuditIssue] = []
    checks: dict[str, int | bool | str] = {
        "manifest_count": len(plan.manifests),
        "sealed_holdout_commitment": plan.sealed_holdout_commitment,
    }

    observed_fingerprint = dataset_fingerprint(records)
    checks["dataset_fingerprint_match"] = observed_fingerprint == plan.dataset_fingerprint
    if observed_fingerprint != plan.dataset_fingerprint:
        issues.append(
            DomainAuditIssue(
                "dataset_fingerprint_mismatch",
                "The audited spectra differ from the dataset used to build the plan.",
                (f"expected:{plan.dataset_fingerprint}", f"observed:{observed_fingerprint}"),
            )
        )

    development = set(plan.development_identity_keys)
    sealed = set(plan.sealed_identity_keys)
    prior = set(plan.prior_final_identity_keys)
    overlap = (development & sealed) | (development & prior) | (sealed & prior)
    checks["stage_identity_overlap_count"] = len(overlap)
    checks["holdout_independence"] = not overlap
    if overlap:
        issues.append(
            DomainAuditIssue(
                "holdout_identity_overlap",
                "Development, sealed and prior-final identities must be disjoint.",
                _evidence(overlap),
            )
        )

    expected_pairs = {(stage, condition) for stage in STAGES for condition in CONDITIONS}
    observed_pairs = {(item.stage, item.condition) for item in plan.manifests}
    checks["condition_matrix_complete"] = observed_pairs == expected_pairs
    if observed_pairs != expected_pairs:
        missing = sorted(expected_pairs - observed_pairs)
        extra = sorted(observed_pairs - expected_pairs)
        issues.append(
            DomainAuditIssue(
                "condition_matrix_incomplete",
                "Exactly one A/B/C manifest is required for development and sealed stages.",
                _evidence([f"missing:{x}" for x in missing] + [f"extra:{x}" for x in extra]),
            )
        )

    duplicate_manifest_pairs = len(plan.manifests) - len(observed_pairs)
    checks["duplicate_condition_manifest_count"] = duplicate_manifest_pairs
    if duplicate_manifest_pairs:
        issues.append(
            DomainAuditIssue(
                "duplicate_condition_manifest",
                "A stage/condition pair occurs more than once.",
            )
        )

    total_content_collisions = 0
    total_acquisition_collisions = 0
    visibility_failures = 0
    provenance_failures = 0
    missing_provenance_ids: set[str] = set()
    unknown_ids: set[str] = set()
    sealed_in_development_references: set[str] = set()
    prior_in_spectra: set[str] = set()

    for manifest in plan.manifests:
        query_ids = set(manifest.query_spectrum_ids)
        reference_ids = set(manifest.reference_spectrum_ids)
        unknown_ids.update((query_ids | reference_ids) - set(by_id))
        if unknown_ids:
            continue
        if len(query_ids) != len(manifest.query_spectrum_ids):
            issues.append(
                DomainAuditIssue(
                    "duplicate_query_id",
                    f"Duplicate query IDs in {manifest.stage}/{manifest.condition}.",
                )
            )
        if len(reference_ids) != len(manifest.reference_spectrum_ids):
            issues.append(
                DomainAuditIssue(
                    "duplicate_reference_id",
                    f"Duplicate reference IDs in {manifest.stage}/{manifest.condition}.",
                )
            )
        direct_overlap = query_ids & reference_ids
        if direct_overlap:
            issues.append(
                DomainAuditIssue(
                    "query_reference_membership_overlap",
                    f"A query row is also a reference in {manifest.stage}/{manifest.condition}.",
                    _evidence(direct_overlap),
                )
            )

        query_content = _ids_by_value(query_ids, content)
        reference_content = _ids_by_value(reference_ids, content)
        content_collisions = set(query_content) & set(reference_content)
        total_content_collisions += len(content_collisions)
        if content_collisions:
            issues.append(
                DomainAuditIssue(
                    "query_reference_content_overlap",
                    f"Copied spectral content crosses query/reference in {manifest.stage}/{manifest.condition}.",
                    _evidence(content_collisions),
                )
            )

        query_acquisition = _ids_by_value(query_ids, acquisition)
        reference_acquisition = _ids_by_value(reference_ids, acquisition)
        acquisition_collisions = set(query_acquisition) & set(reference_acquisition)
        total_acquisition_collisions += len(acquisition_collisions)

        query_keys = {identity[spectrum_id] for spectrum_id in query_ids}
        reference_keys = {identity[spectrum_id] for spectrum_id in reference_ids}
        declared_keys = set(manifest.validation_identity_keys)
        candidates = set(manifest.candidate_identity_keys)
        if query_keys != declared_keys:
            visibility_failures += 1
            issues.append(
                DomainAuditIssue(
                    "query_identity_mismatch",
                    f"Declared validation identities disagree with query rows in {manifest.stage}/{manifest.condition}.",
                    _evidence(query_keys ^ declared_keys),
                )
            )

        if manifest.condition == "A_library_visible":
            if not query_keys <= reference_keys:
                visibility_failures += 1
                issues.append(
                    DomainAuditIssue(
                        "library_visible_reference_missing",
                        "Condition A requires an independent reference for every query identity.",
                        _evidence(query_keys - reference_keys),
                    )
                )
            if not query_keys <= candidates:
                visibility_failures += 1
                issues.append(
                    DomainAuditIssue(
                        "library_visible_candidate_missing",
                        "Condition A requires every target structure in the candidate database.",
                        _evidence(query_keys - candidates),
                    )
                )
        elif manifest.condition == "B_structure_known_spectra_hidden":
            leaked = query_keys & reference_keys
            missing = query_keys - candidates
            if leaked or missing:
                visibility_failures += 1
                issues.append(
                    DomainAuditIssue(
                        "structure_known_visibility_violation",
                        "Condition B hides target spectra but retains target structures.",
                        _evidence(
                            [f"reference:{key}" for key in leaked]
                            + [f"candidate_missing:{key}" for key in missing]
                        ),
                    )
                )
        elif manifest.condition == "C_structure_absent":
            leaked_refs = query_keys & reference_keys
            leaked_candidates = query_keys & candidates
            if leaked_refs or leaked_candidates:
                visibility_failures += 1
                issues.append(
                    DomainAuditIssue(
                        "structure_absent_visibility_violation",
                        "Condition C removes target spectra and canonical structures.",
                        _evidence(
                            [f"reference:{key}" for key in leaked_refs]
                            + [f"candidate:{key}" for key in leaked_candidates]
                        ),
                    )
                )

        for spectrum_id in query_ids:
            record = by_id[spectrum_id]
            if not _display_label(record.ingest_lib) or _display_label(record.ingest_lib) == "<missing>":
                missing_provenance_ids.add(spectrum_id)
            if _normalized_label(record.ingest_lib) != _normalized_label(plan.query_source):
                provenance_failures += 1
            if (
                plan.required_instrument is not None
                and _normalized_label(record.instrument)
                != _normalized_label(plan.required_instrument)
            ):
                provenance_failures += 1

        missing_provenance_ids.update(
            spectrum_id
            for spectrum_id in reference_ids
            if _display_label(by_id[spectrum_id].ingest_lib) == "<missing>"
        )

        if manifest.stage == "development":
            sealed_in_development_references.update(reference_keys & sealed)
        prior_in_spectra.update((query_keys | reference_keys) & prior)

    checks["query_reference_content_collision_count"] = total_content_collisions
    checks["query_reference_acquisition_collision_count"] = total_acquisition_collisions
    checks["visibility_failure_count"] = visibility_failures
    checks["query_provenance_failure_count"] = provenance_failures
    checks["missing_spectral_provenance_count"] = len(missing_provenance_ids)
    checks["sealed_identity_in_development_reference_count"] = len(
        sealed_in_development_references
    )
    checks["prior_final_identity_in_query_or_reference_count"] = len(prior_in_spectra)
    checks["unknown_spectrum_id_count"] = len(unknown_ids)

    if unknown_ids:
        issues.append(
            DomainAuditIssue(
                "unknown_spectrum_id",
                "A manifest references spectra absent from the audited dataset.",
                _evidence(unknown_ids),
            )
        )
    if provenance_failures:
        issues.append(
            DomainAuditIssue(
                "query_provenance_mismatch",
                "Query rows do not match the declared source/instrument domain.",
            )
        )
    if missing_provenance_ids:
        issues.append(
            DomainAuditIssue(
                "missing_spectral_provenance",
                "Every query/reference spectrum must retain its source provenance.",
                _evidence(missing_provenance_ids),
            )
        )
    if sealed_in_development_references:
        issues.append(
            DomainAuditIssue(
                "sealed_identity_used_in_development",
                "Sealed identities occur in development reference spectra.",
                _evidence(sealed_in_development_references),
            )
        )
    if prior_in_spectra:
        issues.append(
            DomainAuditIssue(
                "prior_final_reused",
                "Previously consulted final identities occur in the new query/reference spectra.",
                _evidence(prior_in_spectra),
            )
        )

    report = DomainAuditReport(passed=not issues, issues=tuple(issues), checks=checks)
    if raise_on_error and not report.passed:
        codes = ", ".join(issue.code for issue in report.issues)
        raise DomainValidationError(f"Domain validation leakage audit failed: {codes}")
    return report


def summarize_domain(
    spectra: Iterable[ProcessedSpectrum],
) -> dict[str, Any]:
    """Describe acquisition domain and instrument-specific fragmentation.

    Noise-floor values are explicitly proxies derived from normalized relative
    intensities; they are not estimates of detector electronic noise.
    """

    records = _validated_records(spectra, require_identity=False)
    rows = [_spectrum_diagnostics(record) for record in records]
    known_identities = [
        _identity_key(record)
        for record in records
        if record.inchikey14 is not None or record.normalized_smiles is not None
    ]
    group_keys = [_diagnostic_group_key(record) for record in records]
    spectra_per_group = Counter(group_keys)
    instruments = _category_counts(record.instrument for record in records)
    sources = _category_counts(record.ingest_lib for record in records)
    adducts = _category_counts(record.adduct for record in records)
    ion_modes = _category_counts(record.ion_mode for record in records)

    numeric_names = (
        "precursor_mz",
        "neutral_mass",
        "peak_count",
        "collision_energy_mean_ev",
        "collision_energy_span_ev",
        "low_intensity_fraction_le_0_1pct",
        "low_intensity_fraction_le_1pct",
        "nonpositive_intensity_fraction",
        "relative_intensity_p10",
        "median_mz_spacing",
        "base_peak_intensity_log10",
    )
    numeric = {
        name: _numeric_distribution(row[name] for row in rows) for name in numeric_names
    }

    by_instrument: dict[str, Any] = {}
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        grouped[_display_label(record.instrument)].append(index)
    for instrument, indices in sorted(grouped.items()):
        subset_records = [records[index] for index in indices]
        subset_rows = [rows[index] for index in indices]
        by_instrument[instrument] = {
            "spectrum_count": len(indices),
            "molecule_group_count": len(
                {_diagnostic_group_key(record) for record in subset_records}
            ),
            "labeled_identity_count": len(
                {
                    _identity_key(record)
                    for record in subset_records
                    if record.inchikey14 is not None
                    or record.normalized_smiles is not None
                }
            ),
            "adduct_counts": _category_counts(record.adduct for record in subset_records),
            "peak_count": _numeric_distribution(
                row["peak_count"] for row in subset_rows
            ),
            "collision_energy_mean_ev": _numeric_distribution(
                row["collision_energy_mean_ev"] for row in subset_rows
            ),
            "precursor_mz": _numeric_distribution(
                row["precursor_mz"] for row in subset_rows
            ),
            "low_intensity_fraction_le_1pct": _numeric_distribution(
                row["low_intensity_fraction_le_1pct"] for row in subset_rows
            ),
        }

    return {
        "spectrum_count": len(records),
        "identity_count": (
            len(set(known_identities))
            if len(known_identities) == len(records)
            else None
        ),
        "labeled_identity_count": len(set(known_identities)),
        "molecule_group_count": len(set(group_keys)),
        "grouping_basis": (
            "canonical_inchikey14"
            if len(known_identities) == len(records)
            else "molecule_id_fallback_for_unlabeled_rows"
        ),
        "source_counts": sources,
        "instrument_counts": instruments,
        "adduct_counts": adducts,
        "ion_mode_counts": ion_modes,
        "spectra_per_identity": _numeric_distribution(spectra_per_group.values()),
        "spectra_per_molecule_group": _numeric_distribution(
            spectra_per_group.values()
        ),
        "numeric": numeric,
        "by_instrument": by_instrument,
        "noise_floor_proxy_definition": {
            "low_intensity_fraction_le_0_1pct": (
                "fraction of positive peaks at or below 0.001 of the spectrum maximum"
            ),
            "low_intensity_fraction_le_1pct": (
                "fraction of positive peaks at or below 0.01 of the spectrum maximum"
            ),
            "relative_intensity_p10": "10th percentile of positive intensity / spectrum maximum",
        },
    }


def compare_domain_diagnostics(
    *,
    train: Iterable[ProcessedSpectrum],
    test: Iterable[ProcessedSpectrum],
    domain: Iterable[ProcessedSpectrum],
) -> dict[str, Any]:
    """Compare train, test and proposed domain-validation distributions."""

    collections = {
        "train": _validated_records(train, require_identity=False),
        "test": _validated_records(test, require_identity=False),
        "domain": _validated_records(domain, require_identity=False),
    }
    summaries = {name: summarize_domain(values) for name, values in collections.items()}
    rows = {
        name: [_spectrum_diagnostics(record) for record in values]
        for name, values in collections.items()
    }
    numeric_names = tuple(next(iter(summaries.values()))["numeric"])
    pairs: dict[str, Any] = {}
    for left_name, right_name in (
        ("train", "test"),
        ("domain", "test"),
        ("train", "domain"),
    ):
        numeric_shift = {}
        for feature in numeric_names:
            left = _finite_array(row[feature] for row in rows[left_name])
            right = _finite_array(row[feature] for row in rows[right_name])
            numeric_shift[feature] = _numeric_shift(left, right)
        categorical_shift = {}
        for feature, accessor in (
            ("instrument", lambda record: record.instrument),
            ("adduct", lambda record: record.adduct),
            ("ion_mode", lambda record: record.ion_mode),
            ("source", lambda record: record.ingest_lib),
        ):
            categorical_shift[feature] = _categorical_shift(
                (accessor(record) for record in collections[left_name]),
                target_values=(
                    accessor(record) for record in collections[right_name]
                ),
            )
        pairs[f"{left_name}_to_{right_name}"] = {
            "numeric": numeric_shift,
            "categorical": categorical_shift,
        }

    return {
        "summaries": summaries,
        "pairwise_shift": pairs,
        "interpretation_guard": (
            "Distributional proximity is descriptive only; it does not prove that a "
            "validation score predicts hidden-test MRR. The public test parquet may be a placeholder."
        ),
    }


def _validated_records(
    spectra: Iterable[ProcessedSpectrum], *, require_identity: bool
) -> list[ProcessedSpectrum]:
    records = sorted(list(spectra), key=lambda item: item.spectrum_id)
    if not records:
        raise DomainValidationError("A non-empty spectrum collection is required")
    ids = [record.spectrum_id for record in records]
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise DomainValidationError(f"Duplicate spectrum IDs: {duplicates[:5]}")
    for record in records:
        if require_identity:
            _identity_key(record)
        elif record.inchikey14 is not None or record.normalized_smiles is not None:
            _identity_key(record)
        mz = np.asarray(record.mz)
        intensity = np.asarray(record.intensity)
        if mz.ndim != 1 or intensity.ndim != 1 or mz.shape != intensity.shape:
            raise DomainValidationError(
                f"Spectrum {record.spectrum_id!r} has invalid peak arrays"
            )
        if not np.isfinite(mz).all() or not np.isfinite(intensity).all():
            raise DomainValidationError(
                f"Spectrum {record.spectrum_id!r} contains non-finite peaks"
            )
    return records


def _diagnostic_group_key(record: ProcessedSpectrum) -> str:
    if record.inchikey14 is not None or record.normalized_smiles is not None:
        return _identity_key(record)
    molecule_id = str(record.molecule_id).strip()
    if molecule_id:
        return f"molecule:{molecule_id}"
    return f"spectrum:{record.spectrum_id}"


def _identity_key(record: ProcessedSpectrum) -> str:
    provided = "" if record.inchikey14 is None else str(record.inchikey14).strip().upper()
    computed = (
        None
        if record.normalized_smiles is None
        else canonical_inchikey14(record.normalized_smiles)
    )
    if provided and computed and provided != computed:
        raise DomainValidationError(
            f"Spectrum {record.spectrum_id!r} has inconsistent canonical identity"
        )
    key = computed or provided
    if not key or _INCHIKEY14_RE.fullmatch(key) is None:
        raise DomainValidationError(
            f"Spectrum {record.spectrum_id!r} has invalid InChIKey14 {key!r}"
        )
    return key


def _normalized_identity_set(values: Iterable[str], *, name: str) -> set[str]:
    result: set[str] = set()
    for value in values:
        key = str(value).strip().upper()
        if _INCHIKEY14_RE.fullmatch(key) is None:
            raise DomainValidationError(f"{name} contains invalid InChIKey14 {value!r}")
        result.add(key)
    return result


def _normalized_label(value: object) -> str:
    return "" if value is None else str(value).strip().casefold()


def _display_label(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return text or "<missing>"


def _seeded_order(values: Iterable[str], *, seed: int, namespace: str) -> list[str]:
    def order_key(value: str) -> tuple[bytes, str]:
        payload = f"{namespace}\0{seed}\0{value}".encode("utf-8")
        return hashlib.sha256(payload).digest(), value

    return sorted(set(values), key=order_key)


def _deduplicate_by_content(
    records: Sequence[ProcessedSpectrum], hashes: Mapping[str, str]
) -> list[ProcessedSpectrum]:
    retained: list[ProcessedSpectrum] = []
    seen: set[str] = set()
    for record in sorted(records, key=lambda item: item.spectrum_id):
        digest = hashes[record.spectrum_id]
        if digest in seen:
            continue
        seen.add(digest)
        retained.append(record)
    return retained


def _category_counts(values: Iterable[object]) -> dict[str, int]:
    return dict(sorted(Counter(_display_label(value) for value in values).items()))


def _ids_by_value(
    spectrum_ids: Iterable[str], values: Mapping[str, str]
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for spectrum_id in spectrum_ids:
        result[values[spectrum_id]].append(spectrum_id)
    return dict(result)


def _evidence(values: Iterable[object], limit: int = 25) -> tuple[str, ...]:
    ordered = sorted(str(value) for value in values)
    if len(ordered) <= limit:
        return tuple(ordered)
    return tuple(ordered[:limit] + [f"... and {len(ordered) - limit} more"])


def _spectrum_diagnostics(record: ProcessedSpectrum) -> dict[str, float | None]:
    intensity = np.asarray(record.intensity, dtype=np.float64)
    mz = np.asarray(record.mz, dtype=np.float64)
    positive = intensity[intensity > 0.0]
    if positive.size:
        relative = positive / float(np.max(positive))
        low_01 = float(np.mean(relative <= 0.001))
        low_1 = float(np.mean(relative <= 0.01))
        p10 = float(np.quantile(relative, 0.10))
    else:
        low_01 = None
        low_1 = None
        p10 = None
    if mz.size >= 2:
        median_spacing = float(np.median(np.diff(np.sort(mz))))
    else:
        median_spacing = None
    energies = np.asarray(record.collision_energy_ev, dtype=np.float64)
    energies = energies[np.isfinite(energies)]
    base_peak = record.quality.get("base_peak_intensity", record.quality.get("base_peak"))
    if base_peak is None:
        base_peak = getattr(record, "base_peak_intensity", None)
    base_peak_log = (
        math.log10(float(base_peak))
        if base_peak is not None and math.isfinite(float(base_peak)) and float(base_peak) > 0.0
        else None
    )
    return {
        "precursor_mz": _finite_or_none(record.precursor_mz),
        "neutral_mass": _finite_or_none(record.neutral_mass),
        "peak_count": float(mz.size),
        "collision_energy_mean_ev": (
            float(np.mean(energies)) if energies.size else None
        ),
        "collision_energy_span_ev": (
            float(np.max(energies) - np.min(energies)) if energies.size else None
        ),
        "low_intensity_fraction_le_0_1pct": low_01,
        "low_intensity_fraction_le_1pct": low_1,
        "nonpositive_intensity_fraction": (
            float(np.mean(intensity <= 0.0)) if intensity.size else None
        ),
        "relative_intensity_p10": p10,
        "median_mz_spacing": median_spacing,
        "base_peak_intensity_log10": base_peak_log,
    }


def _finite_or_none(value: object) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _finite_array(values: Iterable[object]) -> np.ndarray:
    finite: list[float] = []
    for value in values:
        if value is None:
            continue
        number = float(value)
        if math.isfinite(number):
            finite.append(number)
    return np.asarray(finite, dtype=np.float64)


def _numeric_distribution(values: Iterable[object]) -> dict[str, float | int | None]:
    materialized = list(values)
    finite = _finite_array(materialized)
    missing = len(materialized) - int(finite.size)
    if not finite.size:
        return {
            "count": 0,
            "missing": missing,
            "min": None,
            "p05": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p95": None,
            "max": None,
            "mean": None,
            "std": None,
        }
    quantiles = np.quantile(finite, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "count": int(finite.size),
        "missing": missing,
        "min": float(np.min(finite)),
        "p05": float(quantiles[0]),
        "p25": float(quantiles[1]),
        "median": float(quantiles[2]),
        "p75": float(quantiles[3]),
        "p95": float(quantiles[4]),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
    }


def _numeric_shift(left: np.ndarray, right: np.ndarray) -> dict[str, float | int | None]:
    if not left.size or not right.size:
        return {
            "left_count": int(left.size),
            "right_count": int(right.size),
            "ks_distance": None,
            "standardized_mean_difference": None,
            "median_delta_right_minus_left": None,
        }
    pooled_variance = (float(np.var(left)) + float(np.var(right))) / 2.0
    smd = (
        (float(np.mean(right)) - float(np.mean(left))) / math.sqrt(pooled_variance)
        if pooled_variance > 0.0
        else (0.0 if float(np.mean(left)) == float(np.mean(right)) else None)
    )
    return {
        "left_count": int(left.size),
        "right_count": int(right.size),
        "ks_distance": _ks_distance(left, right),
        "standardized_mean_difference": smd,
        "median_delta_right_minus_left": float(np.median(right) - np.median(left)),
    }


def _ks_distance(left: np.ndarray, right: np.ndarray) -> float:
    values = np.sort(np.concatenate([left, right]))
    left_sorted = np.sort(left)
    right_sorted = np.sort(right)
    left_cdf = np.searchsorted(left_sorted, values, side="right") / left_sorted.size
    right_cdf = np.searchsorted(right_sorted, values, side="right") / right_sorted.size
    return float(np.max(np.abs(left_cdf - right_cdf)))


def _categorical_shift(
    reference_values: Iterable[object], *, target_values: Iterable[object]
) -> dict[str, Any]:
    reference = Counter(_display_label(value) for value in reference_values)
    target = Counter(_display_label(value) for value in target_values)
    levels = sorted(set(reference) | set(target))
    reference_total = sum(reference.values())
    target_total = sum(target.values())
    if not reference_total or not target_total:
        total_variation = None
    else:
        total_variation = 0.5 * sum(
            abs(reference[level] / reference_total - target[level] / target_total)
            for level in levels
        )
    return {
        "total_variation_distance": total_variation,
        "target_only_levels": sorted(set(target) - set(reference)),
        "reference_only_levels": sorted(set(reference) - set(target)),
        "reference_counts": dict(sorted(reference.items())),
        "target_counts": dict(sorted(target.items())),
    }
