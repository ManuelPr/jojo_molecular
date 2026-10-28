"""Parallel JM cache: run sanpier's prepare.py unchanged on row slices, then merge the slice caches.

Each input is PATH[:SOURCE]; SOURCE 0 marks competition spectra (validation/real), >0 external
(e.g. simulated atlas spectra). Directories expand to their *.parquet files. Duplicate model inputs
are removed within a slice (as upstream); identical spectra split across slices may both remain.
"""
import argparse
import json
from multiprocessing import Pool
import os
from pathlib import Path
import shutil
import sys
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'kaggle/jm_scorer/upstream'))
import prepare as upstream  # noqa: E402
from features import structure  # noqa: E402

TABLE = {}


def safe_structure(args):
    smiles, nbits = args
    try:
        return smiles, structure(smiles, nbits)
    except (ValueError, RuntimeError):
        return smiles, None


def cached(s, nbits):
    value = TABLE[s] if s in TABLE else safe_structure((s, nbits))[1]
    if value is None:
        raise ValueError('Invalid structure')
    return value


def provenance_batches(path):
    for b in pq.ParquetFile(path).iter_batches(batch_size=8192):
        frame = b.to_pandas()
        yield frame.assign(molecule_id=frame['ingest_lib'], spectrum_id=frame['instrument_type'])


def run_slice(args):
    cfg, path, work = args
    upstream.structure = cached
    upstream.batches = provenance_batches
    if 'normalized_smiles' not in upstream.ALIASES['smiles']:
        upstream.ALIASES['smiles'].append('normalized_smiles')
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        upstream.prepare({**cfg, 'work': work, 'train_path': path, 'external_paths': [], 'val_fraction': 0.5})
    return work


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs', nargs='+', help='PATH[:SOURCE]')
    p.add_argument('--config', default=str(ROOT/'kaggle/jm_scorer/configs/sanpier_v1.json'))
    p.add_argument('--work', required=True)
    p.add_argument('--rows-per-slice', type=int, default=40000)
    p.add_argument('--workers', type=int, default=os.cpu_count())
    a = p.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    work = Path(a.work)
    tmp = work/'_slices'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    started = time.monotonic()
    inputs = []
    for item in a.inputs:
        path, _, source = item.partition(':')
        path = Path(path)
        for f in (sorted(path.glob('*.parquet')) if path.is_dir() else [path]):
            inputs.append((f, int(source or 0)))
    columns = ['normalized_smiles', 'ms2_mzs', 'ms2_normalized_intensities', 'precursor_mz', 'adduct',
               'ionization_mode', 'collision_energy_ev', 'ingest_lib', 'instrument_type']
    import pyarrow as pa
    slices, smiles = [], set()
    for source in sorted({s for _, s in inputs}):
        # One table per source, so no slice is a tiny file tail (prepare.py needs >=20 identities).
        table = pa.concat_tables([pq.read_table(f, columns=columns) for f, s in inputs if s == source], promote_options='permissive')
        smiles.update(table.column('normalized_smiles').to_pylist())
        n = max(1, round(table.num_rows/a.rows_per_slice))
        step = -(-table.num_rows//n)
        for start in range(0, table.num_rows, step):
            out = tmp/f'slice{len(slices):05d}.parquet'
            pq.write_table(table.slice(start, step), out)
            slices.append((out, source))
    print('slices', len(slices), 'unique smiles', len(smiles), round(time.monotonic()-started), 's', flush=True)
    with Pool(a.workers) as pool:
        TABLE.update(pool.imap_unordered(safe_structure, [(s, cfg['fp_bits']) for s in sorted(smiles)], chunksize=256))
    print('structures', len(TABLE), round(time.monotonic()-started), 's', flush=True)
    # Workers fork after TABLE is filled, so the structure cache is shared copy-on-write.
    with Pool(a.workers) as pool:
        works = pool.map(run_slice, [(cfg, str(f), str(tmp/f'w{i:05d}')) for i, (f, _) in enumerate(slices)])
    print('slices prepared', round(time.monotonic()-started), 's', flush=True)
    molecules, specs = {}, []
    with open(work/'peaks.bin', 'wb') as px, open(work/'metadata.bin', 'wb') as mx:
        for (f, source), w in zip(slices, works):
            w = Path(w)
            mol = pd.read_parquet(w/'molecules.parquet')
            fps = np.load(w/'fingerprints.npy')
            for k, s, fo, ma, fp in zip(mol.key, mol.smiles, mol.formula, mol.mass, fps):
                molecules.setdefault(k, (s, fo, ma, fp))
            spec = pd.read_parquet(w/'spectra.parquet')
            spec['source'] = source
            specs.append(spec.drop(columns=['mol_idx', 'split']))
            with open(w/'peaks.bin', 'rb') as h:
                shutil.copyfileobj(h, px)
            with open(w/'metadata.bin', 'rb') as h:
                shutil.copyfileobj(h, mx)
    keys = sorted(molecules)
    lookup = {k: i for i, k in enumerate(keys)}
    mol = pd.DataFrame([(k, *molecules[k][:3]) for k in keys], columns=['key', 'smiles', 'formula', 'mass'])
    mol['split'] = 'train'
    np.save(work/'fingerprints.npy', np.stack([molecules[k][3] for k in keys]).astype(np.uint8))
    spec = pd.concat(specs, ignore_index=True)
    spec['mol_idx'] = spec.key.map(lookup)
    spec['split'] = 'train'
    mol.to_parquet(work/'molecules.parquet', index=False)
    spec.to_parquet(work/'spectra.parquet', index=False)
    report = dict(inputs=[(str(f), s) for f, s in inputs], slices=len(slices), spectra=len(spec), molecules=len(mol),
                  spectra_by_source=spec.source.value_counts().to_dict(), seconds=time.monotonic()-started)
    (work/'data_audit.json').write_text(json.dumps(report, indent=2, default=str))
    shutil.rmtree(tmp)
    print(json.dumps(report, default=str), flush=True)


if __name__ == '__main__':
    main()
