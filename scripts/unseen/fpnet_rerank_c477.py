"""Score every SMILES of the C477 final lists with the five fold-safe FPNets (K6 and T1), for rerank experiments.

Output per bench: molecule_id, rank (C477), smiles, metric key (official identity), fpnet score.
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from eval_smiles_level import metric_keys  # noqa: E402
from fpnet_retrieval import CODE, FOLD_SAFE, fpnet_scores  # noqa: E402


def main():
    sys.path.insert(0, str(CODE))
    from casmi import fpnet
    bits = np.load(FOLD_SAFE/'fp_bits.npy')
    models = [fpnet.load_model(str(FOLD_SAFE/f'fpnet_fold{k}.pt'), 'cuda') for k in range(5)]
    for name, cohort, runs in [('k6', 'artifacts/K6/unseen_v1', 'artifacts/k2_replay/r2_k6_s?'),
                               ('t1', 'artifacts/K6/type1_np250_v1', 'artifacts/k2_replay/r_t1_np250')]:
        test = pd.read_parquet(ROOT/cohort/'competition/test.parquet')
        groups = {str(m): g for m, g in test.groupby('molecule_id')}
        c = pd.concat([pd.read_parquet(r+'/k2_export/candidates.parquet') for r in sorted(glob.glob(str(ROOT/runs)))])
        f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
        mk = metric_keys(list(f.smiles))
        rows, cache = [], {}
        for q, g in f.groupby('query_id'):
            s = fpnet_scores(groups[q], list(g.smiles), models, bits, cache)
            rows.append(pd.DataFrame(dict(molecule_id=q, rank=g['rank'].to_numpy(), smiles=g.smiles.to_numpy(),
                                          key=g.smiles.map(mk).to_numpy(), fpnet=s)))
        out = pd.concat(rows, ignore_index=True)
        out.to_parquet(ROOT/f'artifacts/K6/c477_lists_fpnet_{name}.parquet', index=False)
        print(name, len(out), flush=True)


if __name__ == '__main__':
    main()
