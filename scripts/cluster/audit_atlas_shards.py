"""Verify atlas shard contracts and measure same-formula competition overlap.

The overlap scan normalizes the actual competition SMILES, not its raw InChIKeys.
The formula filter keeps this audit small; it assumes correct train formula labels.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from casmi26.atlas import sha256, read_exclusions  # noqa: E402
from casmi26.chemistry import canonical_inchikey14  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--src', type=Path, required=True)
    p.add_argument('--train', type=Path)
    p.add_argument('--exclude-identities', type=Path, nargs='*', default=[])
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location('jm_features', ROOT / 'kaggle/jm_scorer/upstream/features.py')
    features = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(features)
    keys, formulas, pairs, sources, bad = set(), set(), set(), [], []
    total, min_peaks, max_peaks = 0, float('inf'), 0
    exclusions, provenance = read_exclusions(a.exclude_identities)
    for manifest in sorted(a.src.glob('*.manifest.json')):
        info = json.loads(manifest.read_text())
        path = manifest.with_name(manifest.name.removesuffix('.manifest.json') + '.parquet')
        if sha256(path) != info['output_sha256']:
            raise ValueError(f'{path}: hash mismatch')
        source = Path(info['input'])
        if sha256(source) != info['recipe']['source_sha256']:
            raise ValueError(f'{source}: source hash mismatch')
        frame = pq.read_table(path).to_pylist()
        if len(frame) != info['counts']['written_spectra']:
            raise ValueError(f'{path}: row count mismatch')
        for row in frame:
            key = row['inchikey14']
            if canonical_inchikey14(row['normalized_smiles']) != key:
                bad.append(dict(spectrum_id=row['spectrum_id'], reason='identity mismatch'))
            if key in exclusions:
                bad.append(dict(spectrum_id=row['spectrum_id'], reason='excluded identity'))
            pair = (key, row['adduct'], row['collision_energy_ev'])
            if pair in pairs:
                bad.append(dict(spectrum_id=row['spectrum_id'], reason='duplicate acquisition'))
            pairs.add(pair)
            pk, length = features.peaks(row['ms2_mzs'], row['ms2_normalized_intensities'], row['precursor_mz'])
            meta, adduct = features.metadata(row['precursor_mz'], row['adduct'], row['ionization_mode'], row['collision_energy_ev'])
            if not np.isfinite(pk).all() or not np.isfinite(meta).all() or adduct != 1 or length < 3:
                bad.append(dict(spectrum_id=row['spectrum_id'], reason='invalid JM model features'))
            if not row['is_simulated'] or row['ingest_lib'] != 'iceberg_atlas':
                bad.append(dict(spectrum_id=row['spectrum_id'], reason='incorrect provenance'))
            min_peaks, max_peaks = min(min_peaks, length), max(max_peaks, length)
            keys.add(key)
            formulas.add(row['formula'])
        total += len(frame)
        sources.append(dict(path=str(path), sha256=info['output_sha256']))
    if not total:
        raise ValueError('No atlas spectra to audit')
    result = dict(spectra=total, identities=len(keys), formulas=len(formulas), shards=sources,
                  min_model_peaks=min_peaks, max_model_peaks=max_peaks, errors=bad,
                  feature_source_sha256=sha256(ROOT / 'kaggle/jm_scorer/upstream/features.py'),
                  excluded_identities=len(exclusions), exclusion_sources=provenance)
    if a.train:
        table = ds.dataset(a.train, format='parquet').to_table(
            columns=['normalized_smiles'], filter=ds.field('molecular_formula').isin(sorted(formulas)))
        smiles = set(table.column(0).to_pylist())
        train_keys = {canonical_inchikey14(s) for s in smiles} - {None}
        result['competition_overlap'] = dict(train=str(a.train), matching_formula_rows=len(table),
                                             matching_formula_identities=len(train_keys),
                                             atlas_in_train=len(keys & train_keys),
                                             atlas_outside_train=len(keys - train_keys),
                                             assumption='Competition molecular_formula labels are correct; identity recomputed from SMILES.')
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.with_suffix('.outside_train.txt').write_text('\n'.join(sorted(keys - train_keys)) + '\n')
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'shards'}, indent=2))
    if bad:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
