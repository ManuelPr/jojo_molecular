"""G3b: type-3 gate computable INSIDE Engine 1 (pipeline cell 39), so the kernel runs genfix only for gated queries.
Features available at that point, from the base run: library_max, Engine-1 ('main' stage) score gap rank1-rank2 and
top score, generated share of the Engine-1 top 10 and of its leader (key absent from pool/pubchem/engine2 stages), pool size,
PubChem channel size, Engine-2 size. Everything downstream is per query, so 'genfix list if gated else base list'
emulates that kernel exactly on the replays. Protocol as G3 (fixed before scores, 2026-11-06): logistic C=1 on K6 clean
cal type 3 vs type 2; thresholds = fire rates 5/10/20/30% on T1-thin cal; choice on the cal mix 0.35 T1thin + 0.30 K6t2 +
0.35 K6t3; one verification on ver; T1 and K7 as transfer checks.
Usage: CASMI_ROOT=<main> g3b_early_gate.py -> artifacts/G3/gate_early_v2.json
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g3_type3_gate as g3  # noqa: E402

FEATS = ['library_max', 'n_union', 'n_pubchem', 'n_engine2']  # v2: only quantities the kernel has in cell 39
g3.FIRE = [0.05, 0.10, 0.20, 0.30]


def features(pattern):
    rows = []
    for r in g3.runs(pattern):
        c = pd.read_parquet(Path(r)/'k2_export/candidates.parquet')
        n = pd.read_parquet(Path(r)/'k2_export/neural_sanpier.parquet', columns=['molecule_id', 'library_max'])
        lib = n.groupby('molecule_id').library_max.max()
        for q, g in c.groupby('query_id', sort=False):
            e1 = g[g.stage == 'main'].sort_values('rank')
            cat = set(g[g.stage.isin(['pool', 'pubchem', 'engine2'])].candidate_key)
            sc = e1.score.to_numpy(float)
            rows.append(dict(query_id=q, library_max=float(lib.get(q, 0.0)),
                             e1_gap=float(sc[0] - sc[1]) if len(sc) > 1 else 0.0, e1_top=float(sc[0]) if len(sc) else 0.0,
                             e1_gen10=float(np.mean([k not in cat for k in e1.candidate_key.head(10)])) if len(e1) else 0.0,
                             e1_leader_gen=float(e1.candidate_key.iloc[0] not in cat) if len(e1) else 0.0,
                             n_union=float(len(set(g[g.stage.isin(['main', 'engine2', 'pubchem'])].smiles))),
                             n_pubchem=float((g.stage == 'pubchem').sum()),
                             n_engine2=float((g.stage == 'engine2').sum())))
    return pd.DataFrame(rows).set_index('query_id').fillna(0.0)


if __name__ == '__main__':
    g3.FEATS = FEATS
    g3.features = features
    out = Path(os.environ.get('CASMI_ROOT', '/home/mpernigotto/jojo_molecular'))/'artifacts/G3/gate_v1.json'
    tmp = out.with_name('gate_v1_g3_backup.json')
    if out.exists():
        out.rename(tmp)
    try:
        g3.main()
        out.rename(out.with_name('gate_early_v2.json'))
    finally:
        if tmp.exists():
            tmp.rename(out)
