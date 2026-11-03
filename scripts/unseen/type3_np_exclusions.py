"""K7 step 1: NP type-3 bench from K6 type-2 natural products, made 'novel' by withholding them from every catalog and from
the PubChem tier. This step finds the PubChem-tier rows to withhold: rows within 10 ppm of a truth mass whose raw InChIKey14
or official metric identity equals the truth's (metric identity computed only for rows with the truth's heavy-atom
composition, the metric's own cheap gate). Output: artifacts/K7/np_type3_v1/{molecules.parquet, pubchem_excluded_rows.npy}.
"""
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from eval_smiles_level import canonicalize_smiles_to_ik14  # noqa: E402
from jm_retrieval import ASSETS  # noqa: E402

OUT = ROOT/'artifacts/K7/np_type3_v1'


def composition(smiles):
    from rdkit import Chem
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return None
    c = {}
    for a in m.GetAtoms():
        if a.GetSymbol() != 'H':
            c[a.GetSymbol()] = c.get(a.GetSymbol(), 0) + 1
    return tuple(sorted(c.items()))


def window_rows(job):
    truth_raw, truth_metric, comp, mass = job
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    pm = np.load(ASSETS/'pubchem_tier__pc_mass.npy', mmap_mode='r')
    off = np.load(ASSETS/'pubchem_tier__pc_off.npy', mmap_mode='r')
    smi = np.load(ASSETS/'pubchem_tier__pc_smiles.npy', mmap_mode='r')
    lo, hi = np.searchsorted(pm, [mass*(1-10e-6), mass*(1+10e-6)])
    hits = []
    for j in range(lo, hi):
        s = bytes(smi[off[j]:off[j+1]]).decode()
        m = Chem.MolFromSmiles(s)
        if m is None:
            continue
        if Chem.MolToInchiKey(m)[:14] == truth_raw:
            hits.append(j); continue
        if composition(s) == comp and canonicalize_smiles_to_ik14(s) == truth_metric:
            hits.append(j)
    return hits, int(hi - lo)


def main():
    m = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules_metric.parquet')
    coco = set(pickle.load(open(ASSETS/'coconut-casmi26-candidates/coco_meta.pkl', 'rb'))['keys'])
    pm = pd.read_parquet(ASSETS/'casmi26-v2-pool/pool_meta.parquet', columns=['key', 'src'])
    np_pool = set(pm[pm.src == 2].key)
    t2 = m[m.type_metric == 2].copy()
    keys = t2.inchikey14.isin(coco) | t2.truth_metric.isin(coco) | t2.inchikey14.isin(np_pool) | t2.truth_metric.isin(np_pool)
    sel = t2[keys | t2.np_library].copy()
    sel['composition'] = sel.smiles.map(composition)
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = list(zip(sel.inchikey14, sel.truth_metric, sel.composition, sel.mass))
    rows, sizes = [], []
    with ProcessPoolExecutor(24) as ex:
        for k, (h, n) in enumerate(ex.map(window_rows, jobs, chunksize=2)):
            rows.append(h); sizes.append(n)
            if (k+1) % 25 == 0:
                print(k+1, 'molecules', flush=True)
    sel['pubchem_rows'] = rows
    sel['pubchem_window'] = sizes
    sel.drop(columns=['composition']).to_parquet(OUT/'molecules.parquet', index=False)
    allrows = np.array(sorted({j for h in rows for j in h}), dtype=np.int64)
    np.save(OUT/'pubchem_excluded_rows.npy', allrows)
    print('molecules', len(sel), 'with PubChem rows', int(sum(bool(h) for h in rows)), 'rows excluded', len(allrows),
          'median window', float(np.median(sizes)))


if __name__ == '__main__':
    main()
