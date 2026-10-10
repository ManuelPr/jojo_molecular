from pathlib import Path

import pytest

from casmi26.ranking import SupervisedRanker
from casmi26.schemas import CandidateHit
from casmi26.submission import clean_candidates, validate_submission, write_submission


def hit(candidate_id: str, score: float) -> CandidateHit:
    features = {
        "direct_cosine": score,
        "shifted_cosine": score,
        "neutral_loss_cosine": score,
        "entropy_similarity": score,
        "matched_peaks": score * 10,
        "query_coverage": score,
        "reference_coverage": score,
        "mass_error_ppm": 1.0 - score,
        "abs_precursor_delta": 1.0 - score,
        "same_adduct": 1.0,
        "same_ion_mode": 1.0,
        "peak_count_ratio": score,
        "retrieval_score": score,
    }
    return CandidateHit(candidate_id, "CCO" if candidate_id == "truth" else "CCN", None, 1, score, features)


def test_supervised_ranker_fits_saves_and_loads(tmp_path: Path) -> None:
    groups = {
        f"q{i}": [hit("truth", 0.9 - i * 0.01), hit(f"negative-{i}", 0.1 + i * 0.01)]
        for i in range(8)
    }
    truths = {query_id: "truth" for query_id in groups}
    ranker = SupervisedRanker()
    summary = ranker.fit(groups, truths)
    assert summary.positive_count == 8
    path = tmp_path / "ranker.joblib"
    ranker.save(path)
    loaded = SupervisedRanker.load(path)
    assert loaded.rank(groups["q0"])[0].candidate_id == "truth"


def test_submission_writer_canonical_dedup_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "submission.csv"
    validation = write_submission(
        {"m1": ["CCO", "OCC", "CCN"], "m2": ["CCC"]},
        ["m1", "m2"],
        path,
    )
    assert validation.valid
    assert clean_candidates(["CCO", "OCC", "invalid"]) == ["CCO"]
    assert validate_submission(path, expected_molecule_ids=["m1", "m2"]).valid


def test_submission_validator_rejects_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("molecule_id,smiles\nm1,CCO;OCC\n", encoding="utf-8")
    result = validate_submission(path, expected_molecule_ids=["m1"])
    assert not result.valid
    assert any("duplicate canonical" in error for error in result.errors)

