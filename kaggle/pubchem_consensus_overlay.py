"""Append-only treatment after the frozen v89 output; reuse completed simulators."""


def _apply_pubchem_consensus(scope):
    import json
    import hashlib
    import math
    from pathlib import Path
    import pandas as pd

    original_bytes = Path('submission.csv').read_bytes()
    Path('submission_v89_control.csv').write_bytes(original_bytes)
    frame = pd.read_csv('submission.csv', dtype=str, keep_default_na=False)
    # Upstream metric_identity returns (InChIKey14, heavy-atom tuple), which is
    # hashable in Python but cannot be a JSON object key. Use its canonical
    # InChIKey14 component, also used by the independent chemical auditor.
    identity = scope['canonicalize_smiles_to_ik14']
    results, audits, evidence = [], [], []
    snapshot = scope['CONSENSUS_BEFORE_FORWARD']
    for row in frame.itertuples(index=False):
        mid = str(row.molecule_id)
        original = row.smiles.split(';')
        record = snapshot.get(mid, {})
        pc_smiles = record.get('pc_smiles', [])
        base_smiles = record.get('base_smiles', [])
        original_keys = list(map(identity, original))
        external_keys = list(map(identity, pc_smiles))
        base_keys = list(map(identity, base_smiles))
        representatives = dict(zip(original_keys, original))
        for key, smile in zip(external_keys, pc_smiles):
            representatives.setdefault(key, smile)
        eligible = record.get('eligible', False)
        # Select the same preferred simulator as the inherited E006 policy.
        # Do not choose the simulator retrospectively by its preferred candidate.
        gl = scope['gl_of'](mid)
        raw = gl if gl else scope['ICE_SCORES'].get(mid, {})
        scores = {}
        for smile in base_smiles + pc_smiles:
            key = identity(smile)
            value = raw.get(smile)
            if value is None:
                value = raw.get(scope['chem'].score_key(smile))
            if value is not None and math.isfinite(float(value)):
                # Multiple metric-equivalent representations contribute one vote.
                scores[key] = max(scores.get(key, float('-inf')), float(value))
        revised, reason = scope['promote_consensus'](
            original_keys, external_keys, base_keys, scores, eligible=eligible)
        evidence.append(dict(molecule_id=mid, original=original_keys,
                             external=external_keys, base=base_keys,
                             scores=scores, eligible=eligible, revised=revised))
        output = [representatives[k] for k in revised]
        assert 1 <= len(output) <= 25 and len(revised) == len(set(revised))
        if not eligible:
            assert output == original
        results.append((mid, ';'.join(output)))
        audits.append(dict(molecule_id=mid, eligible=eligible, reason=reason,
                           simulator='glacier' if gl else 'iceberg',
                           changed=revised != original_keys,
                           changed_top1=revised[:1] != original_keys[:1],
                           forward_identities=len(scores)))
    result = pd.DataFrame(results, columns=['molecule_id', 'smiles'])
    assert list(result.molecule_id) == list(frame.molecule_id)
    result.to_csv('submission.csv', index=False)
    report = dict(policy='pubchem_source_and_forward_consensus_v1',
                  output_rows=len(result), eligible=sum(a['eligible'] for a in audits),
                  changed_rows=sum(a['changed'] for a in audits),
                  changed_top1=sum(a['changed_top1'] for a in audits),
                  control_sha256=hashlib.sha256(original_bytes).hexdigest(),
                  submission_sha256=hashlib.sha256(Path('submission.csv').read_bytes()).hexdigest(),
                  measured_public_score=None, rows=audits)
    Path('pubchem_consensus_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    Path('pubchem_consensus_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    pd.DataFrame(audits).to_csv('pubchem_consensus_audit.csv', index=False)
    print('PUBCHEM_CONSENSUS', json.dumps({k: v for k, v in report.items() if k != 'rows'}))


_apply_pubchem_consensus(globals())
del _apply_pubchem_consensus
