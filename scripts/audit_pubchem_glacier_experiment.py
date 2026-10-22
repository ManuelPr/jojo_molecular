"""Replay candidate/forward ranks, protocol masks and cross-fit choices."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from casmi26.forward_ranking import fuse_forward, reciprocal_rank, paired_bootstrap

ROOT = Path(__file__).resolve().parents[1]


def ranks(variant, forward=None, weight=0., gate=.9, forward_top_k=40):
    if not variant['keys']:
        return []
    scores = variant['probabilities']
    if forward is not None:
        seen, permitted = set(), set()
        for i in np.argsort(-np.asarray(scores),kind='stable'):
            if variant['keys'][i] in seen:
                continue
            seen.add(variant['keys'][i]); permitted.add(variant['smiles'][i])
            if len(permitted)==forward_top_k:
                break
        scores = fuse_forward(scores, [forward.get(s) if s in permitted else None for s in variant['smiles']], weight,
                              protected=variant['library_max'] >= gate)
    return list(dict.fromkeys(variant['keys'][i] for i in np.argsort(-np.asarray(scores))[:25]))


def audit(features, forward_root=None):
    features = Path(features)
    manifest = json.loads((features/'feature_manifest.json').read_text())
    plan = json.loads((ROOT/'configs/public_baseline_development.json').read_text())
    if not manifest['complete'] or manifest['cohort_plan_sha256'] != plan['plan_sha256']:
        raise ValueError('Incomplete or changed cohort')
    for name,key in [('experiment_candidates.json','candidates_sha256'),('forward_input.json','forward_input_sha256')]:
        if sha256((features/name).read_bytes()).hexdigest() != manifest[key]:
            raise ValueError('Cache checksum mismatch')
    records = json.loads((features/'experiment_candidates.json').read_text())
    items = json.loads((features/'forward_input.json').read_text())
    expected = sorted(plan['identity_keys'],key=lambda k:sha256(k.encode()).hexdigest())
    expected = expected[:manifest['query_count']]
    if [r['identity'] for r in records] != expected:
        raise ValueError('Wrong development identities/order')
    original = json.loads((ROOT/'artifacts/public_baseline/kaggle_v2/public_validation_report.json').read_text())
    original_rr = {r['identity']:r['reciprocal_rank'] for r in original['per_query']}
    baseline_differences = []
    for record in records:
        for name,variant in record['variants'].items():
            count = len(variant['smiles'])
            if len(variant['keys']) != count or len(variant['probabilities']) != count:
                raise ValueError('Misaligned candidate data')
            if not np.isfinite(np.asarray(variant['probabilities'])).all():
                raise ValueError('Invalid ranker probabilities')
            if name == 'catalog_withheld_baseline' and set(variant['keys']) & set(plan['identity_keys']):
                raise ValueError('Withheld identities leaked into base catalog')
            if 'features' in variant:
                array=np.asarray(variant['features'])
                if array.shape != (count,31) or not np.isfinite(array).all():
                    raise ValueError('Invalid feature cache')
        value=reciprocal_rank(ranks(record['variants']['baseline80']),record['identity'])
        if not np.isclose(value,original_rr[record['identity']],atol=1e-12):
            baseline_differences.append(record['identity'])
    if baseline_differences:
        raise ValueError('Successful-control ranks changed: '+str(baseline_differences))
    before={name:[reciprocal_rank(ranks(r['variants'][name]),r['identity']) for r in records] for name in records[0]['variants']}
    result={'passed':True,'queries':len(records),'baseline_parity_queries':len(records),
            'base_mrr':{name:float(np.mean(values)) for name,values in before.items()},'forward_checked':False}
    if forward_root:
        forward_root=Path(forward_root)
        report=json.loads((forward_root/'experiment_report.json').read_text())
        raw=json.loads((forward_root/'forward_scores.json').read_text())
        if not report['complete'] or report['cache_manifest_sha256'] != sha256((features/'feature_manifest.json').read_bytes()).hexdigest():
            raise ValueError('Forward/cache provenance mismatch')
        mapped={}
        for item in items:
            scores=raw[item['id']]['glacier']
            if len(scores)!=len(item['candidates']) or not np.isfinite(np.asarray(scores,float)).all():
                raise ValueError('Missing supported forward score')
            if not all(-1e-6<=s<=1+1e-6 for s in scores):
                raise ValueError('Invalid entropy similarity range')
            mapped[item['id']]=dict(zip(item['candidates'],scores))
        result.update(forward_checked=True,covered_queries=len(items),variants={})
        folds=[int(sha256(r['identity'].encode()).hexdigest()[:8],16)%5 for r in records]
        for name,stats in report['variants'].items():
            grid={str(w):[reciprocal_rank(ranks(r['variants'][name],mapped.get(r['identity'],{}),w,
                       manifest['configuration']['library_gate'],manifest['configuration']['forward_top_k']),r['identity']) for r in records]
                  for w in report['weights']}
            choices={}
            for fold in sorted(set(folds)):
                train=[i for i,f in enumerate(folds) if f!=fold]
                choices[str(fold)]=max(report['weights'],key=lambda w:(np.mean([grid[str(w)][i] for i in train]),-w))
            if choices!=stats['selected_weight_by_fold']:
                raise ValueError('Forward weight selection used wrong folds')
            oof=[grid[str(choices[str(f)])][i] for i,f in enumerate(folds)]
            if not np.isclose(np.mean(oof),stats['forward_oof_mrr_at_25'],atol=1e-12):
                raise ValueError('Forward MRR replay mismatch')
            result['variants'][name]={'mrr':float(np.mean(before[name])),'forward_oof_mrr':float(np.mean(oof)),
                                     'paired_forward_delta':paired_bootstrap(before[name],oof)}
        result['catalog_withheld_retrieval_gain'] = paired_bootstrap(before['catalog_withheld_baseline'],before['catalog_withheld_pubchem'])
    target=(Path(forward_root) if forward_root else features)/'independent_audit.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--features',type=Path,required=True)
    parser.add_argument('--forward',type=Path)
    args=parser.parse_args()
    print(json.dumps(audit(args.features,args.forward),indent=2))
