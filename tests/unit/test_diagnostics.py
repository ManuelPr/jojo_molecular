import pytest

from casmi26.diagnostics import (
    bootstrap_paired_ranking_differences,
    bootstrap_retrieval_confidence_intervals,
    evaluate_retrieval_diagnostics,
)


def test_target_absent_reports_generation_failure_and_zero_conditional_mrr() -> None:
    result = evaluate_retrieval_diagnostics(
        {"q": "TRUE"},
        {"q": ["A", "B"]},
        {"q": ["B", "A"]},
    )

    assert result.query_count == 1
    assert result.candidate_recall_at == {25: 0.0, 100: 0.0, 1000: 0.0}
    assert result.pool_recall == 0.0
    assert result.mrr_at_25 == 0.0
    assert result.conditional_mrr_at_25 == 0.0
    assert result.oracle_mrr_at_25 == 0.0
    assert result.recovered_query_count == 0
    assert result.missing_query_ids == ("q",)


def test_target_beyond_25_separates_pool_recall_from_ranker_mrr() -> None:
    distractors = [f"D{index}" for index in range(30)]
    pool = distractors + ["TRUE"]
    result = evaluate_retrieval_diagnostics(
        {"q": "TRUE"},
        {"q": pool},
        {"q": pool},
    )

    assert result.candidate_recall_at[25] == 0.0
    assert result.candidate_recall_at[100] == 1.0
    assert result.candidate_recall_at[1000] == 1.0
    assert result.pool_recall == 1.0
    assert result.mrr_at_25 == 0.0
    assert result.conditional_mrr_at_25 == 0.0
    assert result.oracle_mrr_at_25 == 1.0


def test_identity_deduplication_uses_first_inchikey14_equivalent_candidate() -> None:
    identity_map = {
        "wrong-a": "WRONG",
        "wrong-b": "WRONG",
        "truth-a": "ABCDEFGHIJKLMN-UHFFFAOYSA-N",
        "truth-b": "ABCDEFGHIJKLMN",
    }
    result = evaluate_retrieval_diagnostics(
        {"q": "ABCDEFGHIJKLMN"},
        {"q": ["wrong-a", "wrong-b", "truth-a", "truth-b"]},
        {"q": ["wrong-a", "wrong-b", "truth-a", "truth-b"]},
        candidate_identity_keys=identity_map,
    )

    # The duplicate wrong identity and duplicate truth do not consume ranks.
    assert result.mrr_at_25 == pytest.approx(0.5)
    assert result.hit_at_1 == 0.0
    assert result.hit_at_5 == 1.0


def test_same_formula_error_counts_isomer_proxy_ahead_of_truth() -> None:
    result = evaluate_retrieval_diagnostics(
        {"isomer": "TRUTH", "right": "RIGHT"},
        {
            "isomer": ["WRONG_ISOMER", "TRUTH"],
            "right": ["RIGHT", "OTHER"],
        },
        {
            "isomer": ["WRONG_ISOMER", "TRUTH"],
            "right": ["RIGHT", "OTHER"],
        },
        candidate_formula_by_id={
            "WRONG_ISOMER": "C2H6O",
            "TRUTH": "C2H6O",
            "RIGHT": "CH4",
            "OTHER": "H2O",
        },
        truth_formula_by_query={"isomer": "C2H6O", "right": "CH4"},
    )

    assert result.same_formula_error_count == 1


def test_breakdowns_cover_mass_formula_adduct_instrument_source_and_custom_field() -> None:
    result = evaluate_retrieval_diagnostics(
        {"a": "A", "b": "B"},
        {"a": ["A"], "b": ["X"]},
        {"a": ["A"], "b": ["X"]},
        truth_formula_by_query={"a": "H2O", "b": "CO2"},
        query_metadata={
            "a": {
                "neutral_mass": 199.9,
                "adduct": "[M+H]+",
                "instrument_type": "QTOF",
                "source": "library-a",
                "fold": "seen-domain",
            },
            "b": {
                "neutral_mass": 200.0,
                "adduct": "[M-H]-",
                "instrument_type": "Orbitrap",
                "source": "library-b",
            },
        },
        breakdown_fields=(
            "mass_bin",
            "formula",
            "adduct",
            "instrument_type",
            "source",
            "fold",
        ),
    )

    assert result.breakdowns["mass_bin"]["[0,200)"]["pool_recall"] == 1.0
    assert result.breakdowns["mass_bin"]["[200,400)"]["pool_recall"] == 0.0
    assert result.breakdowns["formula"]["H2O"]["mrr_at_25"] == 1.0
    assert result.breakdowns["adduct"]["[M-H]-"]["missing_query_count"] == 1
    assert result.breakdowns["instrument_type"]["QTOF"]["query_count"] == 1
    assert result.breakdowns["source"]["library-b"]["query_count"] == 1
    assert result.breakdowns["fold"]["<missing>"]["query_count"] == 1


def test_empty_query_group_has_defined_zero_metrics() -> None:
    result = evaluate_retrieval_diagnostics({}, {}, {})

    assert result.query_count == 0
    assert result.pool_recall == 0.0
    assert result.conditional_mrr_at_25 == 0.0
    assert result.missing_query_ids == ()
    assert all(groups == {} for groups in result.breakdowns.values())


def test_ranked_candidates_must_come_from_pool_by_default() -> None:
    with pytest.raises(ValueError, match="outside its pool"):
        evaluate_retrieval_diagnostics(
            {"q": "TRUE"},
            {"q": ["A"]},
            {"q": ["TRUE"]},
        )


def test_bootstrap_is_molecule_level_bounded_and_deterministic() -> None:
    truths = {"a": "A", "b": "B", "c": "C"}
    pools = {"a": ["A"], "b": ["X", "B"], "c": ["X"]}
    rankings = {"a": ["A"], "b": ["X", "B"], "c": ["X"]}

    first = bootstrap_retrieval_confidence_intervals(
        truths,
        pools,
        rankings,
        n_bootstrap=200,
        seed=7,
    )
    second = bootstrap_retrieval_confidence_intervals(
        truths,
        pools,
        rankings,
        n_bootstrap=200,
        seed=7,
    )

    assert first == second
    assert first["mrr_at_25"]["point"] == pytest.approx(0.5)
    assert first["pool_recall"]["point"] == pytest.approx(2 / 3)
    for interval in first.values():
        assert 0.0 <= interval["lower"] <= interval["point"] <= interval["upper"] <= 1.0


def test_bootstrap_empty_queries_is_well_defined() -> None:
    intervals = bootstrap_retrieval_confidence_intervals(
        {}, {}, {}, n_bootstrap=10, seed=1
    )

    assert intervals["mrr_at_25"]["point"] == 0.0
    assert intervals["mrr_at_25"]["lower"] == 0.0
    assert intervals["mrr_at_25"]["upper"] == 0.0
    assert intervals["mrr_at_25"]["effective_bootstrap"] == 0


def test_paired_bootstrap_measures_challenger_minus_baseline() -> None:
    truths = {"a": "A", "b": "B", "c": "C"}
    pools = {"a": ["A", "X"], "b": ["B", "X"], "c": ["C", "X"]}
    baseline = {"a": ["A", "X"], "b": ["B", "X"], "c": ["C", "X"]}
    challenger = {"a": ["X", "A"], "b": ["B", "X"], "c": ["X", "C"]}
    result = bootstrap_paired_ranking_differences(
        truths,
        pools,
        baseline,
        challenger,
        n_bootstrap=200,
        seed=11,
    )
    assert result["mrr_at_25"]["point"] == pytest.approx(-1 / 3)
    assert result["hit_at_1"]["point"] == pytest.approx(-2 / 3)
    assert result == bootstrap_paired_ranking_differences(
        truths,
        pools,
        baseline,
        challenger,
        n_bootstrap=200,
        seed=11,
    )
