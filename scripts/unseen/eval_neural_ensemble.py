"""K10: neural z-ensemble on ranks 2-25 (rank 1 fixed), emulated on the replays. The public 0.480 line gained by averaging
z(public scorer) with a second scorer (replacing it always lost: 0.454-0.463 for our JM scorers). Tail order is
re-derived with the variant-M CUSTOM formula 1/(3+baseline_rank) + 0.75/(3+neural_rank) from the base run's
neural_sanpier features; 'control' uses the sanpier score alone (measures how well the emulation reproduces final_c477),
the variants z-average sanpier with one or more of our JM scorers (exported for the same candidates).
Selection on the cal half (sha256(query_id) even) of K6 type 2 + T1-thin, one verification on ver. Exposure: the JM
models were trained on train, which holds the T1 truths, so T1/T1-thin are exposed; K6/K7 truths are not in train.

Usage: eval_neural_ensemble.py  -> artifacts/K10/neural_ensemble_v1.json   (run with CASMI_ROOT=<main checkout>)
"""
import glob
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get('CASMI_ROOT', Path(__file__).resolve().parents[2]))  # main checkout holds data/artifacts
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from eval_docprior_layer import compare  # noqa: E402
from eval_smiles_level import metric_keys  # noqa: E402

JM = ['jm_base_full', 'jm_ens_s1s2b', 'jm_base', 'jm_b0', 'jm_small_b1']
VARIANTS = {'control': ['sanpier'], **{f'ens_{m}': ['sanpier', m] for m in JM},
            'ens_full_ens': ['sanpier', 'jm_base_full', 'jm_ens_s1s2b']}


def load(pattern):
    runs = [r for r in sorted(glob.glob(str(ROOT/'artifacts/k2_replay'/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]
    lists, scores = {}, []
    for r in runs:
        c = pd.read_parquet(Path(r)/'k2_export/candidates.parquet')
        f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
        lists.update(f.groupby('query_id').smiles.apply(list).to_dict())
        base = pd.read_parquet(Path(r)/'k2_export/neural_sanpier.parquet')[['molecule_id', 'smiles', 'baseline_rank', 'neural_score']]
        base = base.rename(columns={'neural_score': 'sanpier'})
        for m in JM:
            s = pd.read_parquet(Path(r)/f'k2_export/neural_{m}.parquet')[['molecule_id', 'smiles', 'neural_score']]
            base = base.merge(s.rename(columns={'neural_score': m}), on=['molecule_id', 'smiles'], how='left')
        scores.append(base)
    return lists, pd.concat(scores)


def zscore(s):
    g = s.groupby(level=0)
    return (s - g.transform('mean')) / g.transform(lambda x: x.std(ddof=0)).clip(lower=1e-6)


def rerank(lists, sc, members):
    sc = sc.set_index(['molecule_id', 'smiles'])
    ens = sum(zscore(sc[m].astype(float).fillna(sc[m].min())) for m in members) / len(members)
    out = {}
    for mid, g in ens.groupby(level=0):
        if mid not in lists:
            continue
        L = lists[mid]
        nr = g.droplevel(0).rank(ascending=False, method='first')
        br = sc.loc[mid, 'baseline_rank']
        def key(s):
            if s in nr.index:
                return 1/(3+float(br[s])) + 0.75/(3+float(nr[s]))
            return 1/(3+L.index(s)+1)
        out[mid] = [L[0]] + sorted(L[1:], key=key, reverse=True)
    for mid in lists:
        out.setdefault(mid, lists[mid])
    return out


def half(q):
    return 'cal' if int(hashlib.sha256(str(q).encode()).hexdigest(), 16) % 2 == 0 else 'ver'


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
    benches = {'T1thin': 'r_t1thin_base', 'T1': 'r_t1_np250', 'K6': 'r2_k6_s?', 'K7': 'r_k7v2_s?'}
    data = {b: load(p) for b, p in benches.items()}
    mk = metric_keys(list(t1_smiles.dropna()) + [s for L, _ in data.values() for x in L.values() for s in x])
    t1_truth = {q: mk.get(s) for q, s in t1_smiles.items()}
    truths = {'T1thin': t1_truth, 'T1': t1_truth, 'K6': k6.truth_metric.to_dict(), 'K7': k7_truth}
    groups = {'T1thin': {'type1': list(t1.index)}, 'T1': {'type1': list(t1.index)},
              'K6': {f'type{t}': list(k6.index[k6.type_metric == t]) for t in (2, 3)}, 'K7': {'type3_np': list(k7_truth)}}
    out = {b: {v: rerank(L, sc, m) for v, m in VARIANTS.items()} for b, (L, sc) in data.items()}
    rep = {}
    # emulation fidelity: control vs actual final_c477 (identical lists expected for most queries)
    for b, (L, _) in data.items():
        rep[f'{b}/control_identical_lists'] = int(sum(out[b]['control'][q] == L[q] for q in L))
        rep[f'{b}/queries'] = len(L)
    # selection on cal (K6 type 2 + T1-thin, equal weight), against control
    cal = {}
    for v in VARIANTS:
        if v == 'control':
            continue
        d = [compare(out[b]['control'], out[b][v], truths[b], mk, [q for q in qs if half(q) == 'cal'])['delta']
             for b, qs in (('K6', groups['K6']['type2']), ('T1thin', groups['T1thin']['type1']))]
        cal[v] = float(np.mean(d))
    best = max(cal, key=cal.get)
    rep['cal_mean_delta'] = cal
    rep['selected'] = best if cal[best] > 0 else 'control'
    print('cal', json.dumps(cal), 'selected', rep['selected'], flush=True)
    for b in benches:
        for g, qs in groups[b].items():
            for split in ('ver', 'all'):
                sel = [q for q in qs if split == 'all' or half(q) == 'ver']
                key = f'{b}/{g}/{split}/{rep["selected"]}_vs_control'
                rep[key] = compare(out[b]['control'], out[b][rep['selected']], truths[b], mk, sel)
                print(key, rep[key], flush=True)
            rep[f'{b}/{g}/control_vs_final_c477'] = compare(data[b][0], out[b]['control'], truths[b], mk, qs)
    Path(ROOT/'artifacts/K10').mkdir(exist_ok=True)
    (ROOT/'artifacts/K10/neural_ensemble_v1.json').write_text(json.dumps(rep, indent=1, default=float))
    print(json.dumps({k: v for k, v in rep.items() if 'identical' in k or 'queries' in k}), flush=True)


if __name__ == '__main__':
    main()
