import numpy as np
import pytest
from casmi26.pubchem_retrieval import PubChemMassIndex, screen_pubchem
from casmi26.forward_ranking import fuse_forward, ranked_unique


def fixture_index():
    text = b'ACCD'
    return PubChemMassIndex(np.array([99., 100., 100., 101.]), np.arange(5), np.frombuffer(text, dtype=np.uint8))


def test_ppm_window_retains_all_equal_mass_isomers_and_empty_windows():
    index = fixture_index()
    assert [e.smiles for e in index.iter_window(100., 10.)] == ['C', 'C']
    assert list(index.iter_window(105., 10.)) == []
    with pytest.raises(ValueError):
        index.bounds(float('nan'), 10.)


def test_external_candidate_can_reach_first_without_truth_injection():
    index = fixture_index()
    output, diag = screen_pubchem(index, 100., 20_000., coarse_score=lambda s: {'A': 0, 'C': 2, 'D': 3}[s],
        full_fingerprint=lambda s: np.array([s == 'D'], dtype=np.uint8), logits=np.array([2.]),
        canonical_key=lambda s:s, coarse_limit=3, top_k=2, exclude_keys={'C'})
    assert output[0]['key'] == 'D'
    assert diag['window_count'] == 4
    assert diag['already_in_pool'] == 1


def test_invalid_offsets_fail_instead_of_silent_empty_candidates():
    with pytest.raises(ValueError):
        PubChemMassIndex(np.array([100.]), np.array([0, 3]), np.array([65], dtype=np.uint8))


def test_forward_reverses_rank_and_preserves_fully_unsupported_cases():
    base = np.array([0.6, 0.4])
    assert np.argmax(fuse_forward(base, [0., 1.], weight=2.)) == 1
    assert np.array_equal(fuse_forward(base, [None, None]), base)
    assert np.array_equal(fuse_forward(base, [0., 1.], protected=True), base)


def test_duplicate_identities_do_not_consume_final_slots():
    indices = ranked_unique(['A', 'B', 'a'], [0.5, 0.8, 0.9], lambda s:s.upper(), top_k=2)
    assert indices == [2, 1]


def test_shared_cache_cannot_expand_an_ablation_forward_budget():
    import ast
    from pathlib import Path
    tree=ast.parse((Path(__file__).resolve().parents[2]/'kaggle/pubchem_glacier_runtime.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='rank_keys')
    ns={'np':np,'fuse_forward':fuse_forward,'ranked_unique':ranked_unique,'scorer_key':lambda s:s,
        'EXPERIMENT':{'forward_top_k':2,'library_gate':.9}}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'budget_regression','exec'),ns)
    variant={'smiles':['CCO','CNC','CCC'],'keys':['A','B','C'],'probabilities':[.8,.6,.4],'library_max':0.}
    own=ns['rank_keys'](variant,{'CCO':0.,'CNC':.1},4.)
    borrowed=ns['rank_keys'](variant,{'CCO':0.,'CNC':.1,'CCC':1.},4.)
    assert own==borrowed
    assert borrowed[0]=='B'


def test_calibration_removes_held_identities_even_as_negative_candidates():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'scripts/fit_pubchem_forward_ranker.py'
    spec=importlib.util.spec_from_file_location('calibration_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    mask=module.training_mask(np.array(['train','held','train']),np.array(['held','train','other']),{'held'})
    assert mask.tolist()==[False,False,True]


def test_submission_writer_preserves_raw_top25_cutoff_without_backfill():
    from casmi26.forward_ranking import submission_smiles
    variant={'smiles':[f'a{i}' for i in range(25)]+['b'],
             'keys':['A']*25+['B'],'probabilities':np.linspace(.99,.1,26), 'library_max':0.}
    assert submission_smiles(variant,{})==['a0']


def test_submission_writer_uses_own_forward_budget_and_protects_library_hits():
    from casmi26.forward_ranking import submission_smiles
    variant={'smiles':['A','B','C'],'keys':['A','B','C'],'probabilities':[.8,.6,.4],'library_max':0.}
    expected=submission_smiles(variant,{'A':0.,'B':.1},weight=4.,forward_top_k=2)
    assert submission_smiles(variant,{'A':0.,'B':.1,'C':1.},weight=4.,forward_top_k=2)==expected
    assert expected[0]=='B'
    variant['library_max']=.95
    assert submission_smiles(variant,{'A':0.,'B':.1,'C':1.},weight=4.)==['A','B','C']
