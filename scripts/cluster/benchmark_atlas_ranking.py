"""Known-formula atlas diagnostic against public sanpier v1 on a fixed candidate pool.

This is NOT leak-free validation: sanpier v1 was refit on competition training.
No truth is injected into the atlas sample; absent identities contribute zero RR.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from casmi26.atlas import normalize_structure, sha256  # noqa: E402
from casmi26.atlas_ranking import prepare_spectrum, score_atlas, ranks, leader_safe_fusion, paired_bootstrap  # noqa: E402


MODEL_SHA = '44436b2daec64373e66f9120dd2389c24fc83dd9430ebeeac18e3cb49dcb9642'
METHODS = ['neural', 'atlas_max', 'atlas_nearest', 'neural_atlas_tail']


def load_scorer(bundle, threads):
    import torch
    torch.set_num_threads(threads)
    pins = json.loads((bundle / 'sha256.json').read_text())
    hashes = {}
    for name in ['final_model.pt', 'config.json', 'features.py', 'model.py', 'inference.py']:
        hashes[name] = sha256(bundle / name)
        if hashes[name] != pins[name]:
            raise ValueError(f'{name}: does not match upstream hash manifest')
    if hashes['final_model.pt'] != MODEL_SHA:
        raise ValueError('This experiment requires the fixed sanpier v1 model')
    sys.path.insert(0, str(bundle.resolve()))
    from inference import Scorer
    return Scorer(bundle, device='cpu'), hashes


def load_pool(root, args):
    pools, manifests = defaultdict(dict), []
    for path in sorted(root.glob('*.manifest.json')):
        info = json.loads(path.read_text())
        shard = path.with_name(path.name.removesuffix('.manifest.json') + '.parquet')
        if sha256(shard) != info['output_sha256']:
            raise ValueError(f'{shard}: checksum mismatch')
        manifests.append(dict(path=str(shard), sha256=info['output_sha256']))
        for row in pq.read_table(shard).to_pylist():
            if row['adduct'] != '[M+H]+':
                continue
            formula, key = row['formula'], row['inchikey14']
            item = pools[formula].setdefault(key, dict(smiles=row['normalized_smiles'], refs=[]))
            item['refs'].append(prepare_spectrum(row['ms2_mzs'], row['ms2_normalized_intensities'],
                                                row['precursor_mz'], row['collision_energy_ev'],
                                                max_peaks=args.max_peaks, precursor_window=args.precursor_window))
    if not pools:
        raise ValueError('No atlas candidates')
    return dict(pools), manifests


def load_queries(path, formulas, args):
    columns = ['normalized_smiles', 'molecular_formula', 'ingest_lib', 'instrument_type',
               'ms2_mzs', 'ms2_normalized_intensities', 'precursor_mz', 'adduct',
               'ionization_mode', 'collision_energy_ev']
    table = ds.dataset(path, format='parquet').to_table(columns=columns,
                    filter=ds.field('molecular_formula').isin(formulas))
    counts = Counter(input_rows=len(table))
    by_key = defaultdict(list)
    for row in table.to_pylist():
        if row['adduct'] != '[M+H]+' or row['ionization_mode'] != 'positive':
            counts['unsupported_adduct_or_polarity'] += 1
            continue
        key, _, formula = normalize_structure(row['normalized_smiles'])
        if not key or formula != row['molecular_formula']:
            counts['invalid_structure_or_formula'] += 1
            continue
        try:
            clean = prepare_spectrum(row['ms2_mzs'], row['ms2_normalized_intensities'],
                                     row['precursor_mz'], row['collision_energy_ev'],
                                     max_peaks=args.max_peaks, precursor_window=args.precursor_window)
        except (ValueError, TypeError):
            counts['invalid_spectrum'] += 1
            continue
        if len(clean.mz) < 3:
            counts['fewer_than_three_nonprecursor_peaks'] += 1
            continue
        # Digest excludes library/instrument so identical acquired evidence does not
        # get extra weight merely because multiple libraries redistribute it.
        payload = clean.mz.astype('<f8').tobytes() + clean.weight.astype('<f8').tobytes()
        payload += np.asarray([row['precursor_mz'], clean.energy_ev], dtype='<f8').tobytes()
        row.update(key=key, formula=formula, prepared=clean, digest=hashlib.sha256(payload).hexdigest())
        by_key[key].append(row)
    selected = {}
    for key, rows in by_key.items():
        # Where target-domain spectra exist, evaluate those acquisitions alone.
        np_rows = [r for r in rows if r['ingest_lib'] == 'enveda-np-examples']
        if np_rows:
            rows = np_rows
        unique = {}
        for row in sorted(rows, key=lambda r: (r['ingest_lib'], r['instrument_type'] or '', r['digest'])):
            unique.setdefault(row['digest'], row)
        counts['duplicate_query_rows'] += len(rows) - len(unique)
        groups = defaultdict(list)
        for row in unique.values():
            groups[(row['ingest_lib'], row['instrument_type'] or '')].append(row)
        for group in groups.values():
            group.sort(key=lambda r: hashlib.sha256(f'{args.seed}:{r["digest"]}'.encode()).digest())
        # Round-robin across acquisition sources rather than taking all from the
        # library with the most duplicate energies.
        chosen = []
        while len(chosen) < args.max_spectra and any(groups.values()):
            for group in groups.values():
                if group and len(chosen) < args.max_spectra:
                    chosen.append(group.pop(0))
        selected[key] = chosen
    return selected, dict(counts)


def summarize(frame, seed):
    result = {}
    for name, subset in [('all', frame), ('covered', frame[frame.covered]),
                         ('enveda_np', frame[frame.enveda_np]),
                         ('enveda_np_covered', frame[frame.enveda_np & frame.covered])]:
        result[name] = dict(molecules=len(subset), pool_recall=float(subset.covered.mean()) if len(subset) else None)
        if not len(subset):
            continue
        for method in METHODS:
            result[name][method] = dict(mrr25=float(subset['rr_' + method].mean()),
                                       hit1=float(subset['rank_' + method].eq(1).mean()),
                                       hit25=float(subset['rank_' + method].between(1, 25).mean()))
        result[name]['paired_tail_minus_neural'] = paired_bootstrap(
            subset.rr_neural_atlas_tail.values - subset.rr_neural.values, seed=seed)
        result[name]['paired_atlas_minus_neural'] = paired_bootstrap(
            subset.rr_atlas_max.values - subset.rr_neural.values, seed=seed)
        result[name]['atlas_rescues_neural_top1_errors'] = int((subset.rank_atlas_max.eq(1) & ~subset.rank_neural.eq(1)).sum())
        result[name]['neural_rescues_atlas_top1_errors'] = int((subset.rank_neural.eq(1) & ~subset.rank_atlas_max.eq(1)).sum())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--atlas', type=Path, default=ROOT / 'data/fastweb/iceberg_atlas/h_plus_parquet_v2')
    p.add_argument('--train', type=Path, default=ROOT / 'data/fastweb/competition/train.parquet')
    p.add_argument('--bundle', type=Path, default=ROOT / 'data/fastweb/sanpier-casmi-spectrum-model-v1/casmi_spectrum_model_v1')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--max-spectra', type=int, default=4)
    p.add_argument('--max-peaks', type=int, default=128)
    p.add_argument('--tolerance-da', type=float, default=.02)
    p.add_argument('--precursor-window', type=float, default=.5)
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--seed', type=int, default=20261028)
    p.add_argument('--limit-molecules', type=int)
    a = p.parse_args()
    if min(a.max_spectra, a.max_peaks, a.threads) < 1:
        p.error('Positive resource limits required')
    if a.out.exists() and any(a.out.iterdir()):
        p.error('Use a new output directory')
    a.out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    scorer, model_hashes = load_scorer(a.bundle, a.threads)
    pools, shard_hashes = load_pool(a.atlas, a)
    queries, query_counts = load_queries(a.train, sorted(pools), a)
    keys = sorted(queries)
    if a.limit_molecules:
        keys = keys[:a.limit_molecules]
    config = dict(command=sys.argv, model_hashes=model_hashes, atlas_shards=shard_hashes,
                  scorer_source_sha256=sha256(ROOT / 'src/casmi26/atlas_ranking.py'),
                  benchmark_sha256=sha256(Path(__file__)), config={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},
                  query_counts=query_counts, molecules=len(keys), started_utc=datetime.now(timezone.utc).isoformat(),
                  limitation='Known formula diagnostic on training identities. sanpier refit saw training; ICEBERG training overlap not established. Not H1, not a promotion criterion.')
    (a.out / 'manifest.json').write_text(json.dumps(config, indent=2)+'\n')
    selected_rows = []
    for key in keys:
        for r in queries[key]:
            selected_rows.append({k:v for k,v in r.items() if k != 'prepared'})
    pd.DataFrame(selected_rows).to_parquet(a.out / 'queries.parquet', index=False)
    summary_rows, evidence = [], []
    for n, key in enumerate(keys, 1):
        qs = queries[key]
        formula = qs[0]['formula']
        pool = pools[formula]
        candidate_keys = sorted(pool)
        atlas = score_atlas([q['prepared'] for q in qs], [pool[k]['refs'] for k in candidate_keys], tolerance_da=a.tolerance_da)
        records = [dict(mzs=q['ms2_mzs'], intensities=q['ms2_normalized_intensities'], precursor_mz=q['precursor_mz'],
                        adduct=q['adduct'], ionization_mode=q['ionization_mode'], collision_energy=q['collision_energy_ev']) for q in qs]
        neural = scorer.score_candidates(records, [pool[k]['smiles'] for k in candidate_keys])
        scores = dict(neural=neural, **atlas)
        scores['neural_atlas_tail'] = leader_safe_fusion(neural, atlas['atlas_max'], candidate_keys)
        rankings = {method:ranks(values,candidate_keys) for method,values in scores.items()}
        truth = candidate_keys.index(key) if key in pool else None
        row = dict(key=key, formula=formula, covered=truth is not None, candidates=len(pool), spectra=len(qs),
                   enveda_np=all(q['ingest_lib']=='enveda-np-examples' for q in qs),
                   sources=';'.join(sorted({q['ingest_lib'] for q in qs})),
                   atlas_nonzero_candidates=int((atlas['atlas_max']>0).sum()))
        for method in METHODS:
            rank = int(rankings[method][truth]) if truth is not None else 0
            row['rank_'+method] = rank
            row['rr_'+method] = 1./rank if 1 <= rank <= 25 else 0.
        summary_rows.append(row)
        for c, candidate_key in enumerate(candidate_keys):
            evidence.append(dict(query_key=key, candidate_key=candidate_key, formula=formula,
                                 is_truth=candidate_key==key,
                                 **{method:float(scores[method][c]) for method in METHODS},
                                 **{'rank_'+method:int(rankings[method][c]) for method in METHODS}))
        if n % 10 == 0 or n == len(keys):
            pd.DataFrame(summary_rows).to_csv(a.out / 'molecule_results.csv', index=False)
            print(json.dumps(dict(done=n, total=len(keys), seconds=round(time.monotonic()-started,1))), flush=True)
    frame = pd.DataFrame(summary_rows)
    if frame.empty:
        raise ValueError('No eligible query molecules')
    pd.DataFrame(evidence).to_parquet(a.out / 'candidate_evidence.parquet', index=False)
    result = summarize(frame, a.seed)
    result['runtime_seconds'] = time.monotonic()-started
    result['limitation'] = config['limitation']
    (a.out / 'results.json').write_text(json.dumps(result, indent=2)+'\n')
    config.update(finished_utc=datetime.now(timezone.utc).isoformat(), state='complete',
                  outputs={name:sha256(a.out/name) for name in ['queries.parquet','molecule_results.csv','candidate_evidence.parquet','results.json']})
    (a.out / 'manifest.json').write_text(json.dumps(config, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
