import pytest
from casmi26.pubchem_consensus import promote_consensus


@pytest.mark.parametrize('eligible,score,expected', [
    (False, .9, 'protected_or_unconfident'),
    (True, .9, 'promoted'),
    (True, .5, 'no_strict_forward_agreement'),
    (True, float('nan'), 'insufficient_forward_coverage'),
])
def test_gating_and_strict_agreement(eligible, score, expected):
    before = ['a', 'b', 'x', 'y']
    after, reason = promote_consensus(before, ['x', 'y'], ['a', 'b'],
        {'a': .5, 'b': .3, 'x': score, 'y': .4}, eligible=eligible)
    assert reason == expected
    assert after == (['x', 'a', 'b', 'y'] if expected == 'promoted' else before)


def test_missing_source_cannot_be_interpreted_as_negative_evidence():
    before = ['a', 'b', 'x']
    after, reason = promote_consensus(before, ['x', 'y'], ['a', 'b'],
        {'a': .1, 'x': .9, 'y': .2}, eligible=True)
    assert after == before and reason == 'insufficient_forward_coverage'


def test_external_identity_and_rank_limit():
    before = [f'b{i}' for i in range(25)]
    after, reason = promote_consensus(before, ['x', 'y'], before,
        {'b0': .1, 'b1': .2, 'x': .9, 'y': .3}, eligible=True)
    assert reason == 'promoted' and after == ['x'] + before[:24]
    assert len(set(after)) == 25
    unchanged, reason = promote_consensus(before, ['b0', 'y'], before,
        {'b0': .9, 'b1': .2, 'y': .3}, eligible=True)
    assert unchanged == before and reason == 'not_external'
