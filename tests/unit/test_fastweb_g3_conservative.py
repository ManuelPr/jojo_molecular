"""Safety contract for the experimental top1-preserving submission."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def test_conservative_submission_preserves_f0_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = pd.DataFrame({'molecule_id': ['q1', 'q2'], 'smiles': ['A;B;C;D', 'CCO']})
    def unrestricted(scope, directory):
        original.to_csv('submission_f0_control.csv', index=False)
        pd.DataFrame({'query_identity': ['q1']*3,
                      'candidate_scorer_identity': ['A', 'B', 'C'],
                      'g3_score': [-10., 1., 5.]}).to_parquet('g3_candidate_scores.parquet', index=False)
        return {'main_errors': 0}
    namespace = {'_g3_run': unrestricted}
    exec((ROOT/'kaggle/g3_conservative_overlay.py').read_text(), namespace)
    receipt = namespace['_g3_run']({'metric_identity': lambda s: (s,)}, tmp_path)
    result = pd.read_csv('submission.csv', dtype=str)
    assert result.smiles.tolist() == ['A;C;B;D', 'CCO']
    assert receipt['top1_changes'] == receipt['candidate_set_changes'] == 0
    assert receipt['changed_rows'] == 1
    assert receipt['submission_sha256'] == hashlib.sha256(Path('submission.csv').read_bytes()).hexdigest()
    assert json.loads(Path('g3_submission_receipt.json').read_text()) == receipt
