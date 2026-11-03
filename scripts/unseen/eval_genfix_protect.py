"""Genfix with leader protection, emulated on the genfix replays: a structure inserted by genfix (in the genfix run's
Engine-1 'main' list, absent from the base run's) may not finish at rank 1; if it does, it is moved to rank 2 (or to
rank P). Compares base, genfix and protected genfix on T1 / T1-thin / K6 clean / K7 (official metric identity).

Usage: eval_genfix_protect.py  -> artifacts/K6/genfix_protect_v1.json   (run with CASMI_ROOT=<main checkout>)
"""
import glob
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get('CASMI_ROOT', Path(__file__).resolve().parents[2]))  # main checkout holds data/artifacts
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from eval_docprior_layer import compare  # noqa: E402
from eval_smiles_level import metric_keys  # noqa: E402


def stage_lists(pattern, arm, stage):
    runs = [r for r in sorted(glob.glob(str(ROOT/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]
    c = pd.concat([pd.read_parquet(Path(r)/'k2_export/candidates.parquet') for r in runs])
    f = c[(c.arm == arm) & (c.stage == stage)].sort_values(['query_id', 'rank'])
    return f.groupby('query_id').smiles.apply(list).to_dict()


def protect(fin, base_main, gfx_main, mk, pos):
    out, moved = {}, 0
    for q, L in fin.items():
        inserted = {mk.get(s) for s in gfx_main.get(q, [])} - {mk.get(s) for s in base_main.get(q, [])}
        if L and mk.get(L[0]) in inserted:
            L = L[1:pos] + [L[0]] + L[pos:]
            moved += 1
        out[q] = L
    return out, moved


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
    benches = {'T1': ('r_t1_np250', 'r_t1gfx_np250'), 'T1thin': ('r_t1thin_base', 'r_t1thin_gfx'),
               'K6': ('r2_k6_s?', 'r_k6gfx_s?'), 'K7': ('r_k7v2_s?', 'r_k7v2gfx_s?')}
    data = {}
    for b, (bp, gp) in benches.items():
        if not glob.glob(str(ROOT/'artifacts/k2_replay'/gp/'k2_export/export_info.json')):
            print('skip', b, '(no export yet)'); continue
        data[b] = [stage_lists('artifacts/k2_replay/'+p, a, s) for p, a, s in
                   ((bp, 'sanpier', 'final_c477'), (gp, 'sanpier', 'final_c477'), (bp, 'base', 'main'), (gp, 'base', 'main'))]
    mk = metric_keys(list(t1_smiles.dropna()) + [s for v in data.values() for d in v for L in d.values() for s in L])
    t1_truth = {q: mk.get(s) for q, s in t1_smiles.items()}
    truths = {'T1': t1_truth, 'T1thin': t1_truth, 'K6': k6.truth_metric.to_dict(), 'K7': k7_truth}
    groups = {'T1': {'type1': list(t1.index)}, 'T1thin': {'type1': list(t1.index)},
              'K6': {f'type{t}': list(k6.index[k6.type_metric == t]) for t in (2, 3)}, 'K7': {'type3_np': list(k7_truth)}}
    rep = {}
    for b, (bfin, gfin, bmain, gmain) in data.items():
        variants = {'genfix': (gfin, None)}
        for pos in (2, 3, 5):
            variants[f'protect_r{pos}'] = protect(gfin, bmain, gmain, mk, pos)
        for g, qs in groups[b].items():
            for name, (var, moved) in variants.items():
                rep[f'{b}/{g}/{name}'] = dict(compare(bfin, var, truths[b], mk, qs), leaders_moved=moved)
                print(f'{b}/{g}/{name}', rep[f'{b}/{g}/{name}'], flush=True)
    (ROOT/'artifacts/K6/genfix_protect_v1.json').write_text(json.dumps(rep, indent=1, default=float))


if __name__ == '__main__':
    main()
