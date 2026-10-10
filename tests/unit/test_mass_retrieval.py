from casmi26.mass_retrieval import MassCandidateIndex, StructureCandidate, merge_candidate_hits


def candidates() -> list[StructureCandidate]:
    return [
        StructureCandidate("a", "CC", 30.04695, "C2H6"),
        StructureCandidate("b", "CO", 32.02621, "CH4O"),
        StructureCandidate("c", "CCC", 44.06260, "C3H8"),
    ]


def test_mass_candidates_are_ranked_by_ppm_error() -> None:
    index = MassCandidateIndex(candidates())
    hits = index.retrieve(32.02620, top_k=3)
    assert [hit.candidate_id for hit in hits] == ["b", "a", "c"]
    assert hits[0].features["mass_error_ppm"] < hits[1].features["mass_error_ppm"]


def test_mass_filter_and_unknown_mass() -> None:
    index = MassCandidateIndex(candidates())
    assert [hit.candidate_id for hit in index.retrieve(32.02621, tolerance_ppm=5)] == ["b"]
    assert [hit.candidate_id for hit in index.retrieve(None, top_k=2)] == ["a", "b"]


def test_mass_candidate_boundary_ties_are_deterministic() -> None:
    tied = [
        StructureCandidate(candidate_id, "CC", 100.0, "C2H6")
        for candidate_id in ("d", "b", "c", "a")
    ]
    index = MassCandidateIndex(tied)
    assert [hit.candidate_id for hit in index.retrieve(100.0, top_k=2)] == ["a", "b"]


def test_candidate_union_deduplicates_and_tracks_provenance() -> None:
    index = MassCandidateIndex(candidates())
    first = index.retrieve(32.02621, top_k=2)
    second = index.retrieve(32.02622, top_k=1)
    second[0].source = "spectral"
    second[0].retrieval_score = 0.9
    second[0].features["retrieval_score"] = 0.9
    merged = merge_candidate_hits(first, second)
    assert [hit.candidate_id for hit in merged].count("b") == 1
    assert merged[0].metadata["provenance"] == ["spectral", "structure_catalog"]
