"""Derive atlas training shards by removing canonical identities with provenance.

Pass the full competition identity table to obtain strictly external positives,
or pass held-out identity lists for a specific experiment. Originals are retained.
"""
import argparse
import json
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from casmi26.atlas import read_exclusions, sha256  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--src', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--exclude-identities', type=Path, nargs='+', required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    if a.out.resolve() == a.src.resolve():
        p.error('Use a separate output directory')
    keys, provenance = read_exclusions(a.exclude_identities)
    excluded = pa.array(sorted(keys), type=pa.string())
    a.out.mkdir(parents=True, exist_ok=True)
    records, identities, removed = [], set(), set()
    total = 0
    for manifest in sorted(a.src.glob('*.manifest.json')):
        info = json.loads(manifest.read_text())
        parent = manifest.with_name(manifest.name.removesuffix('.manifest.json') + '.parquet')
        if sha256(parent) != info['output_sha256']:
            raise ValueError(f'{parent}: hash mismatch')
        target = a.out / parent.name
        target_manifest = a.out / manifest.name
        if target.exists() or target_manifest.exists():
            raise ValueError(f'{target}: output already exists; use a new directory')
        table = pq.read_table(parent)
        keep = pc.invert(pc.is_in(table['inchikey14'], value_set=excluded))
        filtered = table.filter(keep)
        kept_keys = set(filtered['inchikey14'].to_pylist())
        dropped_keys = set(table['inchikey14'].to_pylist()) - kept_keys
        identities.update(kept_keys)
        removed.update(dropped_keys)
        total += len(filtered)
        temporary = target.with_suffix('.parquet.tmp')
        pq.write_table(filtered, temporary, compression='zstd')
        temporary.replace(target)
        record = dict(info)
        record.update(output=str(target.resolve()), output_sha256=sha256(target),
                      output_bytes=target.stat().st_size, cache_hit=False,
                      parent_shard=dict(path=str(parent.resolve()), sha256=info['output_sha256']),
                      parent_manifest_sha256=sha256(manifest), exclusions=provenance)
        record['recipe'] = dict(info['recipe'], filter_script_sha256=sha256(Path(__file__)),
                                filter_exclusions=provenance)
        record['counts'] = dict(info['counts'], written_spectra=len(filtered),
                               written_structures=len(kept_keys),
                               filtered_identity_spectra=len(table)-len(filtered),
                               filtered_identities=len(dropped_keys))
        target_manifest.write_text(json.dumps(record, indent=2)+'\n')
        records.append(dict(path=str(target.resolve()), sha256=record['output_sha256']))
    if not records:
        raise ValueError('No input shard manifests')
    result = dict(spectra=total, identities=len(identities), removed_identities=len(removed),
                  exclusions=provenance, shards=records, command=sys.argv)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'shards'}, indent=2))


if __name__ == '__main__':
    main()
