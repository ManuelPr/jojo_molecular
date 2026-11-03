"""K6 scorer bake-off: retrieval quality of each scorer and of z-score averages, on the same in-window candidates.

Single scorers are reported on every type-2 molecule with the truth in the window. Combinations (equal-weight averages of
within-molecule z-scores over every subset of scorers) are selected on the calibration half (hash of the molecule id, as in
jm_channel_merge.py) and reported once on the verification half.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def ranks(df, col):
    """df: molecule_id, key, truth, <col>. Rank of the truth (1 = best) per molecule."""
    out = {}
    for q, g in df.groupby('molecule_id', sort=False):
        s = g[col].to_numpy()
        t = g.key.to_numpy() == g.truth.iat[0]
        if not t.any():
            continue
        best = s[t].max()  # ties share the average rank (isomers often have identical fingerprints)
        out[q] = float((s > best).sum() + ((s == best).sum() - 1) / 2 + 1)
    return pd.Series(out)


def summary(r):
    return dict(n=len(r), mrr25=round(float(np.where(r <= 25, 1/r, 0).mean()), 4), r1=int((r == 1).sum()),
                r5=int((r <= 5).sum()), r25=int((r <= 25).sum()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dir', type=Path, default=ROOT/'artifacts/K6/bakeoff')
    p.add_argument('--cohort', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    a = p.parse_args()
    mols = pd.read_parquet(a.cohort/'molecules.parquet').set_index('molecule_id')
    names = sorted(f.name[:-len('_scores.parquet')] for f in a.dir.glob('*_scores.parquet'))
    base = None
    for n in names:
        s = pd.read_parquet(a.dir/f'{n}_scores.parquet').drop_duplicates(['molecule_id', 'key']).rename(columns={'score': n})
        base = s if base is None else base.merge(s, on=['molecule_id', 'key'], how='inner')
    base = base[base.molecule_id.map(mols.type).eq(2)].copy()
    base['truth'] = base.molecule_id.map(mols.inchikey14)
    for n in names:
        v = base[n].replace(-np.inf, np.nan)
        g = v.groupby(base.molecule_id)
        base[n+'_z'] = ((v - g.transform('mean')) / g.transform('std').replace(0, 1)).fillna(-10)
    part = {q: ('cal' if int(hashlib.sha256(q.encode()).hexdigest(), 16) % 2 == 0 else 'ver') for q in base.molecule_id.unique()}
    base['part'] = base.molecule_id.map(part)
    report = dict(scorers=names, single={}, combos_cal={}, chosen=None, verification={})
    for n in names:
        report['single'][n] = summary(ranks(base, n+'_z'))
    cal, ver = base[base.part == 'cal'], base[base.part == 'ver']
    for k in range(1, len(names)+1):
        for combo in itertools.combinations(names, k):
            col = '+'.join(combo)
            cal = cal.assign(**{col: cal[[c+'_z' for c in combo]].mean(axis=1)})
            report['combos_cal'][col] = summary(ranks(cal, col))
    best = max(report['combos_cal'], key=lambda c: report['combos_cal'][c]['mrr25'])
    report['chosen'] = best
    combo = best.split('+')
    best_single = max(names, key=lambda n: report['combos_cal'][n]['mrr25'])
    for label, cols in (('chosen', combo), ('best_single_on_cal', [best_single])):
        v = ver.assign(score=ver[[c+'_z' for c in cols]].mean(axis=1))
        report['verification'][label] = dict(scorers=cols, **summary(ranks(v, 'score')))
    (a.dir/'bakeoff_report.json').write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != 'combos_cal'}, indent=1))
    top = sorted(report['combos_cal'].items(), key=lambda x: -x[1]['mrr25'])[:8]
    print('top combos on cal:'); [print(' ', c, s) for c, s in top]


if __name__ == '__main__':
    main()
