"""K6 bake-off contender: the five fold-safe FPNet models (logits averaged; none has seen a K6 molecule) ranking the same
local-catalog candidates within 10 ppm as jm_retrieval.py. Query preprocessing follows the dataset's eval_ckpt.py: spectra of
one polarity (the majority one) merged, up to 8, collision energy unknown. Candidate fingerprints: casmi.chem.raw_fingerprint
restricted to the models' fp_bits.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT/'data/fastweb/casmi26-attributed-v4g-reproduction-assets-v6/casmi26-v3-models/code'
FOLD_SAFE = ROOT/'data/fastweb/casmi26-fold-safe-fpnet-v5'


def fpnet_query_vector(g, models):
    """Averaged FPNet logits for one molecule (g: its test rows): majority polarity, up to 8 spectra merged, CE unknown."""
    import numpy as np
    import torch
    from casmi import chem, fpnet
    from casmi.spectra import merge_spectra
    mode = g.ionization_mode.value_counts().index[0]
    sub = g[g.ionization_mode == mode].head(8)
    if len(sub) == 1:
        mz, it = np.asarray(sub.ms2_mzs.iat[0], float), np.asarray(sub.ms2_normalized_intensities.iat[0], float)
    else:
        mz, it = merge_spectra([(np.asarray(r.ms2_mzs, float), np.asarray(r.ms2_normalized_intensities, float))
                                for r in sub.itertuples()])
    prec = float(sub.precursor_mz.iat[0])
    pm, pi = fpnet.prep_peaks(mz, it, prec)
    item = dict(mz=pm, it=pi, prec=prec, adduct_ix=int(chem.adduct_index(sub.adduct.iat[0])), ce=0.0, ce_known=0.0,
                n_merged=min(len(sub), 8), mode=1.0 if mode == 'positive' else -1.0)
    with torch.no_grad(), torch.autocast('cuda', dtype=fpnet.autocast_dtype('cuda')):
        return torch.stack([m(*fpnet.collate([item], 'cuda'))[0].float() for m in models]).mean(0)[0].cpu().numpy()


def fpnet_scores(g, smiles, models, bits, fp_cache):
    """FPNet score of each candidate SMILES for one molecule (g: its test rows); -inf when no fingerprint."""
    import numpy as np
    from casmi import chem
    z = fpnet_query_vector(g, models)
    out = np.full(len(smiles), -np.inf)
    for i, s in enumerate(smiles):
        if s not in fp_cache:
            v = chem.raw_fingerprint(s)
            fp_cache[s] = None if v is None else v[bits].astype(np.float32)
        if fp_cache[s] is not None:
            out[i] = float(fp_cache[s] @ z)
    return out

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    p.add_argument('--ppm', type=float, default=10.0)
    p.add_argument('--out', type=Path, default=ROOT/'artifacts/K6/bakeoff/fpnet5.parquet')
    p.add_argument('--all-scores', type=Path, default=ROOT/'artifacts/K6/bakeoff/fpnet5_scores.parquet')
    a = p.parse_args()
    sys.path.insert(0, str(CODE))
    sys.path.insert(0, str(ROOT/'scripts/unseen'))
    import torch
    from casmi import chem, fpnet
    from casmi.spectra import merge_spectra
    from jm_retrieval import ADDUCTS, catalog
    bits = np.load(FOLD_SAFE/'fp_bits.npy')
    models = [fpnet.load_model(str(FOLD_SAFE/f'fpnet_fold{k}.pt'), 'cuda') for k in range(5)]
    assert all(m.nbits == len(bits) for m in models)
    dtype = fpnet.autocast_dtype('cuda')
    cat = catalog()
    masses = cat.mass.to_numpy()
    mols = pd.read_parquet(a.cohort/'molecules.parquet').set_index('molecule_id')
    test = pd.read_parquet(a.cohort/'competition/test.parquet')
    fp_cache = {}

    rows, everything = [], []
    for k, (q, g) in enumerate(test.groupby('molecule_id', sort=True)):
        neutral = float(np.median(g.precursor_mz - g.adduct.map(ADDUCTS)))
        lo, hi = np.searchsorted(masses, [neutral*(1-a.ppm*1e-6), neutral*(1+a.ppm*1e-6)])
        cand = cat.iloc[lo:hi]
        truth = mols.inchikey14[q]
        rank = None
        if len(cand):
            s = fpnet_scores(g, list(cand.smiles), models, bits, fp_cache)
            order = np.argsort(-s, kind='stable')
            hit = np.where(cand.key.to_numpy()[order] == truth)[0]
            rank = int(hit[0]) + 1 if len(hit) else None
            everything.append(pd.DataFrame(dict(molecule_id=q, key=cand.key.to_numpy(), score=s)))
        rows.append(dict(molecule_id=q, type=int(mols.type[q]), n_candidates=len(cand), fp_rank=rank))
        if (k+1) % 100 == 0:
            print(k+1, 'molecules', flush=True)
    d = pd.DataFrame(rows)
    d.to_parquet(a.out, index=False)
    pd.concat(everything, ignore_index=True).to_parquet(a.all_scores, index=False)
    for t, g in d.groupby('type'):
        print(f'type {t}: n={len(g)}', ' '.join(f'R@{k}={int((g.fp_rank <= k).sum())}' for k in (1, 5, 25, 100)))


if __name__ == '__main__':
    main()
