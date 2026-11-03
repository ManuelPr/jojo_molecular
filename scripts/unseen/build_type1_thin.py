"""T1-thin: T1 (build_type1_cohort.py) with the truth structures' remaining library spectra thinned to at most K per
molecule (seeded), the "thin class-1" situation of discussion 752356 where ungated wide generation lost 6.7% of correct
leaders. T1 keeps a median of 168 library spectra per truth, which makes its rank 1 too robust to show that failure.
Limitation: only competition-train reference rows are thinned; bundled external reference spectra are left as they are.

Usage: build_type1_thin.py [K]   (default 2) -> artifacts/K6/type1_thin_k<K>/, data/fastweb/k2_input_t1thin_k<K>/
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get('CASMI_ROOT', Path(__file__).resolve().parents[2]))  # main checkout holds data/artifacts
SLUG = 'enveda-CASMI26-molecule-id-mass-spectra'
T1 = ROOT/'artifacts/K6/type1_np250_v1/competition'


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    out = ROOT/f'artifacts/K6/type1_thin_k{k}'
    contract = json.loads((T1/'contract.json').read_text())
    keys = set(contract['truth'].values())
    ref = pd.read_parquet(T1/'train.parquet')
    is_truth = ref.inchikey14.isin(keys).to_numpy()
    rng = np.random.default_rng(0)
    keep = np.ones(len(ref), bool)
    for key, idx in ref.index[is_truth].to_series().groupby(ref.inchikey14[is_truth]).groups.items():
        idx = np.asarray(list(idx))
        if len(idx) > k:
            keep[ref.index.get_indexer(rng.choice(idx, len(idx)-k, replace=False))] = False
    thin = ref[keep]
    comp = out/'competition'
    comp.mkdir(parents=True, exist_ok=True)
    thin.to_parquet(comp/'train.parquet', index=False)
    for f in ['test.parquet', 'sample_submission.csv']:
        if not (comp/f).exists():
            (comp/f).symlink_to((T1/f).resolve())
    left = thin[thin.inchikey14.isin(keys)].groupby('inchikey14').size()
    contract.update(removed_reference_rows=int(contract['removed_reference_rows'] + (~keep).sum()),
                    validation=f'T1-thin: T1 with at most {k} remaining library spectra per truth (seed 0)',
                    reference_spectra_per_molecule=dict(min=int(left.min()), median=float(left.median()), max=int(left.max())))
    (comp/'contract.json').write_text(json.dumps(contract, indent=1))
    inp = ROOT/f'data/fastweb/k2_input_t1thin_k{k}'
    cdir = inp/'competitions'/SLUG
    cdir.mkdir(parents=True, exist_ok=True)
    for f in ['contract.json', 'sample_submission.csv', 'test.parquet', 'train.parquet']:
        if not (cdir/f).exists():
            (cdir/f).symlink_to((comp/f).resolve())
    src = ROOT/'data/fastweb/k2_input_t1_np250/datasets'
    if not (inp/'datasets').exists():
        (inp/'datasets').symlink_to(src.resolve())
    print(json.dumps({x: v for x, v in contract.items() if x != 'truth'}, indent=1), 'removed', int((~keep).sum()))


if __name__ == '__main__':
    main()
