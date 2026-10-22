import numpy as np

from casmi26.selective_pubchem import eligible_for_pubchem, external_ranked_keys, insert_external


def test_gate_protects_library_and_confident_ranker():
    assert not eligible_for_pubchem({'library_max': .91, 'probabilities': [.01]})
    assert not eligible_for_pubchem({'library_max': .1, 'probabilities': [.31]})
    assert eligible_for_pubchem({'library_max': .1, 'probabilities': [.29]})


def test_pubchem_only_order_and_base_first_are_preserved():
    variant = {'keys': ['a', 'x', 'y', 'x'], 'smiles': ['A', 'X', 'Y', 'X2'],
               'external_flags': [0, 1, 1, 1], 'probabilities': [.9, .4, .5, .3]}
    assert external_ranked_keys(variant) == [('y', 'Y'), ('x', 'X')]
    base = ['A', 'B', 'C', 'D', 'E', 'F']
    identity = {'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd', 'E': 'e', 'F': 'f',
                'X': 'x', 'Y': 'y'}
    result = insert_external(base, external_ranked_keys(variant), identity.get,
                             slots=(4, 8, 12, 16, 20))
    assert result[:5] == ['A', 'B', 'C', 'Y', 'D']
    assert result[7] == 'X'
    assert len({identity[s] for s in result}) == len(result)
    assert np.isfinite(variant['probabilities']).all()
