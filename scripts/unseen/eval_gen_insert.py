"""Insertion-style wide generation ("genfix", discussion 752356), emulated on final lists: keep the C477 base list order
exactly and insert only the structures (by metric identity) that the wide-generator run has and the base list lacks, at
their wide-run rank + d. Also keepK: C477's first K structures, then the wide-run order. Benches T1 / K6 clean / K7.

Usage: eval_gen_insert.py  -> artifacts/K6/gen_insert_v1.json   (run with CASMI_ROOT=<main checkout>)
"""
import glob
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get('CASMI_ROOT', Path(__file__).resolve().parents[2]))  # main checkout holds data/artifacts
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from eval_docprior_layer import compare, load  # noqa: E402
from eval_smiles_level import metric_keys  # noqa: E402


def load_stage(pattern, stage):
    """Lists of one export stage (e.g. final0465 = the frozen pipeline's own output, before the neural layers)."""
    runs = [r for r in sorted(glob.glob(str(ROOT/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]
    c = pd.concat([pd.read_parquet(Path(r)/'k2_export/candidates.parquet') for r in runs])
    f = c[(c.arm == 'base') & (c.stage == stage)].sort_values(['query_id', 'rank'])
    return f.groupby('query_id').smiles.apply(list).to_dict()


def insert(base, gen, mk, d):
    out = {}
    for q, b in base.items():
        g = gen.get(q, [])
        bk = {mk.get(s) for s in b}
        new = [(r, s) for r, s in enumerate(g) if mk.get(s) not in bk]
        res = list(b)
        for r, s in sorted(new):
            res.insert(min(r+d, len(res)), s)
        out[q] = res[:25]
    return out


def keep(base, gen, k):
    return {q: b[:k] + [s for s in gen.get(q, b) if s not in b[:k]] for q, b in base.items()}


def main():
    t1 = pd.read_parquet(ROOT/'artifacts/K6/type1_np250_v1/molecules.parquet').set_index('molecule_id')
    train = pd.read_parquet(ROOT/'data/fastweb/competition/train.parquet', columns=['inchikey14', 'normalized_smiles'])
    t1_smiles = t1.inchikey14.map(train.drop_duplicates('inchikey14').set_index('inchikey14').normalized_smiles)
    k6 = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules_metric.parquet').set_index('molecule_id')
    k6 = k6[~k6.in_train_metric & (k6.truth_metric.fillna('') != '')]
    k7_truth = {}
    for r in glob.glob(str(ROOT/'artifacts/k2_replay/r_k7v2_s?')):
        info = json.loads(Path(r, 'k2_run_info.json').read_text())
        k7_truth.update(json.loads(Path(info['contract']).read_text())['truth'])
    benches = {'T1': ('r_t1_np250', 'r_t1gen_np250'), 'K6': ('r2_k6_s?', 'r_k6gen_s?'), 'K7': ('r_k7v2_s?', 'r_k7v2gen_s?')}
    data = {b: (load('artifacts/k2_replay/'+p)[0], load('artifacts/k2_replay/'+g)[0]) for b, (p, g) in benches.items()}
    pipe = {b: load_stage('artifacts/k2_replay/'+g, 'final0465') for b, (p, g) in benches.items()}
    mk = metric_keys(list(t1_smiles.dropna()) + [s for b, g in data.values() for d in (b, g) for L in d.values() for s in L]
                    + [s for d in pipe.values() for L in d.values() for s in L])
    truths = {'T1': {q: mk.get(s) for q, s in t1_smiles.items()}, 'K6': k6.truth_metric.to_dict(), 'K7': k7_truth}
    groups = {'T1': {'type1': list(t1.index)},
              'K6': {f'type{t}': list(k6.index[k6.type_metric == t]) for t in (2, 3)},
              'K7': {'type3_np': list(k7_truth)}}
    rep = {}
    for bench, (base, gen) in data.items():
        variants = {'full': gen, **{f'keep{k}': keep(base, gen, k) for k in (1, 3, 5)},
                    **{f'insert_d{d}': insert(base, gen, mk, d) for d in (0, 2, 5)},
                    **{f'insert_pipe_d{d}': insert(base, pipe[bench], mk, d) for d in (0, 2)}}
        for g, qs in groups[bench].items():
            for name, var in variants.items():
                rep[f'{bench}/{g}/{name}'] = compare(base, var, truths[bench], mk, qs)
                print(f'{bench}/{g}/{name}', rep[f'{bench}/{g}/{name}'], flush=True)
    (ROOT/'artifacts/K6/gen_insert_v1.json').write_text(json.dumps(rep, indent=1, default=float))


if __name__ == '__main__':
    main()
