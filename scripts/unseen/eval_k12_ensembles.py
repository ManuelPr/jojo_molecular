"""K12: the public 0.480 final layer (K11 emulation) with the new sanpier-family scorers as ensemble members.

Arms (k2_export/neural_<arm>.parquet, scored by scripts/cluster/score_extra_arm.py): sanpier = public anchor, bgunshui = the
0.480 line's second scorer (kit 16 ep), bgv2 (kit 80 ep), bgv4 (kit 120 ep, width 256), prv03/prv04 (prvsiyan seeds, kit
80 ep), ylspec (yunlong timsTOF specialist). Neural score = weighted mean of per-molecule z-scores; ranks 2-25 re-sorted with
the CUSTOM formula 1/(3+baseline_rank) + 0.75/(3+neural_rank), then the documentation prior; rank 1 never changes
(final_layer of eval_ensemble_480). Reference = ref_480 (sanpier 0.5 / bgunshui 0.5).
Grid fixed below BEFORE any score was computed (2026-11-05); selection on the cal half (sha256(query_id) even) of K6 type 2
(clean, never in train) + T1-thin, one verification on ver. All self-trained arms are trained on full train.parquet, so T1
and T1-thin truths are exposed to them; K6 is the clean bench.

Usage: CASMI_ROOT=<main checkout> eval_k12_ensembles.py -> artifacts/K12/ensembles_v1.json
"""
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get('CASMI_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_ensemble_480 as k11  # noqa: E402
from eval_docprior_layer import compare, docprior, POP  # noqa: E402
from eval_smiles_level import metric_keys  # noqa: E402

ARMS = ['sanpier', 'bgunshui', 'bgv2', 'bgv4', 'prv03', 'prv04', 'ylspec']


def w(**kw):
    return tuple(kw.get(a, 0.0) for a in ARMS)


SELF4 = dict(bgv2=0.125, bgv4=0.125, prv03=0.125, prv04=0.125)
GRID = {
    'ref_480': w(sanpier=0.5, bgunshui=0.5),
    'tri_v2v4': w(sanpier=0.5, bgv2=0.25, bgv4=0.25),                      # zz3t3rn41 v30 (0.481 public)
    'quad_prv': w(sanpier=0.5, prv03=0.25, prv04=0.25),                    # ozertuu / prvsiyan
    'tri_yl': w(sanpier=1/3, bgunshui=1/3, ylspec=1/3),                    # yunlong v27 thirds
    'pub_v4': w(sanpier=0.5, bgv4=0.5),
    'all_self': w(sanpier=0.5, bgunshui=0.1, bgv2=0.1, bgv4=0.1, prv03=0.1, prv04=0.1),
    'self4': w(sanpier=0.5, **SELF4),
    'self4_heavy': w(sanpier=0.3, **{k: 0.175 for k in SELF4}),
}


def load(pattern):
    runs = [r for r in sorted(glob.glob(str(ROOT/'artifacts/k2_replay'/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]
    lists, frames = {}, []
    for r in runs:
        c = pd.read_parquet(Path(r)/'k2_export/candidates.parquet')
        f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
        lists.update(f.groupby('query_id').smiles.apply(list).to_dict())
        base = pd.read_parquet(Path(r)/'k2_export/neural_sanpier.parquet').rename(columns={'neural_score': 'sanpier'})
        for m in ARMS[1:]:
            s = pd.read_parquet(Path(r)/f'k2_export/neural_{m}.parquet')[['molecule_id', 'smiles', 'neural_score']]
            base = base.merge(s.rename(columns={'neural_score': m}), on=['molecule_id', 'smiles'], how='left')
        frames.append(base)
    return lists, pd.concat(frames)


def main():
    k11.ARMS = ARMS  # final_layer zips weights with k11.ARMS
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
    for b, (_, nf) in data.items():
        print(b, 'missing scores per arm', {m: int(nf[m].isna().sum()) for m in ARMS}, 'rows', len(nf), flush=True)
    out = {b: {v: k11.final_layer(L, nf, wt, prior) for v, wt in GRID.items()} for b, (L, nf) in data.items()}
    mk = metric_keys(list(t1_smiles.dropna()) + [s for L, _ in data.values() for x in L.values() for s in x])
    t1_truth = {q: mk.get(s) for q, s in t1_smiles.items()}
    truths = {'T1thin': t1_truth, 'T1': t1_truth, 'K6': k6.truth_metric.to_dict(), 'K7': k7_truth}
    groups = {'T1thin': {'type1': list(t1.index)}, 'T1': {'type1': list(t1.index)},
              'K6': {f'type{t}': list(k6.index[k6.type_metric == t]) for t in (2, 3)}, 'K7': {'type3_np': list(k7_truth)}}
    rep = {'grid': {k: dict(zip(ARMS, v)) for k, v in GRID.items()}}
    cal = {}
    for v in GRID:
        if v == 'ref_480':
            continue
        cal[v] = float(np.mean([compare(out[b]['ref_480'], out[b][v], truths[b], mk, [q for q in qs if k11.half(q) == 'cal'])['delta']
                                for b, qs in (('K6', groups['K6']['type2']), ('T1thin', groups['T1thin']['type1']))]))
    best = max(cal, key=cal.get)
    rep['cal_mean_delta'] = cal
    rep['selected'] = best if cal[best] > 0 else 'ref_480'
    print('cal', json.dumps(cal), 'selected', rep['selected'], flush=True)
    for b in benches:
        for g, qs in groups[b].items():
            for split in ('ver', 'all'):
                sel = [q for q in qs if split == 'all' or k11.half(q) == 'ver']
                for v in ([rep['selected']] if split == 'ver' else list(cal)):
                    key = f'{b}/{g}/{split}/{v}_vs_ref_480'
                    rep[key] = compare(out[b]['ref_480'], out[b][v], truths[b], mk, sel)
                    print(key, rep[key], flush=True)
    Path(ROOT/'artifacts/K12').mkdir(exist_ok=True)
    (ROOT/'artifacts/K12/ensembles_v1.json').write_text(json.dumps(rep, indent=1, default=float))


if __name__ == '__main__':
    main()
