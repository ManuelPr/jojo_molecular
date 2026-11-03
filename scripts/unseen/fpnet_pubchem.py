"""K6/T1: extend the FPNet dense channel to the PubChem tier (105.9 M structures, no precomputed fingerprints).

Phase 1 (CPU pool): per molecule, PubChem-tier SMILES within 10 ppm of the query neutral mass -> InChIKey14 and the
fold-safe fp_bits fingerprint (casmi.chem.raw_fingerprint), capped at --cap entries per window (closest in mass).
Phase 2 (GPU): fpnet_retrieval.fpnet_query_vector logits dotted with those fingerprints. Output rows
(molecule_id, key, smiles, score, src='pubchem'). channel_lists() builds the channel ranking used by the submission:
local and PubChem scores scaled by the molecule's local-score std, PubChem penalised by delta (1, chosen on K6 cal).
"""
import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'data/fastweb/casmi26-attributed-v4g-reproduction-assets-v6'
CODE = ROOT/'data/fastweb/casmi26-attributed-v4g-reproduction-assets-v6/casmi26-v3-models/code'
FOLD_SAFE = ROOT/'data/fastweb/casmi26-fold-safe-fpnet-v5'
ADDUCTS = {'[M+H]+': 1.007276, '[M-H]-': -1.007276, '[M+Na]+': 22.989218, '[M+NH4]+': 18.033823, '[M+K]+': 38.963158,
           '[M+Cl]-': 34.969402, '[M+CH2O2-H]-': 44.998201}
PC_DELTA, PC_CAP = 1.0, 20000


def window_features(job):
    """job: (molecule_id, neutral mass, ppm, cap, pc_dir, code_dir, bits_path) -> (molecule_id, keys, smiles, packed fps, n)."""
    q, mass, ppm, cap, pc_dir, code_dir, bits_path = job
    import sys
    from pathlib import Path
    import numpy as np
    if str(code_dir) not in sys.path:
        sys.path.insert(0, str(code_dir))
    from rdkit import Chem, RDLogger
    from casmi import chem
    RDLogger.DisableLog('rdApp.*')
    bits = np.load(bits_path)
    pm = np.load(Path(pc_dir)/'pubchem_tier__pc_mass.npy', mmap_mode='r')
    off = np.load(Path(pc_dir)/'pubchem_tier__pc_off.npy', mmap_mode='r')
    smi = np.load(Path(pc_dir)/'pubchem_tier__pc_smiles.npy', mmap_mode='r')
    lo, hi = np.searchsorted(pm, [mass*(1-ppm*1e-6), mass*(1+ppm*1e-6)])
    if hi - lo > cap:
        idx = np.argsort(np.abs(np.asarray(pm[lo:hi]) - mass), kind='stable')[:cap] + lo
    else:
        idx = np.arange(lo, hi)
    keys, smiles, fps = [], [], []
    for j in idx:
        s = bytes(smi[off[j]:off[j+1]]).decode()
        m = Chem.MolFromSmiles(s)
        if m is None:
            continue
        v = chem.raw_fingerprint(s)
        if v is None:
            continue
        keys.append(Chem.MolToInchiKey(m)[:14]); smiles.append(s); fps.append(np.packbits(v[bits]))
    return q, keys, smiles, (np.array(fps) if fps else np.zeros((0, (len(bits)+7)//8), np.uint8)), int(hi-lo)


def channel_lists(u, delta=PC_DELTA, top=50):
    """u: molecule_id, key, score, src ('local'/'pubchem'). Returns molecule_id -> top keys of the channel."""
    u = u[np.isfinite(u.score)]
    sd = u[u.src == 'local'].groupby('molecule_id').score.std().fillna(1).replace(0, 1)
    u = u.assign(z=u.score / u.molecule_id.map(sd).fillna(u.score.std()))
    v = u.assign(adj=u.z - np.where(u.src == 'pubchem', delta, 0)).sort_values('adj', ascending=False, kind='stable')
    v = v.drop_duplicates(['molecule_id', 'key'])
    return v.groupby('molecule_id').key.apply(lambda x: list(x[:top])).to_dict()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    p.add_argument('--ppm', type=float, default=10.0)
    p.add_argument('--cap', type=int, default=PC_CAP)
    p.add_argument('--workers', type=int, default=24)
    p.add_argument('--out', type=Path, default=ROOT/'artifacts/K6/fpnet5_pubchem_scores_k6.parquet')
    a = p.parse_args()
    test = pd.read_parquet(a.cohort/'competition/test.parquet')
    jobs = [(q, float(np.median(g.precursor_mz - g.adduct.map(ADDUCTS))), a.ppm, a.cap, ASSETS, CODE, FOLD_SAFE/'fp_bits.npy')
            for q, g in test.groupby('molecule_id')]
    feats, sizes = {}, {}
    with ProcessPoolExecutor(a.workers) as ex:
        for k, (q, keys, smiles, fps, n) in enumerate(ex.map(window_features, jobs, chunksize=4)):
            feats[q] = (keys, smiles, fps); sizes[q] = n
            if (k+1) % 100 == 0:
                print(k+1, 'windows', flush=True)
    print('window size median', np.median(list(sizes.values())), 'max', max(sizes.values()), flush=True)
    sys.path.insert(0, str(CODE)); sys.path.insert(0, str(ROOT/'scripts/unseen'))
    import torch
    from casmi import fpnet
    from fpnet_retrieval import fpnet_query_vector
    bits = np.load(FOLD_SAFE/'fp_bits.npy')
    models = [fpnet.load_model(str(FOLD_SAFE/f'fpnet_fold{k}.pt'), 'cuda') for k in range(5)]
    rows = []
    for q, g in test.groupby('molecule_id'):
        keys, smiles, fps = feats[q]
        if not keys:
            continue
        z = fpnet_query_vector(g, models)
        s = fpnet.unpack_gpu(torch.from_numpy(fps).cuda(), len(bits)).cpu().numpy() @ z
        rows.append(pd.DataFrame(dict(molecule_id=q, key=keys, smiles=smiles, score=s, src='pubchem')))
    pd.concat(rows, ignore_index=True).to_parquet(a.out, index=False)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
