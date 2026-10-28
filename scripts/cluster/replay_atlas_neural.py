"""Replay a locally trained JM scorer on frozen J5c queries, candidates and atlas scores."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'kaggle/jm_scorer')]
from casmi26.atlas import sha256  # noqa: E402
from casmi26.atlas_ranking import ranks, leader_safe_fusion  # noqa: E402
from inference import Scorer  # noqa: E402
from benchmark_atlas_ranking import METHODS, summarize  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--benchmark', type=Path, required=True)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--limit-molecules', type=int)
    p.add_argument('--expect-baseline-parity', action='store_true')
    a = p.parse_args()
    if a.out.exists() and any(a.out.iterdir()):
        p.error('Use a new output directory')
    a.out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    source = json.loads((a.benchmark / 'manifest.json').read_text())
    for name, digest in source['outputs'].items():
        if sha256(a.benchmark / name) != digest:
            raise ValueError(f'{name}: frozen benchmark changed')
    queries = pd.read_parquet(a.benchmark / 'queries.parquet')
    candidates = pd.read_parquet(a.benchmark / 'candidate_evidence.parquet')
    baseline = pd.read_csv(a.benchmark / 'molecule_results.csv')
    smiles = {}
    for shard in source['atlas_shards']:
        path = Path(shard['path'])
        if sha256(path) != shard['sha256']:
            raise ValueError('Atlas candidate structures changed')
        frame = pd.read_parquet(path, columns=['inchikey14','normalized_smiles']).drop_duplicates('inchikey14')
        smiles.update(zip(frame.inchikey14, frame.normalized_smiles))
    torch.set_num_threads(a.threads)
    scorer = Scorer(a.bundle, device='cpu')
    provenance = dict(command=sys.argv, base_manifest_sha256=sha256(a.benchmark / 'manifest.json'),
                      weights_sha256=sha256(a.bundle / 'final_model.pt'), config_sha256=sha256(a.bundle / 'config.json'),
                      sources={str(p):sha256(p) for p in [Path(__file__), ROOT/'kaggle/jm_scorer/inference.py',
                                ROOT/'kaggle/jm_scorer/model.py', ROOT/'kaggle/jm_scorer/features.py']},
                      started_utc=datetime.now(timezone.utc).isoformat(), limitation=source['limitation'])
    (a.out / 'manifest.json').write_text(json.dumps(provenance,indent=2)+'\n')
    summary, evidence, diffs = [], [], []
    keys = sorted(queries.key.unique())
    if a.limit_molecules:
        keys = keys[:a.limit_molecules]
    for n,key in enumerate(keys,1):
        q = queries[queries.key.eq(key)]
        c = candidates[candidates.query_key.eq(key)].sort_values('candidate_key').copy()
        ck = c.candidate_key.tolist()
        records = [dict(mzs=r['ms2_mzs'],intensities=r['ms2_normalized_intensities'],precursor_mz=r['precursor_mz'],
                        adduct=r['adduct'],ionization_mode=r['ionization_mode'],collision_energy=r['collision_energy_ev'])
                   for r in q.to_dict('records')]
        scores = scorer.score_candidates(records,[smiles[k] for k in ck])
        diffs.append(float(np.max(np.abs(scores-c.neural.values))))
        if a.expect_baseline_parity and diffs[-1] > 1e-5:
            raise ValueError(f'Replay parity failed for {key}: {diffs[-1]}')
        c['neural'] = scores
        c['neural_atlas_tail'] = leader_safe_fusion(scores,c.atlas_max.values,ck)
        row = baseline[baseline.key.eq(key)].iloc[0].to_dict()
        truth = ck.index(key) if key in ck else None
        for method in METHODS:
            ranking = ranks(c[method].values,ck)
            c['rank_'+method] = ranking
            rank = int(ranking[truth]) if truth is not None else 0
            row['rank_'+method] = rank
            row['rr_'+method] = 1./rank if 1 <= rank <= 25 else 0.
        summary.append(row)
        evidence.append(c)
        if n % 20 == 0 or n==len(keys):
            print(json.dumps(dict(done=n,total=len(keys),seconds=round(time.monotonic()-started,1))),flush=True)
    frame = pd.DataFrame(summary)
    frame.to_csv(a.out / 'molecule_results.csv',index=False)
    pd.concat(evidence,ignore_index=True).to_parquet(a.out / 'candidate_evidence.parquet',index=False)
    result = summarize(frame,source['config']['seed'])
    result.update(runtime_seconds=time.monotonic()-started,limitation=source['limitation'],
                  max_abs_score_change_from_baseline=max(diffs),baseline_parity_requested=a.expect_baseline_parity)
    (a.out / 'results.json').write_text(json.dumps(result,indent=2)+'\n')
    provenance.update(finished_utc=datetime.now(timezone.utc).isoformat(),state='complete',
                       outputs={name:sha256(a.out/name) for name in ['molecule_results.csv','candidate_evidence.parquet','results.json']})
    (a.out / 'manifest.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
