"""Read-only acceptance audit appended after all 35 public v89 source cells."""


def _observe_reproduction(scope):
    import hashlib
    import json
    import time
    from pathlib import Path
    import pandas as pd

    report = scope['E004_REPORT']
    assert report['is_full_run'] and report['placeholder_fill_rows'] == 0
    assert report['processed_molecules'] == report['input_molecules']
    assert report['base_errors'] == 0
    stages = report['stages']
    for name, stage in stages.items():
        assert stage['status'] == 'ok', (name, stage)
        assert stage['device'].startswith('cuda'), (name, stage)
        assert stage['rdkit'] == '2025.03.6', (name, stage)
        assert not stage.get('errors') and not stage.get('n_pred_fail', 0)
        assert not stage.get('n_feat_fail', 0)
        assert stage['n_mols_scored'] == stage['n_mols_covered'], (name, stage)
        if stage['n_mols_covered']:
            assert stage['n_scored'] > 0
    frame = pd.read_csv('submission.csv', dtype=str, keep_default_na=False)
    assert list(frame.columns) == ['molecule_id', 'smiles']
    assert frame.molecule_id.is_unique
    assert set(frame.molecule_id) == set(report['input_ids'])
    for row in frame.itertuples(index=False):
        keys = [scope['metric_identity'](s) for s in row.smiles.split(';')]
        assert 1 <= len(keys) <= 25 and None not in keys and len(keys) == len(set(keys)), row.molecule_id
    files = ['submission.csv', 'submission_e006_control.csv', 'submission_e004_control.csv',
             'e004_candidate_inputs.json', 'e004_verification.json', 'experiment_verification.json',
             'retrieval_experiment_audit.json', 'retrieval_experiment_audit.csv']
    result = dict(complete=True, source_version=89, source_script_version_id=357683876,
                  input_count=report['input_molecules'], processed_count=report['processed_molecules'],
                  output_count=len(frame), main_rdkit=report['main_rdkit'], stages=stages,
                  elapsed_seconds=round(time.time() - scope['T0'], 2),
                  hashes={f: hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in files},
                  retrieval=json.loads(Path('retrieval_experiment_audit.json').read_text()),
                  measured_public_score=None,
                  limitations=['Visible test is a placeholder; this is a runtime and artifact audit, not accuracy validation.'])
    Path('reproduction_complete.json').write_text(json.dumps(result, indent=2) + '\n')
    print('REPRODUCTION_COMPLETE', json.dumps(result))


_observe_reproduction(globals())
del _observe_reproduction
