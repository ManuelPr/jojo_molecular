from __future__ import annotations

from collections.abc import Iterable, Mapping
import re

from .validation_contracts import LeakageAuditReport, LeakageIssue, SplitManifest


_INCHIKEY14_RE = re.compile(r"^[A-Z]{14}$")
_PARTITIONS = ("train", "reference", "validation")
_DEFAULT_DUPLICATE_HASH_PAIRS = (
    ("train", "reference"),
    ("train", "validation"),
    ("reference", "validation"),
)

# These are lineage labels, not substrings to search for in numeric feature names.
# Callers should add project-specific forbidden labels when auditing a new feature set.
DEFAULT_FORBIDDEN_FEATURE_PROVENANCE = frozenset(
    {
        "ground_truth",
        "is_correct",
        "target_identity",
        "target_inchikey",
        "target_rank",
        "target_smiles",
        "validation_label",
        "validation_target",
    }
)


class LeakageDetectedError(RuntimeError):
    """Raised when a leakage audit is requested in fail-fast mode."""

    def __init__(self, report: LeakageAuditReport):
        self.report = report
        codes = ", ".join(issue.code for issue in report.issues)
        super().__init__(f"Leakage audit failed for {report.protocol}: {codes}")


def audit_split_leakage(
    manifest: SplitManifest,
    *,
    spectrum_identity_keys: Mapping[str, str] | None,
    spectrum_hashes: Mapping[str, str] | None,
    ranker_train_spectrum_ids: Iterable[str] | None = None,
    feature_provenance: Mapping[str, str | Iterable[str]] | None = None,
    forbidden_feature_provenance: Iterable[str] = DEFAULT_FORBIDDEN_FEATURE_PROVENANCE,
    duplicate_hash_forbidden_pairs: Iterable[tuple[str, str]] = _DEFAULT_DUPLICATE_HASH_PAIRS,
    raise_on_error: bool = False,
) -> LeakageAuditReport:
    """Audit a split and its feature lineage for validation contamination.

    ``spectrum_identity_keys`` and ``spectrum_hashes`` deliberately are required
    keyword arguments (although ``None`` is accepted to produce a failed report).
    A passing audit therefore proves that every spectrum in the manifest had both
    its normalized chemical identity and content hash inspected; it cannot pass
    merely because the caller omitted evidence.

    Identity overlap is protocol-aware: library holdout permits the same chemical
    identity in reference and validation acquisitions, molecule-disjoint forbids
    validation identities in supervised/reference data but permits them in the
    unlabeled candidate database, and novelty holdout additionally forbids them
    in the candidate database.
    """

    issues: list[LeakageIssue] = []
    checks: dict[str, int | bool] = {}
    partitions = _partition_ids(manifest)

    _audit_membership(partitions, issues, checks)
    _audit_identity_keys(manifest, spectrum_identity_keys, partitions, issues, checks)
    _audit_spectrum_hashes(
        partitions,
        spectrum_hashes,
        duplicate_hash_forbidden_pairs,
        issues,
        checks,
    )
    _audit_ranker_observations(
        manifest,
        ranker_train_spectrum_ids,
        issues,
        checks,
    )
    _audit_feature_lineage(
        feature_provenance,
        forbidden_feature_provenance,
        issues,
        checks,
    )

    report = LeakageAuditReport(
        protocol=manifest.protocol,
        passed=not issues,
        issues=tuple(issues),
        checks=checks,
    )
    if raise_on_error and not report.passed:
        raise LeakageDetectedError(report)
    return report


def assert_leakage_free(
    manifest: SplitManifest,
    **audit_kwargs: object,
) -> LeakageAuditReport:
    """Run :func:`audit_split_leakage` and raise on the first failed audit."""

    return audit_split_leakage(manifest, raise_on_error=True, **audit_kwargs)  # type: ignore[arg-type]


def _partition_ids(manifest: SplitManifest) -> dict[str, tuple[str, ...]]:
    return {
        "train": manifest.train_spectrum_ids,
        "reference": manifest.reference_spectrum_ids,
        "validation": manifest.validation_spectrum_ids,
    }


def _audit_membership(
    partitions: Mapping[str, tuple[str, ...]],
    issues: list[LeakageIssue],
    checks: dict[str, int | bool],
) -> None:
    duplicate_within: list[str] = []
    for name, identifiers in partitions.items():
        duplicates = _duplicates(identifiers)
        duplicate_within.extend(f"{name}:{value}" for value in duplicates)

    cross_overlap: list[str] = []
    for index, left in enumerate(_PARTITIONS):
        for right in _PARTITIONS[index + 1 :]:
            overlap = set(partitions[left]) & set(partitions[right])
            cross_overlap.extend(f"{left}/{right}:{value}" for value in sorted(overlap))

    checks["spectrum_membership_unique"] = not duplicate_within and not cross_overlap
    checks["duplicate_spectrum_id_count"] = len(duplicate_within) + len(cross_overlap)
    if duplicate_within or cross_overlap:
        issues.append(
            LeakageIssue(
                code="spectrum_membership_overlap",
                message="Spectrum IDs must be unique within and across split partitions.",
                evidence=_evidence(duplicate_within + cross_overlap),
            )
        )


def _audit_identity_keys(
    manifest: SplitManifest,
    spectrum_identity_keys: Mapping[str, str] | None,
    partitions: Mapping[str, tuple[str, ...]],
    issues: list[LeakageIssue],
    checks: dict[str, int | bool],
) -> None:
    declared_groups = {
        "ranker_train": manifest.ranker_train_identity_keys,
        "validation": manifest.validation_identity_keys,
        "candidate": manifest.candidate_identity_keys,
    }
    invalid_declared: list[str] = []
    duplicate_declared: list[str] = []
    for name, keys in declared_groups.items():
        invalid_declared.extend(f"{name}:{key}" for key in keys if not _is_normalized_key(key))
        duplicate_declared.extend(f"{name}:{key}" for key in _duplicates(keys))

    expected_ids = set().union(*(set(values) for values in partitions.values()))
    missing_mapping: list[str] = []
    invalid_observed: list[str] = []
    if spectrum_identity_keys is None:
        missing_mapping = sorted(expected_ids)
        observed: Mapping[str, str] = {}
    else:
        observed = spectrum_identity_keys
        missing_mapping = sorted(expected_ids - set(observed))
        invalid_observed = sorted(
            f"{spectrum_id}:{observed[spectrum_id]}"
            for spectrum_id in expected_ids & set(observed)
            if not _is_normalized_key(observed[spectrum_id])
        )

    checks["identity_mapping_complete"] = not missing_mapping
    checks["normalized_identity_keys"] = not invalid_declared and not invalid_observed
    checks["duplicate_declared_identity_count"] = len(duplicate_declared)
    if missing_mapping:
        issues.append(
            LeakageIssue(
                code="missing_spectrum_identity",
                message="Every manifest spectrum needs a normalized InChIKey14 for audit.",
                evidence=_evidence(missing_mapping),
            )
        )
    if invalid_declared or invalid_observed:
        issues.append(
            LeakageIssue(
                code="non_normalized_identity_key",
                message="Identity keys must be canonical 14-character uppercase InChIKey blocks.",
                evidence=_evidence(invalid_declared + invalid_observed),
            )
        )
    if duplicate_declared:
        issues.append(
            LeakageIssue(
                code="duplicate_declared_identity",
                message="Identity collections in the manifest must be deduplicated.",
                evidence=_evidence(duplicate_declared),
            )
        )

    validation_declared = set(manifest.validation_identity_keys)
    mapped_validation = {
        observed[spectrum_id]
        for spectrum_id in partitions["validation"]
        if spectrum_id in observed and _is_normalized_key(observed[spectrum_id])
    }
    mismatched_validation = mapped_validation ^ validation_declared
    checks["validation_identity_mapping_consistent"] = not mismatched_validation
    if mismatched_validation:
        issues.append(
            LeakageIssue(
                code="validation_identity_mismatch",
                message="Validation spectrum identities disagree with the manifest identity set.",
                evidence=_evidence(sorted(mismatched_validation)),
            )
        )

    mapped_train = {
        observed[spectrum_id]
        for spectrum_id in partitions["train"]
        if spectrum_id in observed and _is_normalized_key(observed[spectrum_id])
    }
    declared_train = set(manifest.ranker_train_identity_keys)
    mismatched_train = mapped_train ^ declared_train
    checks["ranker_train_identity_mapping_consistent"] = not mismatched_train
    if mismatched_train:
        issues.append(
            LeakageIssue(
                code="ranker_train_identity_mismatch",
                message="Ranker-training spectrum identities disagree with the manifest identity set.",
                evidence=_evidence(sorted(mismatched_train)),
            )
        )

    forbidden_supervised_overlap: set[str] = set()
    forbidden_reference_overlap: set[str] = set()
    if manifest.protocol in {"molecule_disjoint", "novelty_holdout"}:
        forbidden_supervised_overlap = validation_declared & set(manifest.ranker_train_identity_keys)
        mapped_reference = {
            observed[spectrum_id]
            for spectrum_id in partitions["reference"]
            if spectrum_id in observed and _is_normalized_key(observed[spectrum_id])
        }
        forbidden_reference_overlap = validation_declared & mapped_reference

    identity_overlap = sorted(forbidden_supervised_overlap | forbidden_reference_overlap)
    checks["forbidden_identity_overlap_count"] = len(identity_overlap)
    checks["protocol_identity_separation"] = not identity_overlap
    if identity_overlap:
        sources = []
        for key in identity_overlap:
            locations = []
            if key in forbidden_supervised_overlap:
                locations.append("ranker_train")
            if key in forbidden_reference_overlap:
                locations.append("reference")
            sources.append(f"{key}:{'+'.join(locations)}")
        issues.append(
            LeakageIssue(
                code="identity_leakage",
                message="Validation identities occur in a protocol-forbidden supervised or reference set.",
                evidence=_evidence(sources),
            )
        )

    novelty_overlap = (
        validation_declared & set(manifest.candidate_identity_keys)
        if manifest.protocol == "novelty_holdout"
        else set()
    )
    checks["novelty_candidate_overlap_count"] = len(novelty_overlap)
    checks["novelty_candidate_separation"] = not novelty_overlap
    if novelty_overlap:
        issues.append(
            LeakageIssue(
                code="novelty_candidate_contamination",
                message="Novelty validation identities occur in the candidate database.",
                evidence=_evidence(sorted(novelty_overlap)),
            )
        )


def _audit_spectrum_hashes(
    partitions: Mapping[str, tuple[str, ...]],
    spectrum_hashes: Mapping[str, str] | None,
    forbidden_pairs: Iterable[tuple[str, str]],
    issues: list[LeakageIssue],
    checks: dict[str, int | bool],
) -> None:
    expected_ids = set().union(*(set(values) for values in partitions.values()))
    if spectrum_hashes is None:
        hashes: Mapping[str, str] = {}
        missing = sorted(expected_ids)
    else:
        hashes = spectrum_hashes
        missing = sorted(
            spectrum_id
            for spectrum_id in expected_ids
            if spectrum_id not in hashes or not str(hashes[spectrum_id]).strip()
        )
    checks["spectrum_hash_mapping_complete"] = not missing
    if missing:
        issues.append(
            LeakageIssue(
                code="missing_spectrum_hash",
                message="Every manifest spectrum needs a non-empty content hash for audit.",
                evidence=_evidence(missing),
            )
        )

    invalid_pairs: list[str] = []
    normalized_pairs: list[tuple[str, str]] = []
    for left, right in forbidden_pairs:
        if left not in partitions or right not in partitions or left == right:
            invalid_pairs.append(f"{left}/{right}")
        else:
            normalized_pairs.append((left, right))
    if invalid_pairs:
        issues.append(
            LeakageIssue(
                code="invalid_hash_policy",
                message="Duplicate-hash policy names an invalid partition pair.",
                evidence=_evidence(sorted(invalid_pairs)),
            )
        )

    collisions: list[str] = []
    for left, right in normalized_pairs:
        left_by_hash = _ids_by_hash(partitions[left], hashes)
        right_by_hash = _ids_by_hash(partitions[right], hashes)
        for digest in sorted(set(left_by_hash) & set(right_by_hash)):
            collisions.append(
                f"{left}/{right}:{digest}:"
                f"{','.join(left_by_hash[digest])}|{','.join(right_by_hash[digest])}"
            )
    checks["cross_partition_duplicate_hash_count"] = len(collisions)
    checks["spectral_content_separation"] = not collisions
    if collisions:
        issues.append(
            LeakageIssue(
                code="spectral_duplicate_leakage",
                message="A spectrum content hash occurs across a forbidden partition pair.",
                evidence=_evidence(collisions),
            )
        )


def _audit_ranker_observations(
    manifest: SplitManifest,
    ranker_train_spectrum_ids: Iterable[str] | None,
    issues: list[LeakageIssue],
    checks: dict[str, int | bool],
) -> None:
    training_ids = set(
        manifest.train_spectrum_ids
        if ranker_train_spectrum_ids is None
        else ranker_train_spectrum_ids
    )
    overlap = training_ids & set(manifest.validation_spectrum_ids)
    checks["ranker_validation_observation_overlap_count"] = len(overlap)
    checks["ranker_observation_separation"] = not overlap
    if overlap:
        issues.append(
            LeakageIssue(
                code="ranker_observation_leakage",
                message="Validation observations were used to train the supervised ranker.",
                evidence=_evidence(sorted(overlap)),
            )
        )


def _audit_feature_lineage(
    feature_provenance: Mapping[str, str | Iterable[str]] | None,
    forbidden: Iterable[str],
    issues: list[LeakageIssue],
    checks: dict[str, int | bool],
) -> None:
    if feature_provenance is None:
        checks["feature_provenance_supplied"] = False
        checks["target_derived_feature_count"] = 0
        issues.append(
            LeakageIssue(
                code="missing_feature_provenance",
                message="Feature provenance must be supplied, including an empty mapping when no features exist.",
            )
        )
        return

    checks["feature_provenance_supplied"] = True
    forbidden_labels = {_normalize_lineage(value) for value in forbidden if str(value).strip()}
    contaminated: list[str] = []
    for feature_name, sources in feature_provenance.items():
        lineage = (sources,) if isinstance(sources, str) else tuple(sources)
        values = (feature_name, *lineage)
        matches = [value for value in values if _lineage_forbidden(value, forbidden_labels)]
        contaminated.extend(f"{feature_name}<-{value}" for value in matches)

    checks["audited_feature_count"] = len(feature_provenance)
    checks["target_derived_feature_count"] = len(contaminated)
    checks["feature_target_separation"] = not contaminated
    if contaminated:
        issues.append(
            LeakageIssue(
                code="target_derived_feature",
                message="A ranker feature is derived from validation targets or labels.",
                evidence=_evidence(sorted(contaminated)),
            )
        )


def _is_normalized_key(value: object) -> bool:
    return isinstance(value, str) and _INCHIKEY14_RE.fullmatch(value) is not None


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _ids_by_hash(
    spectrum_ids: Iterable[str],
    hashes: Mapping[str, str],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for spectrum_id in spectrum_ids:
        digest = str(hashes.get(spectrum_id, "")).strip()
        if digest:
            result.setdefault(digest, []).append(spectrum_id)
    return result


def _normalize_lineage(value: object) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")


def _lineage_forbidden(value: object, forbidden: set[str]) -> bool:
    normalized = _normalize_lineage(value)
    return any(
        normalized == label
        or normalized.startswith(label + ".")
        or normalized.startswith(label + ":")
        or normalized.startswith(label + "/")
        for label in forbidden
    )


def _evidence(values: Iterable[str], limit: int = 25) -> tuple[str, ...]:
    ordered = list(values)
    if len(ordered) <= limit:
        return tuple(ordered)
    return tuple(ordered[:limit] + [f"... and {len(ordered) - limit} more"])
