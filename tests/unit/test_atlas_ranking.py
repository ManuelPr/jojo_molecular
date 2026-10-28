import numpy as np
import pytest

from casmi26.atlas_ranking import (cosine, leader_safe_fusion, paired_bootstrap,
                                 prepare_spectrum, ranks, score_atlas)
from casmi26.spectral_evidence import cosine_similarity


def test_cosine_matches_reference_including_ambiguous_peaks():
    rng = np.random.default_rng(42)
    for _ in range(20):
        qm = np.sort(rng.uniform(50, 51, 24))
        rm = np.sort(rng.uniform(50, 51, 30))
        qi, ri = rng.uniform(.01, 1, 24), rng.uniform(.01, 1, 30)
        q = prepare_spectrum(qm, qi, 500, 20)
        r = prepare_spectrum(rm, ri, 500, 20)
        expected = cosine_similarity(qm, qi, rm, ri, tolerance_da=.02).score
        assert cosine(q, r) == pytest.approx(expected, abs=1e-12)


def test_precursor_and_duplicates_are_handled_symmetrically():
    q = prepare_spectrum([100, 100, 200, 299.9, 300], [1, 2, 3, 10, 100], 300, 20)
    np.testing.assert_array_equal(q.mz, [100, 200])
    assert cosine(q, q) == pytest.approx(1.)
    empty = prepare_spectrum([300], [1], 300, 20)
    assert cosine(q, empty) == 0


def test_energy_selection_and_multi_spectrum_aggregation():
    q1 = prepare_spectrum([100], [1], 500, 10)
    q2 = prepare_spectrum([200], [1], 500, 30)
    wrong_low = prepare_spectrum([200], [1], 500, 10)
    wrong_high = prepare_spectrum([100], [1], 500, 30)
    scores = score_atlas([q1, q2], [[q1, q2], [wrong_low, wrong_high], []])
    np.testing.assert_allclose(scores['atlas_max'], [1, 1, 0])
    np.testing.assert_allclose(scores['atlas_nearest'], [1, 0, 0])
    unknown = prepare_spectrum([100], [1], 500, None)
    assert score_atlas([unknown], [[q1, q2]])['atlas_nearest'][0] == 1


def test_stable_ties_and_leader_protection():
    keys = ['B', 'A', 'C']
    np.testing.assert_array_equal(ranks([0, 0, 0], keys), [2, 1, 3])
    score = leader_safe_fusion([3, 2, 1], [0, 100, 5], keys, atlas_weight=100)
    assert ranks(score, keys)[0] == 1
    with pytest.raises(ValueError, match='unique'):
        ranks([1, 2], ['A', 'A'])


def test_bootstrap_is_paired_and_reproducible():
    delta = [.5, -.5, 0, 0]
    assert paired_bootstrap(delta) == paired_bootstrap(delta)
    assert paired_bootstrap(delta)['mean'] == 0
    assert paired_bootstrap([.25]*10)['ci95'] == [.25, .25]
