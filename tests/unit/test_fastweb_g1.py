"""Check treatment routing and denominators independently of neural predictions."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location('f0_g1_evidence', Path(__file__).resolve().parents[2]/'scripts/cluster/f0_g1_evidence.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

@pytest.mark.parametrize('has_h,has_ice',[(True,True),(False,True),(False,False)])
def test_fixed_pool_routing_and_missing_scores(tmp_path, monkeypatch, has_h, has_ice):
    monkeypatch.setattr(MODULE,'canonical_inchikey14',lambda s:s)
    calls=[]
    def rerank(cands,keys,scores,forms,evidence,lams,top_n):
        calls.append(evidence)
        return list(range(len(cands)))
    spectra=pd.DataFrame([dict(molecule_id='q',spectrum_id='s',adduct='[M+H]+' if has_h else '[M+NH4]+',ionization_mode='positive',collision_energy_ev=[20.])])
    ice={'a':0.7,'b':None} if has_ice else {}
    real={'a':0.2,'b':0.8} if has_h else {}
    proxy={'a':0.1,'b':0.9}
    scope=dict(POOL_POP=[0.,0.],te=spectra,ENG={'q':{'smiles':['a','b']}},PREFUSION_LISTS={'q':['a','b']},ICE_SCORES={'q':ice},GL_REAL_SCORES={'q':real},GL_SCORES={'q':real if has_h else proxy},metric_fusion=lambda *a,**k:(['a','b'],[2.,1.],0),metric_identity=lambda s:s,ALPHA=.6,KRR=3.,chem=SimpleNamespace(score_key=lambda s:s),_form2=lambda s:'F',gl_fuse=SimpleNamespace(rerank_multi=rerank),ICE_LAM=1.,GL_LAM=1.)
    pd.DataFrame([dict(query_identity='q',candidate_smiles=s,pool_row=0,ranker_score=1.,library_confidence=0.,features='{}') for s in ['a','b']]).to_parquet(tmp_path/'raw_candidate_evidence.parquet')
    contract=tmp_path/'contract.json';contract.write_text(json.dumps(dict(truth={'q':'b'},validation='fixture')))
    MODULE.export(scope,contract,tmp_path)
    result=json.loads((tmp_path/'g1_results.json').read_text())
    assert all(v['queries']==1 and v['mrr_at25']==.5 for v in result['arms'].values())
    if has_h:
        assert calls==[[{},real]]*3
    elif has_ice:
        assert calls==[[ice],[ice],[ice,proxy]]
    else:
        assert calls==[[{}],[{},proxy],[{},proxy]]
    table=pd.read_parquet(tmp_path/'candidate_evidence.parquet')
    assert table.loc[table.candidate_smiles.eq('b'),'iceberg_score_missing'].all()
    if has_h:assert table.glacier_proxy_score.isna().all()
    assert len(pd.read_parquet(tmp_path/'candidate_spectrum_pairs.parquet'))==2
