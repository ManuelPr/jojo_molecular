"""Build the JM scorer training cache with sanpier's prepare.py, structures precomputed in parallel."""
import argparse
import json
from multiprocessing import Pool
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'kaggle/jm_scorer/upstream'))
import prepare as upstream  # noqa: E402
from features import structure  # noqa: E402


def safe_structure(args):
    smiles, nbits = args
    try:
        return smiles, structure(smiles, nbits)
    except (ValueError, RuntimeError):
        return smiles, None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', default=str(ROOT/'kaggle/jm_scorer/configs/sanpier_v1.json'))
    p.add_argument('--train', default=str(ROOT/'data/fastweb/competition/train.parquet'))
    p.add_argument('--work', default=str(ROOT/'data/fastweb/jm_cache_v1'))
    p.add_argument('--workers', type=int, default=os.cpu_count())
    p.add_argument('--external', nargs='*', default=[], help='extra train-like parquet files or directories (e.g. atlas shards)')
    a = p.parse_args()
    import pyarrow.parquet as pq
    cfg = json.loads(Path(a.config).read_text())
    external = []
    for e in a.external:
        e = Path(e)
        external += sorted(map(str, e.glob('*.parquet'))) if e.is_dir() else [str(e)]
    cfg.update(work=a.work, train_path=a.train, external_paths=external)
    started = time.monotonic()
    smiles = set()
    for path in [a.train]+external:
        smiles.update(pq.read_table(path, columns=['normalized_smiles']).column(0).to_pylist())
    smiles = sorted(smiles)
    print('unique smiles', len(smiles), flush=True)
    with Pool(a.workers) as pool:
        table = dict(pool.imap_unordered(safe_structure, [(s, cfg['fp_bits']) for s in smiles], chunksize=256))
    print('structures done', round(time.monotonic()-started), 's', flush=True)

    def cached(s, nbits):
        value = table[s] if s in table else safe_structure((s, nbits))[1]
        if value is None:
            raise ValueError('Invalid structure')
        return value
    upstream.structure = cached
    if 'normalized_smiles' not in upstream.ALIASES['smiles']:
        upstream.ALIASES['smiles'].append('normalized_smiles')
    batches = upstream.batches

    def provenance_batches(path):
        # prepare.py records molecule_id/spectrum_id per row; carry library and instrument there instead.
        for frame in batches(path):
            yield frame.assign(molecule_id=frame['ingest_lib'], spectrum_id=frame['instrument_type'])
    upstream.batches = provenance_batches
    report = upstream.prepare(cfg)
    report['prepare_seconds'] = time.monotonic()-started
    (Path(a.work)/'jm_prepare_config.json').write_text(json.dumps(cfg, indent=2))
    print('done', round(report['prepare_seconds']), 's', flush=True)


if __name__ == '__main__':
    main()
