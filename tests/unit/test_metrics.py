import pytest

from casmi26.metrics import mean_reciprocal_rank_at_k, reciprocal_rank


def test_reciprocal_rank_uses_first_correct_tautomer_key() -> None:
    assert reciprocal_rank("CCO", ["CC", "OCC", "CCC"]) == pytest.approx(0.5)


def test_reciprocal_rank_is_zero_when_absent() -> None:
    assert reciprocal_rank("CCO", ["CC", "CCC"]) == 0.0


def test_mrr_at_25() -> None:
    truths = {"a": "CCO", "b": "CCN"}
    predictions = {"a": ["OCC"], "b": ["CCC", "NCC"]}
    assert mean_reciprocal_rank_at_k(truths, predictions) == pytest.approx(0.75)


def test_mrr_rejects_missing_molecule() -> None:
    with pytest.raises(ValueError, match="Missing predictions"):
        mean_reciprocal_rank_at_k({"a": "CCO"}, {})

