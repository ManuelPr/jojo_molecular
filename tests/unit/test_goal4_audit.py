from __future__ import annotations

import pytest

from casmi26.goal4_audit import (
    CandidateDescriptor,
    ConstructionProvenance,
    QueryMetadata,
    assert_realistic_integrity,
    audit_construction_integrity,
    audit_realistic_benchmark,
    explain_recall_at_100,
)


def _fixture():
    candidates = {
        "T1": CandidateDescriptor("T1", "AAAAAAAAAAAAAA", 100.0, "C5H8O2", ("train",)),
        "I1": CandidateDescriptor("I1", "BBBBBBBBBBBBBB", 100.0003, "C5H8O2", ("train",)),
        "D1": CandidateDescriptor("D1", "CCCCCCCCCCCCCC", 100.0008, "C6H12O", ("train",)),
        "T2": CandidateDescriptor("T2", "DDDDDDDDDDDDDD", 200.0, "C10H16O4", ("train",)),
        "D2": CandidateDescriptor("D2", "EEEEEEEEEEEEEE", 200.003, "C11H20O3", ("train",)),
    }
    truths = {"q1": "AAAAAAAAAAAAAA", "q2": "DDDDDDDDDDDDDD"}
    catalog = tuple(candidates)
    pools = {"q1": ["I1", "D1", "T1"], "q2": ["D2", "T2"]}
    rankings = {"q1": ["I1", "T1", "D1"], "q2": ["T2", "D2"]}
    metadata = {
        "q1": QueryMetadata(
            100.0,
            "C5H8O2",
            "[M+H]+",
            "timsTOF",
            3,
            "enveda-180",
            spectral_evidence_informative=True,
            ranker_used_informative_evidence=False,
        ),
        "q2": QueryMetadata(
            200.0, "C10H16O4", "[M-H]-", "QTOF", 1, "other"
        ),
    }
    provenance = ConstructionProvenance(
        mode="realistic",
        catalog_selection_policy="source_order_target_blind",
        catalog_source_count=5,
        catalog_selected_count=5,
        pool_target_consulted={"q1": False, "q2": False},
        pool_target_injected={"q1": False, "q2": False},
    )
    return candidates, truths, catalog, pools, rankings, metadata, provenance


def test_goal4_audit_reports_ppm_ambiguity_breakdowns_and_error_taxonomy() -> None:
    candidates, truths, catalog, pools, rankings, metadata, provenance = _fixture()
    report = audit_realistic_benchmark(
        truth_keys=truths,
        catalog_candidate_ids=catalog,
        candidate_pools=pools,
        rankings=rankings,
        candidates=candidates,
        query_metadata=metadata,
        provenance=provenance,
    )

    assert report.integrity.passed
    assert report.summary["query_count"] == 2
    assert report.summary["candidate_recall_at_25"] == 1.0
    assert report.summary["candidate_recall_at_100"] == 1.0
    assert report.summary["mrr_at_25"] == pytest.approx(0.75)
    q1 = next(row for row in report.per_query if row["query_id"] == "q1")
    assert q1["candidates_within_ppm"] == {"5": 2, "10": 3, "20": 3, "50": 3}
    assert q1["same_formula_competitors"] == 1
    assert "constitutional_isomer_proxy" in q1["error_flags"]
    assert "informative_features_not_exploited" in q1["error_flags"]
    assert report.breakdowns["adduct"]["[M+H]+"]["query_count"] == 1
    assert report.breakdowns["instrument"]["QTOF"]["mrr_at_25"] == 1.0


def test_recall_at_100_explanation_requires_audited_non_oracle_construction() -> None:
    candidates, truths, catalog, pools, rankings, metadata, provenance = _fixture()
    report = audit_realistic_benchmark(
        truth_keys=truths,
        catalog_candidate_ids=catalog,
        candidate_pools=pools,
        rankings=rankings,
        candidates=candidates,
        query_metadata=metadata,
        provenance=provenance,
    )
    explanation = explain_recall_at_100(report)
    assert explanation["recall_at_100_is_one"]
    assert explanation["maximum_truth_rank"] == 3
    assert not explanation["target_consultation_detected"]
    assert not explanation["target_injection_detected"]


def test_realistic_integrity_fails_on_target_consultation_or_injection() -> None:
    candidates, truths, catalog, pools, _, _, _ = _fixture()
    provenance = ConstructionProvenance(
        mode="realistic",
        catalog_selection_policy="validation_target_priority",
        catalog_source_count=5,
        catalog_selected_count=5,
        catalog_target_ids_consulted=("AAAAAAAAAAAAAA",),
        validation_identities_used=("AAAAAAAAAAAAAA",),
        pool_target_consulted={"q1": True, "q2": False},
        pool_target_injected={"q1": True, "q2": False},
    )
    integrity = audit_construction_integrity(
        provenance,
        truth_keys=truths,
        catalog_candidate_ids=catalog,
        candidate_pools=pools,
        candidates=candidates,
    )
    assert not integrity.passed
    assert len(integrity.violations) >= 4
    with pytest.raises(AssertionError):
        assert_realistic_integrity(integrity)


def test_pool_candidate_outside_catalog_fails_closed() -> None:
    candidates, truths, catalog, pools, _, _, provenance = _fixture()
    pools["q1"] = ["T1", "UNKNOWN"]
    integrity = audit_construction_integrity(
        provenance,
        truth_keys=truths,
        catalog_candidate_ids=catalog,
        candidate_pools=pools,
        candidates=candidates,
    )
    assert not integrity.passed
    assert any("outside the catalog" in item for item in integrity.violations)


def test_inchikey14_duplicate_does_not_consume_rank() -> None:
    candidates, truths, catalog, pools, rankings, metadata, provenance = _fixture()
    candidates["T1_alias"] = CandidateDescriptor(
        "T1_alias", "AAAAAAAAAAAAAA", 100.0, "C5H8O2", ("external",)
    )
    catalog = (*catalog, "T1_alias")
    pools["q1"] = ["I1", "T1_alias", "T1"]
    rankings["q1"] = ["I1", "T1_alias", "T1"]
    report = audit_realistic_benchmark(
        truth_keys=truths,
        catalog_candidate_ids=catalog,
        candidate_pools=pools,
        rankings=rankings,
        candidates=candidates,
        query_metadata=metadata,
        provenance=ConstructionProvenance(
            mode="realistic",
            catalog_selection_policy="source_order_target_blind",
            catalog_source_count=6,
            catalog_selected_count=6,
            pool_target_consulted={"q1": False, "q2": False},
            pool_target_injected={"q1": False, "q2": False},
        ),
    )
    q1 = next(row for row in report.per_query if row["query_id"] == "q1")
    assert q1["pool_rank"] == 2
    assert q1["pool_size"] == 2

