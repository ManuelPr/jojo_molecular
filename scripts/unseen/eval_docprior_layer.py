"""Offline emulation of the public midx 0.479 final layer (documentation prior on ranks 2-25) on the clean benches,
for the C477 base runs and the wide class-3 generator runs, to see whether the prior (which favours PubChem-documented
pool structures) cancels the type-3 gain of generated candidates.

Layer, as in baidalinadilzhan/casmi26-midx-exact-dedup-fill-0-479 pxm_merge: leader = final_c477[0]; ranks 2-25
re-sorted by 1/(3+baseline_rank) + 0.75/(3+neural_rank) + POP_W*pop/20 + SPEC_W*spec*[lib_max>=0.87] + NP_W*np,
pop/spec/np looked up by metric InChIKey14 in pool_popularity.csv (0 when absent, e.g. generated structures);
candidates without neural evidence keep 1/(3+idx+1). Leader-move and outsider-fill details are not emulated.
Evaluation: official metric identity on truth and candidate SMILES (eval_smiles_level.metric_keys).

Usage: eval_docprior_layer.py  -> artifacts/K6/docprior_layer_v1.json
"""
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get('CASMI_ROOT', Path(__file__).resolve().parents[2]))  # main checkout holds data/artifacts
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from analyze_gen_cost import rr  # noqa: E402
from eval_smiles_level import metric_keys  # noqa: E402

POP_W, SPEC_W, NP_W, LIB_HIT_GATE = 0.10, 0.05, 0.02, 0.87
POP = ROOT/'data/fastweb/casmi26-pubchem-popularity-prior-v10/pool_popularity.csv'


def load(pattern):
    runs = [r for r in sorted(glob.glob(str(ROOT/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]
    lists, nf = {}, []
    for r in runs:
        c = pd.read_parquet(Path(r)/'k2_export/candidates.parquet')
        f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
        lists.update(f.groupby('query_id').smiles.apply(list).to_dict())
        nf.append(pd.read_parquet(Path(r)/'k2_export/neural_sanpier.parquet'))
    return lists, pd.concat(nf), len(runs)


def docprior(lists, nf, pop, spec, npm):
    out = {}
    for mid, g in nf.groupby('molecule_id', sort=False):
        if mid not in lists:
            continue
        order = np.argsort(-g.neural_score.to_numpy(), kind='stable')
        nr = np.empty(len(g), dtype=int)
        nr[order] = np.arange(1, len(g)+1)
        info = {s: (int(b), int(n), k) for s, b, n, k in zip(g.smiles, g.baseline_rank, nr, g.metric_key)}
        lib_hit = float(g.library_max.max()) >= LIB_HIT_GATE
        c = lists[mid]

        def score(s):
            if s in info:
                b, n, k = info[s]
                return (1/(3+b) + 0.75/(3+n) + POP_W*pop.get(k, 0.0)/20 + (SPEC_W if lib_hit else 0.0)*spec.get(k, 0.0)
                        + NP_W*npm.get(k, 0))
            return 1/(3+c.index(s)+1)
        out[mid] = [c[0]] + sorted(c[1:], key=score, reverse=True)
    for mid in lists:
        out.setdefault(mid, lists[mid])
    return out


def compare(base, var, truth, mk, qs):
    qs = [q for q in qs if q in base and q in var and truth.get(q)]
    b = np.array([rr(base[q], truth[q], mk) for q in qs])
    v = np.array([rr(var[q], truth[q], mk) for q in qs])
    d = v-b
    bt = d[np.random.default_rng(0).integers(0, len(d), (5000, len(d)))].mean(1)
    return dict(n=len(qs), base=round(b.mean(), 4), var=round(v.mean(), 4), delta=round(d.mean(), 4),
                ci95=np.quantile(bt, [.025, .975]).round(4).tolist(), improved=int((d > 0).sum()), worsened=int((d < 0).sum()))


def main():
    p = pd.read_csv(POP, usecols=['inchikey14', 'pop', 'src_spectral_library', 'np_coconut', 'np_lotus', 'src_natural_product'])
    pop = dict(zip(p.inchikey14, p['pop']))
    spec = dict(zip(p.inchikey14, p.src_spectral_library))
    npm = dict(zip(p.inchikey14, (p.np_coconut | p.np_lotus | p.src_natural_product).astype(int)))
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
    arms = {}
    for bench, (bpat, gpat) in benches.items():
        for arm, pat in (('base', bpat), ('gen', gpat)):
            lists, nf, n = load('artifacts/k2_replay/'+pat)
            arms[bench, arm] = lists
            arms[bench, arm+'_doc'] = docprior(lists, nf, pop, spec, npm)
            print(bench, arm, 'runs', n, 'queries', len(lists), flush=True)
    mk = metric_keys(list(t1_smiles.dropna()) + [s for d in arms.values() for L in d.values() for s in L])
    truths = {'T1': {q: mk.get(s) for q, s in t1_smiles.items()}, 'K6': k6.truth_metric.to_dict(), 'K7': k7_truth}
    groups = {'T1': {'type1': list(t1.index)},
              'K6': {f'type{t}': list(k6.index[k6.type_metric == t]) for t in (2, 3)},
              'K7': {'type3_np': list(k7_truth)}}
    pairs = [('base', 'base_doc'), ('base', 'gen'), ('base', 'gen_doc'), ('base_doc', 'gen_doc')]
    rep = {}
    for bench in benches:
        for g, qs in groups[bench].items():
            for a, b in pairs:
                rep[f'{bench}/{g}/{b}_vs_{a}'] = compare(arms[bench, a], arms[bench, b], truths[bench], mk, qs)
                print(f'{bench}/{g}/{b}_vs_{a}', rep[f'{bench}/{g}/{b}_vs_{a}'], flush=True)
    (ROOT/'artifacts/K6/docprior_layer_v1.json').write_text(json.dumps(rep, indent=1))


if __name__ == '__main__':
    main()
