"""Independently check a downloaded full-run reproduction artifact."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

from audit_expanded_glacier_submission import chemical_keys

ROOT = Path(__file__).resolve().parents[1]


def audit(output):
    output = Path(output)
    report = json.loads((output / 'reproduction_complete.json').read_text())
    assert report['complete'] and report['source_script_version_id'] == 357683876
    for name, digest in report['hashes'].items():
        assert sha256((output / name).read_bytes()).hexdigest() == digest, name
    with (ROOT / 'data/sample_submission.csv').open(newline='') as f:
        expected = [r['molecule_id'] for r in csv.DictReader(f)]
    with (output / 'submission.csv').open(newline='') as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ['molecule_id', 'smiles']
        rows = list(reader)
    assert len(expected) == len(set(expected)) == 400
    assert [r['molecule_id'] for r in rows] == expected
    assert report['input_count'] == report['processed_count'] == report['output_count'] == 400
    keys = chemical_keys([s for r in rows for s in r['smiles'].split(';')])
    counts = []
    for row in rows:
        identities = [keys[s] for s in row['smiles'].split(';')]
        assert 1 <= len(identities) <= 25 and None not in identities
        assert len(identities) == len(set(identities)), row['molecule_id']
        counts.append(len(identities))
    assert report['main_rdkit'] == '2026.03.3'
    assert set(report['stages']) == {'ice', 'gl'}
    for name, stage in report['stages'].items():
        assert stage['status'] == 'ok' and stage['device'].startswith('cuda'), name
        assert stage['rdkit'] == '2025.03.6', name
        assert not stage.get('errors') and not stage.get('n_pred_fail', 0) and not stage.get('n_feat_fail', 0), name
        assert stage['n_mols_scored'] == stage['n_mols_covered'], name
    assert 0 < report['elapsed_seconds'] < 32400
    pre = json.loads((output / 'e004_verification.json').read_text())
    assert pre['base_errors'] == pre['placeholder_fill_rows'] == 0
    assert pre['base_nonempty'] == pre['engine2_nonempty'] == 400
    assert report['retrieval']['mode'] == 'dual'
    result = dict(passed=True, molecules=400, unique_smiles_checked=len(keys),
                  min_candidates=min(counts), max_candidates=max(counts),
                  elapsed_seconds=report['elapsed_seconds'],
                  submission_sha256=report['hashes']['submission.csv'],
                  simulator_molecules={k: v['n_mols_scored'] for k, v in report['stages'].items()},
                  retrieval=report['retrieval'],
                  limitation='Visible-placeholder audit only; no hidden accuracy measurement.')
    (output / 'independent_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('output', type=Path)
    print(json.dumps(audit(parser.parse_args().output), indent=2))
