"""Component proxy replay; this does not validate the complete v89 treatment."""
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from casmi26.forward_ranking import submission_smiles, reciprocal_rank, paired_bootstrap
from casmi26.selective_pubchem import external_ranked_keys, insert_external, eligible_for_pubchem
from casmi26.pubchem_consensus import promote_consensus


def main():
    root = Path('artifacts/pubchem_glacier')
    features = root / 'features_full_v1'
    mf = json.loads((features / 'feature_manifest.json').read_text())
    for name, field in [('experiment_candidates.json', 'candidates_sha256'), ('forward_input.json', 'forward_input_sha256')]:
        assert sha256((features / name).read_bytes()).hexdigest() == mf[field]
    records = json.loads((features / 'experiment_candidates.json').read_text())
    items = json.loads((features / 'forward_input.json').read_text())
    raw = json.loads((root / 'forward_full_v2/forward_scores.json').read_text())
    fws = {i['id']: dict(zip(i['candidates'], raw[i['id']]['glacier'])) for i in items}
    report = dict(component='Strict forward agreement for the independently ranked external lead', cohorts={},
                  limitation='PG1 component proxy, not v89 end-to-end. PG1 probability gate 0.3 differs from v89 source-confidence gate; pretrained overlap unknown.')
    for cohort, bn, pn in [('known_catalog', 'expanded', 'pubchem'), ('catalog_withheld_proxy', 'catalog_withheld_baseline', 'catalog_withheld_pubchem')]:
        before, after, audits = [], [], []
        for r in records:
            b, p = r['variants'][bn], r['variants'][pn]
            fw = fws.get(r['identity'], {})
            original = submission_smiles(b, fw)
            ext = external_ranked_keys(p)
            mapping = dict(zip(b['smiles'], b['keys'])); mapping.update(zip(p['smiles'], p['keys']))
            active = eligible_for_pubchem(b)
            control = insert_external(original, ext, mapping.get) if active else original
            def allowed(v):
                seen, out = set(), []
                for idx in np.argsort(-np.array(v['probabilities']), kind='stable'):
                    if v['keys'][idx] in seen: continue
                    seen.add(v['keys'][idx]); out.append(v['smiles'][idx])
                    if len(out) == 40: break
                return out
            scores = {}
            for s in set(allowed(b) + allowed(p)):
                if fw.get(s) is not None and np.isfinite(fw[s]):
                    scores[mapping[s]] = max(scores.get(mapping[s], float('-inf')), fw[s])
            old = [mapping[s] for s in control]
            revised, reason = promote_consensus(old, [k for k,s in ext], b['keys'], scores, eligible=active)
            before.append(reciprocal_rank(old, r['identity'])); after.append(reciprocal_rank(revised, r['identity']))
            audits.append(dict(identity=r['identity'], reason=reason, before=before[-1], after=after[-1]))
        report['cohorts'][cohort] = dict(query_count=len(records), before_mrr=float(np.mean(before)), after_mrr=float(np.mean(after)),
            promotions=sum(a['reason'] == 'promoted' for a in audits), delta=paired_bootstrap(before, after), rows=audits)
    report['feature_manifest_sha256'] = sha256((features / 'feature_manifest.json').read_bytes()).hexdigest()
    out = Path('artifacts/pubchem_consensus'); out.mkdir(exist_ok=True)
    (out / 'component_replay.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: {a:b for a,b in v.items() if a != 'rows'} for k,v in report['cohorts'].items()}, indent=2))


if __name__ == '__main__':
    main()
