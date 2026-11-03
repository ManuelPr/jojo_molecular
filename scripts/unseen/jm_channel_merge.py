"""K6: C477 final list + JM retrieval channel, leader-safe (rank 1 of C477 kept, ranks 2-25 merged by reciprocal rank).

Protocol fixed before looking at the merge results: molecules split 50/50 into calibration and verification by a hash of
the molecule id; the JM weight w is chosen on calibration from {0.25, 0.5, 1.0, 2.0}; the verification half is scored once
with that w, against C477 unchanged, with a paired bootstrap per molecule.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRID = (0.25, 0.5, 1.0, 2.0)
OFFSET = 3.0


def merged(c477, jm, w):
    """c477, jm: candidate keys in order. Rank 1 = C477 rank 1; ranks 2-25 by 1/(k+b) + w/(k+n)."""
    if not c477:
        return jm[:25]
    lead = c477[0]
    score = {}
    for b, key in enumerate(c477[1:], 2):
        score[key] = score.get(key, 0) + 1/(OFFSET+b)
    for n, key in enumerate(jm, 1):
        if key != lead:
            score[key] = score.get(key, 0) + w/(OFFSET+n)
    rest = sorted(score, key=lambda k: -score[k])
    return [lead] + rest[:24]


def rr(keys, truth):
    return next((1/i for i, k in enumerate(keys[:25], 1) if k == truth), 0.0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    p.add_argument('--runs', default='artifacts/k2_replay/r2_k6_s*')
    p.add_argument('--jm', type=Path, default=ROOT/'artifacts/K6/jm_retrieval_lists_v1.parquet')
    p.add_argument('--out', type=Path, default=ROOT/'artifacts/K6/jm_merge_v1.json')
    p.add_argument('--fixed-w', type=float, help='skip selection: score every query (all as verification) with this w')
    a = p.parse_args()
    mols = pd.read_parquet(a.cohort/'molecules.parquet').set_index('molecule_id')
    parts = [pd.read_parquet(r/'k2_export/candidates.parquet') for r in sorted(ROOT.glob(a.runs))
             if (r/'k2_export/export_info.json').is_file()]
    c = pd.concat(parts)
    c = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
    c477 = c.groupby('query_id').candidate_key.apply(list).to_dict()
    jm = pd.read_parquet(a.jm).sort_values(['molecule_id', 'jm_rank']).groupby('molecule_id').key.apply(list).to_dict()
    q = sorted(set(c477) & set(mols.index))
    part = {x: ('cal' if a.fixed_w is None and int(hashlib.sha256(x.encode()).hexdigest(), 16) % 2 == 0 else 'ver') for x in q}
    truth = mols.inchikey14.to_dict()
    base = {x: rr(c477[x], truth[x]) for x in q}
    cal = [x for x in q if part[x] == 'cal']
    cal_scores = {w: float(np.mean([rr(merged(c477[x], jm.get(x, []), w), truth[x]) for x in cal])) for w in GRID} if cal else {}
    w = a.fixed_w if a.fixed_w is not None else max(GRID, key=lambda k: cal_scores[k])
    rng = np.random.default_rng(0)
    report = dict(queries=len(q), grid=GRID, cal_scores=cal_scores, chosen_w=w, cal_base=float(np.mean([base[x] for x in cal])) if cal else None,
                  verification={})
    for t in sorted(set(mols.type[q])) + ['all']:
        ver = [x for x in q if part[x] == 'ver' and (t == 'all' or mols.type[x] == t)]
        new = np.array([rr(merged(c477[x], jm.get(x, []), w), truth[x]) for x in ver])
        old = np.array([base[x] for x in ver])
        d = new - old
        if not len(d):
            continue
        boot = d[rng.integers(0, len(d), (5000, len(d)))].mean(1)
        report['verification'][str(t)] = dict(n=len(ver), c477=round(old.mean(), 4), merged=round(new.mean(), 4),
                                              delta=round(d.mean(), 4), ci95=np.quantile(boot, [.025, .975]).round(4).tolist(),
                                              improved=int((d > 0).sum()), worsened=int((d < 0).sum()),
                                              top1_changed=0)
    a.out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
