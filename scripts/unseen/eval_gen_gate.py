"""Gated wide generation, emulated per query: wide-generator list when the query's library_max (best library cosine,
from the base run's neural features) is below a gate, C477 base list otherwise. Measures how much of the T1 cost of the
wide generator a library gate removes and how much of the type-3 gain it keeps, on T1 / K6 clean / K7.

Usage: eval_gen_gate.py  -> artifacts/K6/gen_gate_v1.json   (run with CASMI_ROOT=<main checkout>)
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get('CASMI_ROOT', Path(__file__).resolve().parents[2]))  # main checkout holds data/artifacts
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from eval_docprior_layer import compare, load  # noqa: E402
from eval_smiles_level import metric_keys  # noqa: E402

GATES = [0.6, 0.7, 0.8, 0.87, 0.95, 2.0]   # 2.0 = always wide


def main():
    import glob
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
    data = {}
    for bench, (bpat, gpat) in benches.items():
        base, nf, _ = load('artifacts/k2_replay/'+bpat)
        gen, _, _ = load('artifacts/k2_replay/'+gpat)
        data[bench] = (base, gen, nf.groupby('molecule_id').library_max.max().to_dict())
    mk = metric_keys(list(t1_smiles.dropna()) + [s for b, g, _ in data.values() for d in (b, g) for L in d.values() for s in L])
    truths = {'T1': {q: mk.get(s) for q, s in t1_smiles.items()}, 'K6': k6.truth_metric.to_dict(), 'K7': k7_truth}
    groups = {'T1': {'type1': list(t1.index)},
              'K6': {f'type{t}': list(k6.index[k6.type_metric == t]) for t in (2, 3)},
              'K7': {'type3_np': list(k7_truth)}}
    rep = {}
    for bench, (base, gen, lm) in data.items():
        for g, qs in groups[bench].items():
            vals = pd.Series([lm.get(q, 0.0) for q in qs])
            rep[f'{bench}/{g}/lib_max_quantiles'] = vals.quantile([.1, .25, .5, .75, .9]).round(3).tolist()
            for gate in GATES:
                var = {q: (gen[q] if lm.get(q, 0.0) < gate and q in gen else base[q]) for q in base}
                rep[f'{bench}/{g}/gate{gate}'] = compare(base, var, truths[bench], mk, qs)
                print(f'{bench}/{g}/gate{gate}', rep[f'{bench}/{g}/gate{gate}'], flush=True)
            print(f'{bench}/{g} lib_max quantiles', rep[f'{bench}/{g}/lib_max_quantiles'], flush=True)
    (ROOT/'artifacts/K6/gen_gate_v1.json').write_text(json.dumps(rep, indent=1, default=float))


if __name__ == '__main__':
    main()
