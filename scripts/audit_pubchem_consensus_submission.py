"""Audit the same-run v89 control and the appended consensus treatment."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile

from audit_flexon_v89_reproduction import audit as audit_control
from audit_expanded_glacier_submission import chemical_keys
from casmi26.pubchem_consensus import promote_consensus


def audit(output):
    output = Path(output)
    baseline = json.loads((output / 'reproduction_complete.json').read_text())
    with tempfile.TemporaryDirectory(prefix='casmi_consensus_audit_') as directory:
        view = Path(directory)
        shutil.copyfile(output / 'reproduction_complete.json', view / 'reproduction_complete.json')
        for name in baseline['hashes']:
            source = 'submission_v89_control.csv' if name == 'submission.csv' else name
            shutil.copyfile(output / source, view / name)
        control = audit_control(view)
    report = json.loads((output / 'pubchem_consensus_audit.json').read_text())
    evidence = json.loads((output / 'pubchem_consensus_evidence.json').read_text())
    assert report['control_sha256'] == baseline['hashes']['submission.csv']
    assert sha256((output / 'submission.csv').read_bytes()).hexdigest() == report['submission_sha256']
    def read(name):
        with (output / name).open(newline='') as f:
            r = csv.DictReader(f); assert r.fieldnames == ['molecule_id', 'smiles']
            return list(r)
    before, after = read('submission_v89_control.csv'), read('submission.csv')
    assert [r['molecule_id'] for r in before] == [r['molecule_id'] for r in after]
    assert len(after) == report['output_rows'] == len(evidence) == 400
    mapping = chemical_keys([s for r in before + after for s in r['smiles'].split(';')])
    by_id = {r['molecule_id']: r for r in evidence}
    assert len(by_id) == 400
    changes = 0
    for a, b in zip(before, after):
        old = [mapping[s] for s in a['smiles'].split(';')]
        new = [mapping[s] for s in b['smiles'].split(';')]
        assert None not in new and 1 <= len(new) <= 25 and len(new) == len(set(new))
        e = by_id[a['molecule_id']]
        assert e['original'] == old
        expected, reason = promote_consensus(old, e['external'], e['base'], e['scores'], eligible=e['eligible'])
        assert expected == new == e['revised']
        if not e['eligible']:
            assert a['smiles'] == b['smiles']
        changes += new != old
    assert changes == report['changed_rows']
    result = dict(passed=True, control_audit=control, output_rows=400,
                  replay_rows=400, changed_rows=changes, eligible=report['eligible'],
                  submission_sha256=report['submission_sha256'],
                  limitation='Visible-placeholder audit; component proxy does not establish full-v89 accuracy.')
    (output / 'independent_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('output', type=Path)
    print(json.dumps(audit(p.parse_args().output), indent=2))
