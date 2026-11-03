"""K6 experiment: retrieval channel that scores every local-catalog structure within 10 ppm of the query neutral mass with a
JM spectrum<->structure model, instead of reranking only the final 25. Reports the truth rank per molecule.

The neutral mass comes from the query precursors and adducts (median over spectra), never from the truth structure.
Catalogs: pool (train + COCONUT subset), COCONUT candidates, ChEBI/LMSD, ChEBI/LIPID MAPS, PubChemLite (deduplicated by IK14).
"""
import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'data/fastweb/casmi26-attributed-v4g-reproduction-assets-v6'
ADDUCTS = {'[M+H]+': 1.007276, '[M-H]-': -1.007276, '[M+Na]+': 22.989218, '[M+NH4]+': 18.033823, '[M+K]+': 38.963158,
           '[M+Cl]-': 34.969402, '[M+CH2O2-H]-': 44.998201}


def catalog():
    from rdkit import Chem, RDLogger
    from rdkit.Chem.Descriptors import ExactMolWt
    RDLogger.DisableLog('rdApp.*')
    pool = pd.read_parquet(ASSETS/'casmi26-v2-pool/pool_meta.parquet', columns=['key', 'smiles', 'mass']).assign(src='pool')
    parts = [pool]
    for name, f, massf in [('coconut', 'coconut-casmi26-candidates/coco_meta.pkl', 'coconut-casmi26-candidates/coco_mass.npy'),
                           ('chebi_lipidmaps', 'chebi-lipidmaps-casmi26/bio_meta.pkl', 'chebi-lipidmaps-casmi26/bio_mass.npy'),
                           ('pubchemlite', 'casmi26-pubchemlite-cc0-candidate-fingerprints/pubchemlite_meta.pkl',
                            'casmi26-pubchemlite-cc0-candidate-fingerprints/pubchemlite_mass.npy'),
                           ('chebi_lmsd', 'casmi-chebi-lmsd-structures/bio_meta.pkl', 'casmi-chebi-lmsd-structures/bio_mass.npy')]:
        m = pickle.load(open(ASSETS/f, 'rb'))
        mass = np.load(ASSETS/massf)
        assert len(mass) == len(m['keys']), name
        parts.append(pd.DataFrame(dict(key=list(m['keys']), smiles=list(m['smiles']), mass=mass, src=name)))
    c = pd.concat(parts, ignore_index=True).drop_duplicates('key').sort_values('mass', kind='stable').reset_index(drop=True)
    return c


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, default=ROOT/'kaggle/jm_submissions/jm-base-full/dataset')
    p.add_argument('--cohort', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    p.add_argument('--ppm', type=float, default=10.0)
    p.add_argument('--out', type=Path, default=ROOT/'artifacts/K6/jm_retrieval_v1.parquet')
    p.add_argument('--all-scores', type=Path, help='also write every candidate score (molecule_id, key, score)')
    a = p.parse_args()
    sys.path[:0] = [str(a.bundle), str(ROOT/'kaggle/jm_scorer')]  # bundle model/features first, then inference.py
    from inference import Scorer
    scorer = Scorer(a.bundle)
    cat = catalog()
    masses = cat.mass.to_numpy()
    print('catalog structures', len(cat), cat.src.value_counts().to_dict(), flush=True)
    mols = pd.read_parquet(a.cohort/'molecules.parquet').set_index('molecule_id')
    test = pd.read_parquet(a.cohort/'competition/test.parquet')
    rows, lists, everything = [], [], []
    for k, (q, g) in enumerate(test.groupby('molecule_id', sort=True)):
        neutral = float(np.median(g.precursor_mz - g.adduct.map(ADDUCTS)))
        lo, hi = np.searchsorted(masses, [neutral*(1-a.ppm*1e-6), neutral*(1+a.ppm*1e-6)])
        cand = cat.iloc[lo:hi]
        truth = mols.inchikey14[q]
        rank, n = None, len(cand)
        if n:
            spectra = [dict(mzs=r.ms2_mzs, intensities=r.ms2_normalized_intensities, precursor_mz=r.precursor_mz,
                            adduct=r.adduct, ionization_mode=r.ionization_mode, collision_energy=None) for r in g.itertuples()]
            s = scorer.score_candidates(spectra, list(cand.smiles))
            order = np.argsort(-s, kind='stable')
            keys = cand.key.to_numpy()[order]
            hit = np.where(keys == truth)[0]
            rank = int(hit[0]) + 1 if len(hit) else None
            if a.all_scores:
                everything.append(pd.DataFrame(dict(molecule_id=q, key=cand.key.to_numpy(), score=s)))
            top = order[:50]
            lists += [dict(molecule_id=q, jm_rank=r+1, key=cand.key.iat[j], smiles=cand.smiles.iat[j], score=float(s[j]), src=cand.src.iat[j])
                      for r, j in enumerate(top) if np.isfinite(s[j])]
        rows.append(dict(molecule_id=q, type=int(mols.type[q]), n_candidates=n, truth_in_window=bool((cand.key == truth).any()),
                         jm_rank=rank))
        if (k+1) % 100 == 0:
            print(k+1, 'molecules', flush=True)
    d = pd.DataFrame(rows)
    d.to_parquet(a.out, index=False)
    if a.all_scores:
        pd.concat(everything, ignore_index=True).to_parquet(a.all_scores, index=False)
    pd.DataFrame(lists).to_parquet(a.out.with_name(a.out.stem.replace('retrieval', 'retrieval_lists') + '.parquet'), index=False)
    for t, g in d.groupby('type'):
        print(f'type {t}: n={len(g)} truth in 10ppm window={int(g.truth_in_window.sum())} median candidates={g.n_candidates.median():.0f}',
              ' '.join(f'R@{k}={int((g.jm_rank <= k).sum())}' for k in (1, 5, 25, 100)))


if __name__ == '__main__':
    main()
