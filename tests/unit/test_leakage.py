from __future__ import annotations

import pytest

from casmi26.leakage import (
    LeakageDetectedError,
    assert_leakage_free,
    audit_split_leakage,
)
from casmi26.validation_contracts import SplitManifest


TRAIN_KEY = "AAAAAAAAAAAAAA"
VALIDATION_KEY = "BBBBBBBBBBBBBB"
CANDIDATE_KEY = "CCCCCCCCCCCCCC"


def _manifest(protocol: str = "molecule_disjoint", **overrides: object) -> SplitManifest:
    values = {
        "protocol": protocol,
        "seed": 2026,
        "dataset_fingerprint": "fixture-v1",
        "train_spectrum_ids": ("train-1",),
        "reference_spectrum_ids": ("reference-1",),
        "validation_spectrum_ids": ("validation-1",),
        "ranker_train_identity_keys": (TRAIN_KEY,),
        "validation_identity_keys": (VALIDATION_KEY,),
        "candidate_identity_keys": (VALIDATION_KEY, CANDIDATE_KEY),
    }
    values.update(overrides)
    return SplitManifest(**values)  # type: ignore[arg-type]


def _identity_keys() -> dict[str, str]:
    return {
        "train-1": TRAIN_KEY,
        "reference-1": TRAIN_KEY,
        "validation-1": VALIDATION_KEY,
    }


def _hashes() -> dict[str, str]:
    return {
        "train-1": "hash-train",
        "reference-1": "hash-reference",
        "validation-1": "hash-validation",
    }


def _audit(manifest: SplitManifest, **overrides: object):
    values = {
        "spectrum_identity_keys": _identity_keys(),
        "spectrum_hashes": _hashes(),
        "feature_provenance": {
            "direct_cosine": ("query_spectrum", "reference_spectrum"),
            "mass_error_ppm": ("query_precursor", "candidate_exact_mass"),
        },
    }
    values.update(overrides)
    return audit_split_leakage(manifest, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize("protocol", ["molecule_disjoint", "novelty_holdout"])
def test_clean_disjoint_audit_passes(protocol: str) -> None:
    candidate_keys = (CANDIDATE_KEY,) if protocol == "novelty_holdout" else (VALIDATION_KEY,)
    report = _audit(_manifest(protocol, candidate_identity_keys=candidate_keys))

    assert report.passed
    assert report.issues == ()
    assert report.checks["protocol_identity_separation"] is True
    assert report.checks["spectral_content_separation"] is True


def test_library_holdout_allows_shared_identity_but_not_shared_observation() -> None:
    manifest = _manifest(
        "library_holdout",
        ranker_train_identity_keys=(VALIDATION_KEY,),
    )
    identities = _identity_keys()
    identities["train-1"] = VALIDATION_KEY
    identities["reference-1"] = VALIDATION_KEY

    report = _audit(manifest, spectrum_identity_keys=identities)

    assert report.passed


def test_adversarial_identity_leakage_is_detected() -> None:
    manifest = _manifest(ranker_train_identity_keys=(TRAIN_KEY, VALIDATION_KEY))

    report = _audit(manifest)

    assert not report.passed
    issue = next(issue for issue in report.issues if issue.code == "identity_leakage")
    assert any(VALIDATION_KEY in item and "ranker_train" in item for item in issue.evidence)


def test_adversarial_reference_identity_leakage_is_detected() -> None:
    identities = _identity_keys()
    identities["reference-1"] = VALIDATION_KEY

    report = _audit(_manifest(), spectrum_identity_keys=identities)

    assert not report.passed
    assert "identity_leakage" in {issue.code for issue in report.issues}


def test_adversarial_spectral_duplicate_is_detected() -> None:
    hashes = _hashes()
    hashes["validation-1"] = hashes["reference-1"]

    report = _audit(_manifest(), spectrum_hashes=hashes)

    assert not report.passed
    issue = next(issue for issue in report.issues if issue.code == "spectral_duplicate_leakage")
    assert "reference/validation" in issue.evidence[0]


def test_adversarial_novelty_candidate_contamination_is_detected() -> None:
    manifest = _manifest(
        "novelty_holdout",
        candidate_identity_keys=(CANDIDATE_KEY, VALIDATION_KEY),
    )

    report = _audit(manifest)

    assert not report.passed
    assert "novelty_candidate_contamination" in {issue.code for issue in report.issues}


def test_adversarial_target_derived_feature_is_detected() -> None:
    provenance = {
        "mass_error_ppm": ("query_precursor", "candidate_exact_mass"),
        "was_correct_in_validation": ("validation_target.inchikey14",),
    }

    report = _audit(_manifest(), feature_provenance=provenance)

    assert not report.passed
    issue = next(issue for issue in report.issues if issue.code == "target_derived_feature")
    assert issue.evidence == (
        "was_correct_in_validation<-validation_target.inchikey14",
    )


def test_ranker_may_not_train_on_validation_observations() -> None:
    report = _audit(
        _manifest(),
        ranker_train_spectrum_ids=("train-1", "validation-1"),
    )

    assert not report.passed
    assert "ranker_observation_leakage" in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    ("override", "expected_code"),
    [
        ({"spectrum_identity_keys": None}, "missing_spectrum_identity"),
        ({"spectrum_hashes": None}, "missing_spectrum_hash"),
        ({"feature_provenance": None}, "missing_feature_provenance"),
    ],
)
def test_audit_cannot_pass_when_required_evidence_is_omitted(
    override: dict[str, object], expected_code: str
) -> None:
    report = _audit(_manifest(), **override)

    assert not report.passed
    assert expected_code in {issue.code for issue in report.issues}


def test_noncanonical_identity_and_manifest_mismatch_are_detected() -> None:
    identities = _identity_keys()
    identities["validation-1"] = "bbbbbbbbbbbbbb"

    report = _audit(_manifest(), spectrum_identity_keys=identities)

    codes = {issue.code for issue in report.issues}
    assert "non_normalized_identity_key" in codes


def test_declared_identity_sets_must_match_observed_partitions() -> None:
    report = _audit(
        _manifest(
            ranker_train_identity_keys=(TRAIN_KEY, CANDIDATE_KEY),
            validation_identity_keys=(VALIDATION_KEY, CANDIDATE_KEY),
        )
    )
    codes = {issue.code for issue in report.issues}
    assert "ranker_train_identity_mismatch" in codes
    assert "validation_identity_mismatch" in codes


def test_assertion_api_exposes_structured_report() -> None:
    with pytest.raises(LeakageDetectedError) as caught:
        assert_leakage_free(
            _manifest("novelty_holdout"),
            spectrum_identity_keys=_identity_keys(),
            spectrum_hashes=_hashes(),
            feature_provenance={},
        )

    assert not caught.value.report.passed
    assert caught.value.report.protocol == "novelty_holdout"
