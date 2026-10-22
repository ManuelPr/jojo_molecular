"""Exercise the real overlay through CSV and JSON, including upstream tuple IDs."""
import json
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import pytest
from casmi26.chemistry import canonical_inchikey14
from casmi26.pubchem_consensus import promote_consensus

SOURCE = Path(__file__).resolve().parents[2] / 'kaggle/pubchem_consensus_overlay.py'


@pytest.mark.parametrize('eligible', [False, True])
def test_complete_overlay_serializes_real_chemical_identities(tmp_path, monkeypatch, eligible):
    monkeypatch.chdir(tmp_path)
    original = ['CCO', 'CCC', 'CCN', 'CCCC']
    pd.DataFrame([('m_test', ';'.join(original))], columns=['molecule_id', 'smiles']).to_csv('submission.csv', index=False)
    scope = dict(
        metric_identity=lambda s: (canonical_inchikey14(s), (('C', 2),)),
        canonicalize_smiles_to_ik14=canonical_inchikey14,
        CONSENSUS_BEFORE_FORWARD={'m_test': dict(pc_smiles=['CCN', 'CCCC'], base_smiles=['CCO', 'CCC'], eligible=eligible)},
        gl_of=lambda mid: {'CCO': .2, 'CCC': .3, 'CCN': .9, 'CCCC': .4},
        ICE_SCORES={}, chem=SimpleNamespace(score_key=canonical_inchikey14),
        promote_consensus=promote_consensus,
    )
    exec(compile(SOURCE.read_text(), str(SOURCE), 'exec'), scope)
    evidence = json.loads(Path('pubchem_consensus_evidence.json').read_text())
    report = json.loads(Path('pubchem_consensus_audit.json').read_text())
    assert all(isinstance(k, str) and len(k) == 14 for k in evidence[0]['scores'])
    assert evidence[0]['original'] == list(map(canonical_inchikey14, original))
    actual = pd.read_csv('submission.csv').iloc[0].smiles.split(';')
    assert actual == (['CCN', 'CCO', 'CCC', 'CCCC'] if eligible else original)
    assert report['changed_rows'] == int(eligible)
    assert pd.read_csv('submission_v89_control.csv').iloc[0].smiles == ';'.join(original)
