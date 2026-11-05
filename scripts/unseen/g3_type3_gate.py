"""G3: type-3 gate. Decide per query whether to take the genfix list (base Engine-1 list + inserted wide-generation
structures) instead of the base list, from features of the BASE run only (no truth, no genfix output).

Protocol fixed before any score (2026-11-05):
  features  library_max, final-score gap rank1-rank2, sanpier neural z-score of the leader and its neural rank, max
            neural_cos / neural_fp in the list, generated fraction of the final top 10 and of the leader (generated =
            key absent from that query's pool / pubchem / engine2 stages), pool size, pubchem candidates in the final list.
  model     standardised logistic regression (C=1), trained on K6 clean cal half only: y = type 3 vs type 2 (same
            instruments, so the gate cannot learn "timsTOF => type 1").
  gate      fires when p(type3) > threshold; thresholds = quantiles giving fire rates 5% / 10% / 20% on T1-thin cal.
  choice    threshold maximising 0.35*T1thin + 0.30*K6t2 + 0.35*K6t3 delta on the cal halves; one verification on ver,
            plus T1 and K7 (type 3 NP) as transfer checks. Reference = ungated genfix and base.
Usage: CASMI_ROOT=<main checkout> g3_type3_gate.py -> artifacts/G3/gate_v1.json
"""
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(os.environ.get('CASMI_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_docprior_layer import compare  # noqa: E402
from eval_ensemble_480 import half  # noqa: E402
from eval_smiles_level import metric_keys  # noqa: E402

FEATS = ['library_max', 'score_gap', 'leader_z', 'leader_nrank', 'max_cos', 'max_fp', 'gen_frac10', 'leader_gen', 'n_pool',
         'n_pubchem_final']
BENCH = {'K6': ('r2_k6_s?', 'r_k6gfx_s?'), 'K7': ('r_k7v2_s?', 'r_k7v2gfx_s?'), 'T1': ('r_t1_np250', 'r_t1gfx_np250'),
         'T1thin': ('r_t1thin_base', 'r_t1thin_gfx')}
FIRE = [0.05, 0.10, 0.20]
MIX = {'T1thin': 0.35, 'K6t2': 0.30, 'K6t3': 0.35}


def runs(pattern):
    return [r for r in sorted(glob.glob(str(ROOT/'artifacts/k2_replay'/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]


def lists_of(pattern):
    out = {}
    for r in runs(pattern):
        c = pd.read_parquet(Path(r)/'k2_export/candidates.parquet', columns=['query_id', 'arm', 'stage', 'rank', 'smiles'])
        f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
        out.update(f.groupby('query_id').smiles.apply(list).to_dict())
    return out


def features(pattern):
    rows = []
    for r in runs(pattern):
        c = pd.read_parquet(Path(r)/'k2_export/candidates.parquet')
        n = pd.read_parquet(Path(r)/'k2_export/neural_sanpier.parquet')
        for q, g in c.groupby('query_id', sort=False):
            fin = g[(g.arm == 'sanpier') & (g.stage == 'final_c477')].sort_values('rank')
            if fin.empty:
                continue
            cat = set(g[g.stage.isin(['pool', 'pubchem', 'engine2'])].candidate_key)
            pub = set(g[g.stage == 'pubchem'].candidate_key)
            nq = n[n.molecule_id == q]
            z = (nq.neural_score - nq.neural_score.mean()) / max(nq.neural_score.std(ddof=0), 1e-6)
            nz = dict(zip(nq.smiles, z))
            nrank = dict(zip(nq.smiles, nq.neural_score.rank(ascending=False, method='first')))
            lead = fin.iloc[0]
            sc = fin.score.to_numpy(float)
            rows.append(dict(query_id=q, library_max=float(nq.library_max.max()) if len(nq) else 0.0,
                             score_gap=float(sc[0] - sc[1]) if len(sc) > 1 else 0.0,
                             leader_z=float(nz.get(lead.smiles, 0.0)), leader_nrank=float(nrank.get(lead.smiles, 25)),
                             max_cos=float(nq.neural_cos.max()) if len(nq) else 0.0,
                             max_fp=float(nq.neural_fp.max()) if len(nq) else 0.0,
                             gen_frac10=float(np.mean([k not in cat for k in fin.candidate_key.head(10)])),
                             leader_gen=float(lead.candidate_key not in cat),
                             n_pool=float((g.stage == 'pool').sum()),
                             n_pubchem_final=float(sum(k in pub for k in fin.candidate_key))))
    return pd.DataFrame(rows).set_index('query_id').fillna(0.0)


def main():
    t1 = pd.read_parquet(ROOT/'artifacts/K6/type1_np250_v1/molecules.parquet').set_index('molecule_id')
    train = pd.read_parquet(ROOT/'data/fastweb/competition/train.parquet', columns=['inchikey14', 'normalized_smiles'])
    t1_smiles = t1.inchikey14.map(train.drop_duplicates('inchikey14').set_index('inchikey14').normalized_smiles)
    k6 = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules_metric.parquet').set_index('molecule_id')
    k6 = k6[~k6.in_train_metric & (k6.truth_metric.fillna('') != '')]
    k7_truth = {}
    for r in glob.glob(str(ROOT/'artifacts/k2_replay/r_k7v2_s?')):
        info = json.loads(Path(r, 'k2_run_info.json').read_text())
        k7_truth.update(json.loads(Path(info['contract']).read_text())['truth'])

    base = {b: lists_of(p[0]) for b, p in BENCH.items()}
    gfx = {b: lists_of(p[1]) for b, p in BENCH.items()}
    feat = {b: features(p[0]) for b, p in BENCH.items()}
    mk = metric_keys(list(t1_smiles.dropna()) + [s for d in (base, gfx) for L in d.values() for x in L.values() for s in x])
    t1_truth = {q: mk.get(s) for q, s in t1_smiles.items()}
    truths = {'K6': k6.truth_metric.to_dict(), 'K7': k7_truth, 'T1': t1_truth, 'T1thin': t1_truth}
    groups = {'K6t2': ('K6', list(k6.index[k6.type_metric == 2])), 'K6t3': ('K6', list(k6.index[k6.type_metric == 3])),
              'K7': ('K7', list(k7_truth)), 'T1': ('T1', list(t1.index)), 'T1thin': ('T1thin', list(t1.index))}

    kq = [q for q in k6.index if q in feat['K6'].index]
    cal = [q for q in kq if half(q) == 'cal']
    X, y = feat['K6'].loc[cal, FEATS], (k6.loc[cal, 'type_metric'] == 3).astype(int)
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)).fit(X, y)
    coef = dict(zip(FEATS, model[-1].coef_[0].round(3)))
    p = {b: pd.Series(model.predict_proba(f[FEATS])[:, 1], index=f.index) for b, f in feat.items()}
    thin_cal = p['T1thin'][[q for q in p['T1thin'].index if half(q) == 'cal']]
    thresholds = {f: float(thin_cal.quantile(1 - f)) for f in FIRE}

    def gated(b, thr):
        return {q: (gfx[b][q] if (q in gfx[b] and p[b].get(q, 0.0) > thr) else L) for q, L in base[b].items()}

    def evaluate(variant_lists, split):
        res = {}
        for g, (b, qs) in groups.items():
            sel = [q for q in qs if q in base[b] and (split == 'all' or half(q) == split)]
            res[g] = compare(base[b], variant_lists[b], truths[b], mk, sel)
            res[g]['fire_rate'] = float(np.mean([p[b].get(q, 0.0) > (variant_lists.get('_thr', -1)) for q in sel])) if sel else 0.0
        return res

    rep = {'coef': coef, 'thresholds_by_t1thin_cal_fire': thresholds,
           'model': dict(features=FEATS, mean=model[0].mean_.tolist(), scale=model[0].scale_.tolist(),
                         coef=model[-1].coef_[0].tolist(), intercept=float(model[-1].intercept_[0])),
           'auc_k6_cal': float(__import__('sklearn.metrics', fromlist=['roc_auc_score']).roc_auc_score(y, model.predict_proba(X)[:, 1]))}
    ver = [q for q in kq if half(q) == 'ver']
    from sklearn.metrics import roc_auc_score
    rep['auc_k6_ver'] = float(roc_auc_score((k6.loc[ver, 'type_metric'] == 3).astype(int), p['K6'][ver]))
    variants = {'ungated': {b: gfx[b] for b in BENCH}}
    for f, thr in thresholds.items():
        v = {b: gated(b, thr) for b in BENCH}
        v['_thr'] = thr
        variants[f'fire{int(f*100)}'] = v
    variants['ungated']['_thr'] = -1.0
    calres = {k: evaluate(v, 'cal') for k, v in variants.items()}
    obj = {k: sum(MIX[g]*calres[k][g]['delta'] for g in MIX) for k in variants}
    sel = max((k for k in variants if k != 'ungated'), key=obj.get)
    rep.update(cal_objective=obj, selected=sel, cal=calres)
    rep['ver'] = {k: evaluate(variants[k], 'ver') for k in (sel, 'ungated')}
    rep['all'] = {k: evaluate(v, 'all') for k, v in variants.items()}
    print(json.dumps({k: rep[k] for k in ('coef', 'auc_k6_cal', 'auc_k6_ver', 'thresholds_by_t1thin_cal_fire', 'cal_objective', 'selected')}, indent=1, default=float))
    for k, r in rep['ver'].items():
        for g, v in r.items():
            print('ver', k, g, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items()}, flush=True)
    Path(ROOT/'artifacts/G3').mkdir(exist_ok=True)
    (ROOT/'artifacts/G3/gate_v1.json').write_text(json.dumps(rep, indent=1, default=float))


if __name__ == '__main__':
    main()
