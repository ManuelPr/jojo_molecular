"""Key/formula/mass table of every train structure (scorer identity), computed in parallel."""
import argparse
from multiprocessing import Pool
import os
from pathlib import Path
import sys

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'kaggle/jm_scorer'))
from features import structure  # noqa: E402


def row(smiles):
    try:
        key, canonical, formula, mass, _ = structure(smiles, 64)
        return key, canonical, formula, mass
    except (ValueError, RuntimeError):
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--train', default=str(ROOT/'data/fastweb/competition/train.parquet'))
    p.add_argument('--out', default=str(ROOT/'data/fastweb/jm_cache_v1/train_molecules.parquet'))
    p.add_argument('--workers', type=int, default=os.cpu_count())
    a = p.parse_args()
    smiles = sorted(set(pq.read_table(a.train, columns=['normalized_smiles']).column(0).to_pylist()))
    with Pool(a.workers) as pool:
        rows = [r for r in pool.imap(row, smiles, chunksize=256) if r]
    frame = pd.DataFrame(rows, columns=['key', 'smiles', 'formula', 'mass']).drop_duplicates('key')
    frame.to_parquet(a.out, index=False)
    print('molecules', len(frame), 'formulas', frame.formula.nunique(), flush=True)


if __name__ == '__main__':
    main()
