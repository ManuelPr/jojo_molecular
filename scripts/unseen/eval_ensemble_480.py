"""K11: the public 0.480 final layer emulated on the replays, to choose the neural ensemble that goes on it.
Per query: neural score = weighted mean of per-molecule z-scores of the arms (sanpier = public scorer, bgunshui = the
0.480 line's second scorer, jm_base = our JM-base); ranks 2-25 re-sorted with the CUSTOM formula
1/(3+baseline_rank) + 0.75/(3+neural_rank), then the midx documentation prior (eval_docprior_layer.docprior, which
re-reads the neural rank) - rank 1 is never changed. Reference = the 0.480 line (sanpier 0.5 / bgunshui 0.5).
Grid fixed below; selection on the cal half (sha256(query_id) even) of T1-thin + K6 type 2, one verification on ver.

Usage: eval_ensemble_480.py  -> artifacts/K11/ensemble_480_v1.json   (run with CASMI_ROOT=<main checkout>)
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
from eval_docprior_layer import compare, docprior, POP  # noqa: E402
from eval_smiles_level import metric_keys  # noqa: E402

ARMS = ['sanpier', 'bgunshui', 'jm_base']
GRID = {'ref_480': (0.5, 0.5, 0.0), 'jm3_50_25_25': (0.5, 0.25, 0.25), 'jm3_thirds': (1/3, 1/3, 1/3),
        'jm3_40_30_30': (0.4, 0.3, 0.3), 'jm3_50_30_20': (0.5, 0.3, 0.2), 'pub_jm_50_50': (0.5, 0.0, 0.5)}


def load(pattern):
    runs = [r for r in sorted(glob.glob(str(ROOT/'artifacts/k2_replay'/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]
    lists, frames = {}, []
    for r in runs:
        c = pd.read_parquet(Path(r)/'k2_export/candidates.parquet')
        f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
        lists.update(f.groupby('query_id').smiles.apply(list).to_dict())
        base = pd.read_parquet(Path(r)/'k2_export/neural_sanpier.parquet')
        base = base.rename(columns={'neural_score': 'sanpier'})
        for m in ARMS[1:]:
            s = pd.read_parquet(Path(r)/f'k2_export/neural_{m}.parquet')[['molecule_id', 'smiles', 'neural_score']]
            base = base.merge(s.rename(columns={'neural_score': m}), on=['molecule_id', 'smiles'], how='left')
        frames.append(base)
    return lists, pd.concat(frames)


def zscore(s):
    g = s.groupby(level=0)
    return (s - g.transform('mean')) / g.transform(lambda x: x.std(ddof=0)).clip(lower=1e-6)


def final_layer(lists, nf, w, prior):
    nf = nf.copy()
    idx = nf.set_index(['molecule_id', 'smiles']).index
    ens = sum(wi * zscore(pd.Series(nf[m].astype(float).fillna(nf[m].min()).to_numpy(), index=idx)) for wi, m in zip(w, ARMS) if wi)
    nf['neural_score'] = ens.to_numpy()
    custom = {}
    for mid, g in nf.groupby('molecule_id', sort=False):
        if mid not in lists:
            continue
        L = lists[mid]
        nr = g.set_index('smiles').neural_score.rank(ascending=False, method='first')
        br = g.set_index('smiles').baseline_rank
        def key(s):
            if s in nr.index:
                return 1/(3+float(br[s])) + 0.75/(3+float(nr[s]))
            return 1/(3+L.index(s)+1)
        custom[mid] = [L[0]] + sorted(L[1:], key=key, reverse=True)
    for mid in lists:
        custom.setdefault(mid, lists[mid])
    return docprior(custom, nf, *prior)


def half(q):
    return 'cal' if int(hashlib.sha256(str(q).encode()).hexdigest(), 16) % 2 == 0 else 'ver'


def main():
    p = pd.read_csv(POP, usecols=['inchikey14', 'pop', 'src_spectral_library', 'np_coconut', 'np_lotus', 'src_natural_product'])
    prior = (dict(zip(p.inchikey14, p['pop'])), dict(zip(p.inchikey14, p.src_spectral_library)),
             dict(zip(p.inchikey14, (p.np_coconut | p.np_lotus | p.src_natural_product).astype(int))))
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
    data = {b: load(pt) for b, pt in benches.items()}
    out = {b: {v: final_layer(L, nf, w, prior) for v, w in GRID.items()} for b, (L, nf) in data.items()}
    mk = metric_keys(list(t1_smiles.dropna()) + [s for L, _ in data.values() for x in L.values() for s in x])
    t1_truth = {q: mk.get(s) for q, s in t1_smiles.items()}
    truths = {'T1thin': t1_truth, 'T1': t1_truth, 'K6': k6.truth_metric.to_dict(), 'K7': k7_truth}
    groups = {'T1thin': {'type1': list(t1.index)}, 'T1': {'type1': list(t1.index)},
              'K6': {f'type{t}': list(k6.index[k6.type_metric == t]) for t in (2, 3)}, 'K7': {'type3_np': list(k7_truth)}}
    rep = {'grid': GRID}
    for b, (L, _) in data.items():
        for g, qs in groups[b].items():
            rep[f'{b}/{g}/ref_480_vs_c477'] = compare(L, out[b]['ref_480'], truths[b], mk, qs)
            print(f'{b}/{g}/ref_480_vs_c477', rep[f'{b}/{g}/ref_480_vs_c477'], flush=True)
    cal = {}
    for v in GRID:
        if v == 'ref_480':
            continue
        cal[v] = float(np.mean([compare(out[b]['ref_480'], out[b][v], truths[b], mk, [q for q in qs if half(q) == 'cal'])['delta']
                                for b, qs in (('K6', groups['K6']['type2']), ('T1thin', groups['T1thin']['type1']))]))
    best = max(cal, key=cal.get)
    rep['cal_mean_delta'] = cal
    rep['selected'] = best if cal[best] > 0 else 'ref_480'
    print('cal', json.dumps(cal), 'selected', rep['selected'], flush=True)
    for b in benches:
        for g, qs in groups[b].items():
            for split in ('ver', 'all'):
                sel = [q for q in qs if split == 'all' or half(q) == 'ver']
                for v in ([rep['selected']] if split == 'ver' else list(cal)):
                    key = f'{b}/{g}/{split}/{v}_vs_ref_480'
                    rep[key] = compare(out[b]['ref_480'], out[b][v], truths[b], mk, sel)
                    if split == 'ver' or v == rep['selected']:
                        print(key, rep[key], flush=True)
    Path(ROOT/'artifacts/K11').mkdir(exist_ok=True)
    (ROOT/'artifacts/K11/ensemble_480_v1.json').write_text(json.dumps(rep, indent=1, default=float))


if __name__ == '__main__':
    main()
