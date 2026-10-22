"""Identity-grouped OOF calibration of the external-candidate/forward channel.

Not a library-holdout benchmark: positive identities' references are hidden.
The native ranking is preserved behind the existing library-confidence gate.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from casmi26.forward_ranking import paired_bootstrap, reciprocal_rank

FEATURE_NAMES = [f'public_feature_{i}' for i in range(31)] + [
    'native_probability', 'native_log_odds', 'mass_error_ppm', 'abs_mass_error_ppm',
    'external_candidate', 'glacier_entropy', 'glacier_missing', 'glacier_z']
CONFIG = dict(max_depth=4,max_iter=150,learning_rate=.05,min_samples_leaf=20,
              l2_regularization=1.,early_stopping=False)


def selected_smiles(variant, limit):
    seen, selected=set(),set()
    for i in np.argsort(-np.asarray(variant['probabilities']),kind='stable'):
        if variant['keys'][i] in seen:
            continue
        seen.add(variant['keys'][i]);selected.add(variant['smiles'][i])
        if len(selected)==limit:
            break
    return selected


def features(variant, forward, limit):
    if not variant['keys']:
        return np.empty((0,len(FEATURE_NAMES)),np.float32)
    matrix=np.asarray(variant['features'],np.float32)
    allowed=selected_smiles(variant,limit)
    gl=np.array([forward.get(s,np.nan) if s in allowed else np.nan for s in variant['smiles']],float)
    valid=np.isfinite(gl)
    standardized=np.zeros(len(gl))
    if valid.sum()>1 and gl[valid].std()>1e-12:
        standardized[valid]=(gl[valid]-gl[valid].mean())/gl[valid].std()
    p=np.clip(np.array(variant['probabilities']),1e-6,1-1e-6)
    ppm=np.asarray(variant['mass_error_ppm'])
    result=np.column_stack([matrix,p,np.log(p/(1-p)),ppm,np.abs(ppm),variant['external_flags'],
                           np.where(valid,gl,0.),~valid,standardized]).astype(np.float32)
    if result.shape!=(len(p),len(FEATURE_NAMES)) or not np.isfinite(result).all():
        raise ValueError('Learned ranker input contract failed')
    return result


def training_mask(rows_query, rows_candidate, held_queries):
    """Exclude held query identities and their candidate identities from fitting."""
    return ~np.isin(rows_query,list(held_queries)) & ~np.isin(rows_candidate,list(held_queries))


def ranked_rr(variant,scores,truth):
    order=np.argsort(-scores)[:25]
    keys=list(dict.fromkeys(variant['keys'][i] for i in order))
    return reciprocal_rank(keys,truth)


def fit(features_root,forward_root,output):
    features_root,forward_root,output=map(Path,[features_root,forward_root,output])
    manifest=json.loads((features_root/'feature_manifest.json').read_text())
    report=json.loads((forward_root/'experiment_report.json').read_text())
    if report['cache_manifest_sha256']!=sha256((features_root/'feature_manifest.json').read_bytes()).hexdigest():
        raise ValueError('Different cache/forward results')
    if not manifest['complete'] or not report['complete'] or not report['forward_executed']:
        raise ValueError('Calibration requires completed feature and forward jobs')
    for filename,key in [('experiment_candidates.json','candidates_sha256'),('forward_input.json','forward_input_sha256')]:
        if sha256((features_root/filename).read_bytes()).hexdigest()!=manifest[key]:
            raise ValueError('Calibration cache checksum mismatch: '+filename)
    records=json.loads((features_root/'experiment_candidates.json').read_text())
    items=json.loads((features_root/'forward_input.json').read_text())
    raw=json.loads((forward_root/'forward_scores.json').read_text())
    forward={i['id']:dict(zip(i['candidates'],raw[i['id']]['glacier'])) for i in items}
    names=['pubchem','catalog_withheld_pubchem']
    prepared={}
    blocks,labels,weights,query_keys,candidate_keys=[],[],[],[],[]
    for record in records:
        for name in names:
            variant=record['variants'][name]
            x=features(variant,forward.get(record['identity'],{}),manifest['configuration']['forward_top_k'])
            prepared[(record['identity'],name)]=x
            y=np.array([k==record['identity'] for k in variant['keys']],dtype=int)
            if not y.sum():
                continue  # fit conditional ranking; evaluation keeps misses as zero
            positives,negatives=int(y.sum()),len(y)-int(y.sum())
            if not negatives:
                continue
            w=np.where(y,1./positives,1./negatives)/len(names)
            blocks.append(x);labels.append(y);weights.append(w)
            query_keys.extend([record['identity']]*len(y));candidate_keys.extend(variant['keys'])
    x,y,w=np.concatenate(blocks),np.concatenate(labels),np.concatenate(weights)
    q,c=np.array(query_keys,dtype=object),np.array(candidate_keys,dtype=object)
    folds={r['identity']:int(sha256(r['identity'].encode()).hexdigest()[:8],16)%5 for r in records}
    per_query={};without_forward={};fold_audits=[]
    for fold in range(5):
        held={k for k,f in folds.items() if f==fold}
        if not held:
            continue
        keep=training_mask(q,c,held)
        if len(set(q[keep])&held) or len(set(c[keep])&held):
            raise ValueError('Identity leakage in calibration fitting')
        model=HistGradientBoostingClassifier(random_state=26+fold,**CONFIG)
        model.fit(x[keep],y[keep],sample_weight=w[keep])
        # Same folds, labels, weights and hyperparameters isolate the contribution
        # of GLACIER from the benefit of supervised calibration itself.
        model_without=HistGradientBoostingClassifier(random_state=26+fold,**CONFIG)
        model_without.fit(x[keep,:-3],y[keep],sample_weight=w[keep])
        fold_audits.append({'fold':fold,'held_queries':len(held),'training_queries':len(set(q[keep])),
                            'training_rows':int(keep.sum()),'positive_rows':int(y[keep].sum())})
        for record in records:
            identity=record['identity']
            if identity not in held:
                continue
            for name in names:
                variant=record['variants'][name];matrix=prepared[(identity,name)]
                if not len(matrix):
                    value=value_without=0.
                else:
                    probability=model.predict_proba(matrix)[:,1]
                    probability_without=model_without.predict_proba(matrix[:,:-3])[:,1]
                    if variant['library_max']>=manifest['configuration']['library_gate']:
                        probability=np.array(variant['probabilities'])
                        probability_without=probability
                    value=ranked_rr(variant,probability,identity)
                    value_without=ranked_rr(variant,probability_without,identity)
                per_query[(identity,name)]=value
                without_forward[(identity,name)]=value_without
        print('fold',fold,'done',fold_audits[-1],flush=True)
    summary={'configuration':CONFIG,'feature_names':FEATURE_NAMES,'fold_audits':fold_audits,'variants':{},
             'query_count':len(records),'cohort_plan_sha256':manifest['cohort_plan_sha256'],
             'feature_manifest_sha256':report['cache_manifest_sha256'],
             'forward_report_sha256':sha256((forward_root/'experiment_report.json').read_bytes()).hexdigest(),
             'forward_scores_sha256':sha256((forward_root/'forward_scores.json').read_bytes()).hexdigest(),
             'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
             'runtime_versions':{'numpy':np.__version__,'scikit_learn':sklearn.__version__},
             'limitations':['Supervised calibration evaluated only on own-reference-hidden development; library-holdout still required',
                            'Unknown supervised/pretrained identity overlap in original fingerprint/31-feature ranker assets',
                            'No hidden score or new official submission measured'],'per_query':[]}
    for name in names:
        after=[per_query[(r['identity'],name)] for r in records]
        calibrated_without=[without_forward[(r['identity'],name)] for r in records]
        native=[ranked_rr(r['variants'][name],np.array(r['variants'][name]['probabilities']),r['identity']) for r in records]
        weighted=[r['metrics'][name]['forward_oof_rr'] for r in report['per_query']]
        summary['variants'][name]={'learned_oof_mrr':float(np.mean(after)),'native_mrr':float(np.mean(native)),
                                 'learned_without_forward_oof_mrr':float(np.mean(calibrated_without)),
                                 'paired_glacier_contribution':paired_bootstrap(calibrated_without,after),
                                 'weighted_forward_oof_mrr':float(np.mean(weighted)),
                                 'delta_vs_native':paired_bootstrap(native,after),'delta_vs_weighted_forward':paired_bootstrap(weighted,after)}
        if name=='pubchem':
            expanded=[ranked_rr(r['variants']['expanded'],np.array(r['variants']['expanded']['probabilities']),r['identity']) for r in records]
            summary['variants'][name]['delta_vs_expanded_base']=paired_bootstrap(expanded,after)
        summary['per_query'].extend({'identity':r['identity'],'variant':name,'fold':folds[r['identity']],
                                    'reciprocal_rank':after[i],
                                    'without_forward_reciprocal_rank':calibrated_without[i]} for i,r in enumerate(records))
    output.mkdir(parents=True,exist_ok=True)
    (output/'learned_ranker_report.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary['variants'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--features',required=True);parser.add_argument('--forward',required=True);parser.add_argument('--output',required=True)
    a=parser.parse_args();fit(a.features,a.forward,a.output)
