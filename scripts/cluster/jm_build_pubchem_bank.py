"""Build same-formula PubChem negatives (structures absent from train) for every training formula."""
import argparse
from multiprocessing import Pool
import os
from pathlib import Path
import sys
import time
import zlib

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'kaggle/jm_scorer'))
from features import structure  # noqa: E402

PRIOR = ROOT/'data/fastweb/casmi26-pubchem-popularity-prior-v10'
G = {}


def init(train_keys_path, top, rand, ppm, seed):
    G['mass'] = np.load(PRIOR/'casmi26-pubchem-tier/pc_mass.npy', mmap_mode='r')
    G['off'] = np.load(PRIOR/'casmi26-pubchem-tier/pc_off.npy', mmap_mode='r')
    G['smi'] = np.load(PRIOR/'casmi26-pubchem-tier/pc_smiles.npy', mmap_mode='r')
    G['doc'] = (np.load(PRIOR/'pc_lsid.npy', mmap_mode='r'), np.load(PRIOR/'pc_lpmid.npy', mmap_mode='r'))
    G['np'] = np.load(PRIOR/'pc_np.npy', mmap_mode='r')
    G['train'] = set(Path(train_keys_path).read_text().split())
    G.update(top=top, rand=rand, ppm=ppm, seed=seed)


def smiles_at(i):
    return bytes(G['smi'][G['off'][i]:G['off'][i+1]]).decode()


def same_formula(i, formula):
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors
    mol = Chem.MolFromSmiles(smiles_at(i))
    return mol is not None and rdMolDescriptors.CalcMolFormula(mol) == formula


def bank_for(args):
    formula, mass = args
    lo = int(np.searchsorted(G['mass'], mass*(1-G['ppm']*1e-6)))
    hi = int(np.searchsorted(G['mass'], mass*(1+G['ppm']*1e-6)))
    if hi <= lo:
        return formula, []
    rows = np.arange(lo, hi)
    doc = np.asarray(G['doc'][0][lo:hi], np.float32)+np.asarray(G['doc'][1][lo:hi], np.float32)
    rng = np.random.default_rng(zlib.crc32(f"{G['seed']}:{formula}".encode()))
    picked, seen, keys = [], set(), set()
    # Best-documented isomers first (what the pipeline's PubChem channel proposes), then random isomers.
    for order, quota, budget in ((rows[np.argsort(-doc, kind='stable')], G['top'], 400), (rng.permutation(rows), G['rand'], 400)):
        got = 0
        for i in order[:budget]:
            if got >= quota:
                break
            i = int(i)
            if i in seen or not same_formula(i, formula):
                continue
            seen.add(i)
            try:
                key, canonical, f2, _, fp = structure(smiles_at(i), 2048)
            except (ValueError, RuntimeError):
                continue
            if key in G['train'] or key in keys or f2 != formula:
                continue
            keys.add(key)
            picked.append((key, canonical, formula, float(doc[i-lo]), int(G['np'][i]), np.packbits(fp)))
            got += 1
    return formula, picked


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', default=str(ROOT/'data/fastweb/jm_cache_v1'))
    p.add_argument('--top', type=int, default=16)
    p.add_argument('--rand', type=int, default=16)
    p.add_argument('--ppm', type=float, default=5.)
    p.add_argument('--seed', type=int, default=20261028)
    p.add_argument('--workers', type=int, default=os.cpu_count())
    p.add_argument('--molecules', help='key/formula/mass table (default: WORK/molecules.parquet)')
    a = p.parse_args()
    work = Path(a.work)
    out = work/'pubchem_bank'
    lock = out/'BUILDING'
    owner = lock.read_text().split()[1] if lock.exists() else None
    if (out/'bank.parquet').exists() or (owner and owner != os.environ.get('SLURM_JOB_ID')):
        print('bank exists or is being built by job', owner, '- skipping', out, flush=True)
        return
    out.mkdir(parents=True, exist_ok=True)
    mol = pd.read_parquet(a.molecules or work/'molecules.parquet')
    (out/'train_keys.txt').write_text('\n'.join(mol.key))
    formulas = mol.groupby('formula', sort=True).mass.median()
    print('formulas', len(formulas), flush=True)
    started = time.monotonic()
    records = []
    with Pool(a.workers, initializer=init, initargs=(str(out/'train_keys.txt'), a.top, a.rand, a.ppm, a.seed)) as pool:
        for n, (formula, picked) in enumerate(pool.imap_unordered(bank_for, list(formulas.items()), chunksize=16), 1):
            records.extend(picked)
            if n % 5000 == 0:
                print(n, 'formulas', len(records), 'negatives', round(time.monotonic()-started), 's', flush=True)
    frame = pd.DataFrame([r[:5] for r in records], columns=['key', 'smiles', 'formula', 'doc', 'np'])
    keep = ~frame.duplicated(['formula', 'key'])
    frame = frame[keep].reset_index(drop=True)
    packed = np.stack([r[5] for r, k in zip(records, keep) if k])
    np.save(out/'bank_fp_packed.npy', packed)
    frame.to_parquet(out/'bank.parquet', index=False)
    lock.unlink(missing_ok=True)
    print('done', len(frame), 'negatives for', frame.formula.nunique(), 'formulas', round(time.monotonic()-started), 's', flush=True)


if __name__ == '__main__':
    main()
