"""K6 analysis: per type (2 = structure in a catalog, 3 = in none), where the truth is in each C477 stage and the final MRR@25."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STAGES = ['main_pre_forward', 'main_post_forward', 'engine2', 'pubchem', 'pool', 'prefusion', 'final0465']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    p.add_argument('--runs', default='artifacts/k2_replay/r2_k6_s*')
    p.add_argument('--out', type=Path, default=ROOT/'artifacts/K6/analysis_v1')
    a = p.parse_args()
    mols = pd.read_parquet(a.cohort/'shards.parquet').set_index('molecule_id')
    parts, done = [], []
    for run in sorted(ROOT.glob(a.runs)):
        f = run/'k2_export/candidates.parquet'
        if (run/'k2_export/export_info.json').is_file():
            parts.append(pd.read_parquet(f)); done.append(run.name)
    c = pd.concat(parts, ignore_index=True)
    c = c[c.query_id.isin(mols.index)]
    c['truth'] = c.query_id.map(mols.inchikey14)
    c['hit'] = c.candidate_key.eq(c.truth)
    queries = sorted(set(c.query_id))
    rows = []
    for (arm, stage), g in c.groupby(['arm', 'stage']):
        if arm != 'base' and stage != 'final_c477':
            continue
        best = g[g.hit].groupby('query_id')['rank'].min()
        r = pd.Series(queries).map(best)
        for t in (2, 3, 'all'):
            sel = np.array([t == 'all' or mols.type[q] == t for q in queries])
            rr = r[sel]
            rows.append(dict(arm=arm, stage=stage, type=t, queries=int(sel.sum()), present=int(rr.notna().sum()),
                             top1=int((rr == 1).sum()), top25=int((rr <= 25).sum()),
                             mrr25=round(float(np.where(rr <= 25, 1/rr, 0).mean()), 4)))
    out = pd.DataFrame(rows)
    a.out.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.out/'stages_by_type.csv', index=False)
    (a.out/'runs.json').write_text(json.dumps(dict(runs=done, queries=len(queries)), indent=1))
    print('runs', len(done), 'queries', len(queries))
    print(out.pivot_table(index=['arm', 'stage'], columns='type', values=['present', 'top1', 'mrr25']).to_string())


if __name__ == '__main__':
    main()
