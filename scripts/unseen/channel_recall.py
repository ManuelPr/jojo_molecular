"""Recall@K of the truth in Engine2 / PubChem channel lists of K2 CPU-phase runs (e.g. K2_DIAG_TOPN=200), by K6 type."""
import argparse
import glob
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def ik14(smiles, cache={}):
    if smiles not in cache:
        from rdkit import Chem, RDLogger
        RDLogger.DisableLog('rdApp.*')
        m = Chem.MolFromSmiles(smiles)
        cache[smiles] = Chem.MolToInchiKey(m)[:14] if m is not None else None
    return cache[smiles]


def first_rank(smis, truth):
    for r, s in enumerate(smis, 1):
        if ik14(s) == truth:
            return r
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', default='artifacts/k2_replay/cpu_k6diag200_s*')
    p.add_argument('--cohort', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    a = p.parse_args()
    mols = pd.read_parquet(a.cohort/'shards.parquet').set_index('molecule_id')
    rows = []
    for run in sorted(glob.glob(str(ROOT/a.runs))):
        run = Path(run)
        if not (run/'k2_cpu_phase_done.json').is_file():
            continue
        eng = json.loads((run/'eng_lists.json').read_text())
        pc = json.loads((run/'pc_lists.json').read_text())
        for q in mols.index[mols.shard == int(run.name.rsplit('_s', 1)[1])]:
            t = mols.inchikey14[q]
            e = first_rank(eng.get(q, {}).get('smiles', []), t)
            c = first_rank(pc.get(q, {}).get('pc', []), t)
            rows.append(dict(query=q, type=mols.type[q], eng_rank=e, pc_rank=c,
                             eng_len=len(eng.get(q, {}).get('smiles', [])), pc_len=len(pc.get(q, {}).get('pc', []))))
    d = pd.DataFrame(rows)
    out = []
    for t, g in d.groupby('type'):
        for k in (1, 5, 25, 50, 100, 200):
            out.append(dict(type=t, K=k, n=len(g), engine2=int((g.eng_rank <= k).sum()), pubchem=int((g.pc_rank <= k).sum()),
                            either=int(((g.eng_rank <= k) | (g.pc_rank <= k)).sum())))
    print('runs', d['query'].nunique(), 'median list len eng/pc', d.eng_len.median(), d.pc_len.median())
    print(pd.DataFrame(out).to_string(index=False))
    d.to_parquet(ROOT/'artifacts/K6/channel_recall_diag200.parquet', index=False)


if __name__ == '__main__':
    main()
