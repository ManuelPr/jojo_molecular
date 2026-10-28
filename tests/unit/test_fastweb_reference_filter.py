import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

SPEC=importlib.util.spec_from_file_location('filter_f0_reference_cache',Path(__file__).resolve().parents[2]/'scripts/cluster/filter_f0_reference_cache.py')
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)


def make_cache(path):
    path.mkdir()
    pd.DataFrame({'inchikey14':['raw0','raw1','raw2','raw3'],'sid':[0,1,2,3]}).to_parquet(path/'train_structs.parquet')
    pd.DataFrame({'sid':[0,1,2,1,3],'n_clean':[2,1,3,0,2]}).to_parquet(path/'spec_meta.parquet')
    np.save(path/'spec_off.npy',np.array([0,2,3,6,6,8],dtype=np.int64))
    np.save(path/'spec_mz.npy',np.arange(8,dtype=np.float32))
    np.save(path/'spec_it.npy',np.arange(8,dtype=np.float32)/10)
    return dict(path=str(path),base_rows=2,added=3,keys=3,error=None)


def test_external_sid_exclusion_preserves_csr_and_candidate_catalog(tmp_path):
    state=make_cache(tmp_path/'source')
    result=MODULE.exclude_sids(state,['raw2'],tmp_path/'filtered')
    assert result['identity_filter_removed']==1 and result['added']==2
    out=Path(result['path'])
    assert pd.read_parquet(out/'spec_meta.parquet').sid.tolist()==[0,1,1,3]
    np.testing.assert_array_equal(np.load(out/'spec_off.npy'),[0,2,3,3,5])
    np.testing.assert_array_equal(np.load(out/'spec_mz.npy'),[0,1,2,6,7])
    assert (out/'train_structs.parquet').read_bytes()==(tmp_path/'source/train_structs.parquet').read_bytes()
    assert len(pd.read_parquet(tmp_path/'source/spec_meta.parquet'))==5


def test_rejects_identity_already_leaking_in_base(tmp_path):
    state=make_cache(tmp_path/'source')
    with pytest.raises(ValueError,match='prefiltered base'):
        MODULE.exclude_sids(state,['raw1'],tmp_path/'filtered')
