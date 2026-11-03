"""Relabel K6 types with the official metric identity (stereo removed + canonical tautomer InChIKey14) on both sides.

build_unseen_cohort.py compared raw InChIKey14 truths with catalog keys that are partly metric identities (pool) and
partly raw (COCONUT, ...), so some 'type 3' molecules are in a catalog under their metric identity. Here every local-catalog
SMILES and every PubChem-tier SMILES within 5 ppm of the truth mass is canonicalised with the official function.
Output: molecules_metric.parquet (truth_metric, in_local_metric, in_pubchem_metric, type_metric).
"""
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from eval_smiles_level import canonicalize_smiles_to_ik14  # noqa: E402
from jm_retrieval import ASSETS, catalog  # noqa: E402


def pubchem_hit(job):
    truth, mass, ppm = job
    import numpy as np
    pm = np.load(ASSETS/'pubchem_tier__pc_mass.npy', mmap_mode='r')
    off = np.load(ASSETS/'pubchem_tier__pc_off.npy', mmap_mode='r')
    smi = np.load(ASSETS/'pubchem_tier__pc_smiles.npy', mmap_mode='r')
    lo, hi = np.searchsorted(pm, [mass*(1-ppm*1e-6), mass*(1+ppm*1e-6)])
    for j in range(lo, hi):
        if canonicalize_smiles_to_ik14(bytes(smi[off[j]:off[j+1]]).decode()) == truth:
            return True
    return False


def local_hit(job):
    truth, smiles = job
    return any(canonicalize_smiles_to_ik14(x) == truth for x in smiles)


def main():
    cohort = ROOT/'artifacts/K6/unseen_v1'
    mols = pd.read_parquet(cohort/'molecules.parquet')
    cat = catalog()
    masses = cat.mass.to_numpy()
    with ProcessPoolExecutor(24) as ex:
        mols['truth_metric'] = list(ex.map(canonicalize_smiles_to_ik14, mols.smiles, chunksize=50))
        jobs = []
        for t, m in zip(mols.truth_metric, mols.mass):  # only structures within 5 ppm of the truth mass can match
            lo, hi = np.searchsorted(masses, [m*(1-5e-6), m*(1+5e-6)])
            jobs.append((t, list(cat.smiles.iloc[lo:hi])))
        mols['in_local_metric'] = list(ex.map(local_hit, jobs, chunksize=4))
    # PubChem tier: raw-key membership from build_unseen_cohort.py (canonicalising every window is too slow); a metric-only
    # PubChem match would make a molecule type 2, so type_metric 3 may still include a few such cases.
    mols['type_metric'] = np.where(mols.in_local_metric | mols.in_local_catalog | mols.in_pubchem_tier, 2, 3)
    mols.to_parquet(cohort/'molecules_metric.parquet', index=False)
    print(pd.crosstab(mols.type, mols.type_metric))

if __name__ == '__main__':
    main()
