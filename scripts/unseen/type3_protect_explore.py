"""K6/T1: FPNet channel variants that protect generated candidates (type-3 cost). Exploration on the calibration half only."""
import glob
import hashlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, 'scripts/unseen')
import jm_channel_merge as J  # noqa: E402


def load(cohort, runs, lists):
    m = pd.read_parquet(cohort+'/molecules.parquet').set_index('molecule_id')
    c = pd.concat([pd.read_parquet(r+'/k2_export/candidates.parquet') for r in sorted(glob.glob(runs))])
    f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
    c477 = f.groupby('query_id').candidate_key.apply(list).to_dict()
    mp = c[(c.arm == 'base') & (c.stage == 'main_post_forward')].sort_values(['query_id', 'rank'])
    org = mp.drop_duplicates(['query_id', 'candidate_key']).set_index(['query_id', 'candidate_key']).origin.to_dict()
    lead_gen = mp.groupby('query_id').origin.first().eq('generated').to_dict()
    fp = pd.read_parquet(lists).sort_values(['molecule_id', 'jm_rank']).groupby('molecule_id').key.apply(list).to_dict()
    return m, c477, org, lead_gen, fp


def plain(q, c, fp, org, lg, w):
    return J.merged(c, fp, w)


def skip_if_generated_leader(q, c, fp, org, lg, w):
    return c[:25] if lg.get(q, False) else J.merged(c, fp, w)


def keep_generated_positions(q, c, fp, org, lg, w):
    new = J.merged(c, fp, w)
    keep = {i: k for i, k in enumerate(c[:25]) if org.get((q, k)) == 'generated'}
    rest = [k for k in new if k not in keep.values()]
    out = []
    for i in range(25):
        if i in keep:
            out.append(keep[i])
        elif rest:
            out.append(rest.pop(0))
    return out


POLICIES = dict(plain=plain, skip_if_generated_leader=skip_if_generated_leader, keep_generated_positions=keep_generated_positions)

if __name__ == '__main__':
    m, c477, org, lg, fp = load('artifacts/K6/unseen_v1', 'artifacts/k2_replay/r2_k6_s?', 'artifacts/K6/fpnet5_lists_k6.parquet')
    q = sorted(set(c477) & set(m.index))
    part = {x: ('cal' if int(hashlib.sha256(x.encode()).hexdigest(), 16) % 2 == 0 else 'ver') for x in q}
    print('C477 main leader generated, rate by type:',
          pd.Series({x: lg.get(x, False) for x in q}).groupby(m.type.loc[q].values).mean().round(3).to_dict())
    for name, pol in POLICIES.items():
        for w in (1.0, 2.0):
            res = []
            for t in (2, 3):
                xs = [x for x in q if part[x] == 'cal' and m.type[x] == t]
                d = np.mean([J.rr(pol(x, c477[x], fp.get(x, []), org, lg, w), m.inchikey14[x]) - J.rr(c477[x], m.inchikey14[x]) for x in xs])
                res.append(f'type{t} {d:+.4f}')
            print(f'{name:26s} w={w} cal: ' + '  '.join(res))
