"""Separate absence in downloaded atlas files from losses in a sampled training pool."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from casmi26.atlas import iter_mgf, normalize_structure, sha256  # noqa: E402
from casmi26.chemistry import canonical_inchikey14  # noqa: E402


def inspect(task):
    formula, path, truth_keys, sampled = task
    normalized, available, unstable = {}, set(), set()
    for _, header, _ in iter_mgf(path, headers_only=True):
        if header.get('ADDUCT') != '[M+H]+' or header.get('FORMULA') != formula:
            continue
        smiles = header.get('SMILES', '')
        if smiles not in normalized:
            normalized[smiles] = normalize_structure(smiles)
        key, canonical, computed_formula = normalized[smiles]
        if not key or computed_formula != formula:
            continue
        available.add(key)
        if key in truth_keys and canonical_inchikey14(canonical) != key:
            unstable.add(key)
    rows = []
    for key in sorted(truth_keys):
        status = ('sampled_pool' if key in sampled else
                  'normalization_not_idempotent' if key in unstable else
                  'available_in_raw_but_missing_from_sample' if key in available else
                  'absent_from_downloaded_formula_file')
        rows.append(dict(key=key, formula=formula, status=status,
                         sampled_candidates=len(sampled), raw_candidates=len(available)))
    return dict(formula=formula, path=str(path), sha256=sha256(path), raw_candidates=len(available), rows=rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--benchmark', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--workers', type=int, default=2)
    a = p.parse_args()
    manifest = json.loads((a.benchmark / 'manifest.json').read_text())
    query = pd.read_parquet(a.benchmark / 'queries.parquet', columns=['key','formula']).drop_duplicates()
    tasks = []
    for shard in manifest['atlas_shards']:
        path = Path(shard['path'])
        if sha256(path) != shard['sha256']:
            raise ValueError('Sampled atlas changed since the benchmark')
        info = json.loads(path.with_suffix('.manifest.json').read_text())
        formula = path.stem
        raw = Path(info['input'])
        if sha256(raw) != info['recipe']['source_sha256']:
            raise ValueError('Raw atlas changed since conversion')
        truth = set(query.loc[query.formula.eq(formula), 'key'])
        if truth:
            sampled = set(pd.read_parquet(path, columns=['inchikey14']).inchikey14)
            tasks.append((formula, raw, truth, sampled))
    a.out.mkdir(parents=True, exist_ok=True)
    results = []
    with ProcessPoolExecutor(a.workers) as pool:
        for result in pool.map(inspect, tasks):
            results.append(result)
            print(json.dumps(dict(formula=result['formula'], done=len(results), total=len(tasks))), flush=True)
    rows = pd.DataFrame([row for result in results for row in result.pop('rows')])
    rows.to_csv(a.out / 'coverage_by_molecule.csv', index=False)
    summary = dict(queries=len(rows), counts=rows.status.value_counts().to_dict(),
                   sampled_recall=float(rows.status.eq('sampled_pool').mean()),
                   raw_recall=float(rows.status.ne('absent_from_downloaded_formula_file').mean()),
                   sources=results, query_sha256=sha256(a.benchmark / 'queries.parquet'),
                   script_sha256=sha256(Path(__file__)), command=sys.argv,
                   limitation='Raw presence checks structure identity, not useful predicted peaks. No truth was added to the benchmark pool.')
    (a.out / 'coverage.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='sources'}, indent=2))


if __name__ == '__main__':
    main()
