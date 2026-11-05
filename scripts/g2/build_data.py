"""G2 data: structures for the formula + fingerprint -> SMILES decoder.

Source: pipeline pool (pool_meta.parquet: train structures + COCONUT, key = official metric identity). Kept: elements in
ELEMENTS, 150-1200 Da, <= MAX_TOK tokens. Excluded: every bench truth (K6 all 1186 metric truths, K7 v2 truths, T1 np250
identities), so the benches stay clean for generation. Each row: smiles (no stereo, canonical), key, element counts,
Morgan r2 2048 bits (same generator as the sanpier kit's features.structure), packed.
Usage: build_data.py --out artifacts/G2/data_v1
"""
import argparse
import glob
import json
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

MAIN = Path('/home/mpernigotto/jojo_molecular')
POOL = MAIN/'data/fastweb/casmi26-attributed-v4g-reproduction-assets-v6/casmi26-v2-pool/pool_meta.parquet'
ELEMENTS = ['C', 'H', 'N', 'O', 'S', 'P', 'F', 'Cl', 'Br', 'I', 'Si', 'B', 'Se']
TOKEN_RE = re.compile(r'(\[[^\]]+]|Br|Cl|Si|Se|B|C|N|O|S|P|F|I|b|c|n|o|s|p|se|\(|\)|\.|=|#|-|\+|\\|/|:|~|@|\?|>|\*|\$|%[0-9]{2}|[0-9])')
MAX_TOK = 160


def tokenize(s):
    toks = TOKEN_RE.findall(s)
    return toks if ''.join(toks) == s else None


def one(smiles):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdFingerprintGenerator, rdMolDescriptors
    RDLogger.DisableLog('rdApp.*')
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        Chem.RemoveStereochemistry(mol)
        s = Chem.MolToSmiles(mol, isomericSmiles=False)
        t = tokenize(s)
        if t is None or len(t) > MAX_TOK:
            return None
        mh = Chem.AddHs(mol)
        cnt = {}
        for a in mh.GetAtoms():
            cnt[a.GetSymbol()] = cnt.get(a.GetSymbol(), 0) + 1
        if any(k not in ELEMENTS for k in cnt) or Chem.GetFormalCharge(mol) != 0:
            return None
        mass = rdMolDescriptors.CalcExactMolWt(mol)
        if not 150 <= mass <= 1200:
            return None
        fp = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048).GetFingerprintAsNumPy(mol)
        return s, [cnt.get(e, 0) for e in ELEMENTS], np.packbits(fp.astype(np.uint8)), mass
    except Exception:
        return None


def bench_keys():
    keys = set()
    k6 = pd.read_parquet(MAIN/'artifacts/K6/unseen_v1/molecules_metric.parquet')
    keys |= set(k6.truth_metric.dropna())
    for c in ['inchikey14', 'truth', 'truth_key']:
        if c in k6:
            keys |= set(k6[c].dropna())
    for r in glob.glob(str(MAIN/'artifacts/k2_replay/r_k7v2_s?')):
        info = json.loads(Path(r, 'k2_run_info.json').read_text())
        keys |= set(json.loads(Path(info['contract']).read_text())['truth'].values())
    t1 = pd.read_parquet(MAIN/'artifacts/K6/type1_np250_v1/molecules.parquet')
    keys |= set(t1.inchikey14.dropna())
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(MAIN/'artifacts/G2/data_v1'))
    ap.add_argument('--workers', type=int, default=24)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pm = pd.read_parquet(POOL, columns=['key', 'smiles', 'train_sid', 'np_likeness'])
    excl = bench_keys()
    pm = pm[~pm.key.isin(excl)].drop_duplicates('key')
    print('pool', len(pm), 'excluded bench keys', len(excl), flush=True)
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(one, pm.smiles.tolist(), chunksize=512))
    ok = [i for i, r in enumerate(res) if r is not None]
    d = pd.DataFrame(dict(key=pm.key.to_numpy()[ok], smiles=[res[i][0] for i in ok], mass=[res[i][3] for i in ok],
                          in_train=(pm.train_sid.to_numpy()[ok] >= 0)))
    counts = np.array([res[i][1] for i in ok], np.int16)
    fps = np.stack([res[i][2] for i in ok])
    rng = np.random.default_rng(0)
    d['split'] = np.where(rng.random(len(d)) < 0.01, 'val', 'train')
    d.to_parquet(out/'structures.parquet', index=False)
    np.save(out/'counts.npy', counts)
    np.save(out/'fp_packed.npy', fps)
    vocab = sorted({t for s in d.smiles for t in tokenize(s)})
    (out/'meta.json').write_text(json.dumps(dict(elements=ELEMENTS, vocab=vocab, n=len(d), max_tok=MAX_TOK,
                                                 excluded_bench_keys=len(excl)), indent=1))
    print('kept', len(d), 'vocab', len(vocab), flush=True)


if __name__ == '__main__':
    main()
