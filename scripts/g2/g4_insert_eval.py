"""G4: turn generator recall into MRR. Generated candidates are inserted into the emulated 0.480 final lists (K11
final_layer, ref_480 weights) only for queries the G3b early gate selects (artifacts/G3/gate_early_v2.json, fire5).

Protocol fixed before scores (2026-11-06):
  generation  G2 decoder, formula of the base final leader, fingerprint = mean sigmoid fp head of own_w384_s7 over the query
              spectra, N samples, exact formula (with H), dedup by official metric identity, top 50 by sample count, minus
              keys already in the list. (Optional extra source: G1 candidates parquet, same treatment.)
  scoring     neural z-ensemble 0.5 z(public sanpier v1) + 0.5 z(own_w384_s7) over list + generated, per query.
  insertion   a generated candidate goes right after the last list member with a higher ensemble score, never above
              position MINPOS; at most KINS per list; list truncated to 25. Grid KINS {1,3,5} x MINPOS {2,5}.
  choice      cal mix 0.35 T1thin + 0.30 K6t2 + 0.35 K6t3 (sha256 half 'cal'); one verification on ver; T1, K7 transfer.
Usage: CASMI_ROOT=<main> g4_insert_eval.py --run artifacts/G2/run_v2 --gpu 1 [--n 512] -> <run>/g4_insert.json
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get('CASMI_ROOT', '/home/mpernigotto/jojo_molecular'))
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent/'unseen'), str(ROOT/'artifacts/k2_replay/src')]
import eval_ensemble_480 as k11  # noqa: E402
import g3_type3_gate as g3  # noqa: E402
import g3b_early_gate as g3b  # noqa: E402
from eval_docprior_layer import compare, POP  # noqa: E402
from eval_smiles_level import canonicalize_smiles_to_ik14, metric_keys  # noqa: E402
from eval_g2 import fp_predictions, formula_counts, mol_formula  # noqa: E402
from g2 import Generator  # noqa: E402

PUB = ROOT/'data/fastweb/sanpier-casmi-spectrum-model-v1/casmi_spectrum_model_v1'
OWN = ROOT/'artifacts/X2/own_w384_s7'
BENCH = {'K6': 'r2_k6_s?', 'K7': 'r_k7v2_s?', 'T1': 'r_t1_np250', 'T1thin': 'r_t1thin_base',
         # test-domain transfer benches (report only, not in the selection mix): 128 enveda NP examples with ALL their
         # reference spectra removed; T2np keeps the catalogs (type 2), T3np withholds them (type-3 proxy)
         'T2np': 'run_cohort_v2_base', 'T3np': 'r3_proxy3_v4_cohort_v2_reuse'}
COHORT_V2 = ROOT/'artifacts/K2/cohort_v2/competition/contract.json'
G2_KEYS = ROOT/'artifacts/G2/data_v1/structures.parquet'
GRID = {f'k{k}_p{p}': (k, p) for k in (1, 3, 5) for p in (2, 5)}
MIX = {'T1thin': 0.35, 'K6t2': 0.30, 'K6t3': 0.35}


def gate_fire(feat):
    r = json.loads((ROOT/'artifacts/G3/gate_early_v2.json').read_text())
    m, thr = r['model'], r['thresholds_by_t1thin_cal_fire']['0.05']
    X = feat[m['features']].to_numpy(float)
    z = ((X - np.array(m['mean'])) / np.array(m['scale'])) @ np.array(m['coef']) + m['intercept']
    return pd.Series(1 / (1 + np.exp(-z)) > thr, index=feat.index)


def neural(bundle, frame, spectra, path, device):
    import neural_scores
    ev, qs = Path(str(path) + '.evidence.parquet'), Path(str(path) + '.queries.parquet')
    frame.to_parquet(ev, index=False)
    spectra.to_parquet(qs, index=False)
    neural_scores.score(str(bundle), 'final_model.pt', str(ev), str(qs), str(path), device)
    return pd.read_parquet(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--gpu', default='1')
    ap.add_argument('--n', type=int, default=512)
    ap.add_argument('--extra', default=None, help='optional G1 candidates parquet (query_id, smiles)')
    ap.add_argument('--gate_mode', choices=['g3b', 'all'], default='g3b')
    ap.add_argument('--benches', default=None, help='comma list restricting BENCH (e.g. T1thin,T2np,T3np,K7)')
    ap.add_argument('--tag', default='')
    ap.add_argument('--topm', type=int, default=20, help='generated structures kept per query (amended 50 -> 20 before the '
                    'v2 run, to match the kernel runtime budget)')
    a = ap.parse_args()
    global BENCH
    if a.benches:
        BENCH = {b: BENCH[b] for b in a.benches.split(',')}
    dev = f'cuda:{a.gpu}'
    out = Path(a.run)
    gen = Generator(a.run, dev)
    p = pd.read_csv(POP, usecols=['inchikey14', 'pop', 'src_spectral_library', 'np_coconut', 'np_lotus', 'src_natural_product'])
    prior = (dict(zip(p.inchikey14, p['pop'])), dict(zip(p.inchikey14, p.src_spectral_library)),
             dict(zip(p.inchikey14, (p.np_coconut | p.np_lotus | p.src_natural_product).astype(int))))
    k11.ARMS = ['sanpier', 'bgunshui']
    lists, fire, spectra = {}, {}, []
    for b, pat in BENCH.items():
        L, nf = k11.load(pat)
        lists[b] = k11.final_layer(L, nf, (0.5, 0.5), prior)
        fire[b] = gate_fire(g3b.features(pat))
        for r in g3.runs(pat):
            spectra.append(pd.read_parquet(Path(r)/'effective_query_spectra.parquet'))
    spectra = pd.concat(spectra).drop_duplicates(['molecule_id', 'spectrum_id'])
    spectra['molecule_id'] = spectra.molecule_id.astype(str)
    if a.gate_mode == 'all':      # diagnostic: every query of the benches listed in --benches (no gate)
        fire = {b: pd.Series(True, index=list(lists[b])) for b in BENCH}
    gated = {q for b in BENCH for q, f in fire[b].items() if f and q in lists[b]}
    print('gated queries', {b: int(fire[b].sum()) for b in BENCH}, flush=True)
    sp = spectra[spectra.molecule_id.isin(gated)]
    fps = fp_predictions(OWN, sp, dev)
    extra = pd.read_parquet(a.extra) if a.extra else None
    rows = []
    allL = {q: L for b in BENCH for q, L in lists[b].items()}
    for i, q in enumerate(sorted(gated)):
        L = allL[q]
        f = mol_formula(L[0])
        have = {canonicalize_smiles_to_ik14(s) for s in L}
        cnt, rep = Counter(), {}
        if f and q in fps:
            counts, ex = formula_counts(f, gen.elements)
            if not ex:
                for s in gen.sample(fps[q], counts, n=a.n):
                    if s and mol_formula(s) == f:
                        k = canonicalize_smiles_to_ik14(s)
                        if k and k not in have:
                            cnt[k] += 1; rep.setdefault(k, s)
        if extra is not None:
            for s in extra[extra.query_id.astype(str) == q].smiles:
                k = canonicalize_smiles_to_ik14(s)
                if k and k not in have and k not in rep:
                    cnt[k] += 1; rep[k] = s
        for k, c in cnt.most_common(a.topm):
            rows.append(dict(molecule_id=q, smiles=rep[k], key=k, count=c))
        if (i + 1) % 100 == 0:
            print(i + 1, 'generated', flush=True)
    G = pd.DataFrame(rows)
    G.to_parquet(out/f'g4_generated{a.tag}.parquet', index=False)
    frame = pd.concat([pd.DataFrame([dict(molecule_id=q, smiles=s, baseline_rank=j + 1, processed=True) for q in gated for j, s in enumerate(allL[q])]),
                       pd.DataFrame(dict(molecule_id=G.molecule_id, smiles=G.smiles, baseline_rank=26 + G.groupby('molecule_id').cumcount(),
                                         processed=True))], ignore_index=True)
    sc = {}
    for name, bundle in (('pub', PUB), ('own', OWN)):
        n = neural(bundle, frame, sp, out/f'g4_neural_{name}{a.tag}.parquet', dev)
        g = n.groupby('molecule_id').neural_score
        sc[name] = ((n.neural_score - g.transform('mean')) / g.transform(lambda x: x.std(ddof=0)).clip(lower=1e-6)).to_numpy()
    n['ens'] = 0.5 * sc['pub'] + 0.5 * sc['own']
    ens = {q: dict(zip(g.smiles, g.ens)) for q, g in n.groupby('molecule_id')}
    gen_by_q = {q: list(g.smiles) for q, g in G.groupby('molecule_id')}

    def insert(kins, minpos):
        res = {}
        for b in BENCH:
            res[b] = {}
            for q, L in lists[b].items():
                if q not in gated or q not in gen_by_q:
                    res[b][q] = L
                    continue
                e = ens[q]
                cand = sorted(gen_by_q[q], key=lambda s: -e.get(s, -1e9))[:kins]
                new = list(L)
                for s in cand:
                    pos = max(minpos - 1, max([j + 1 for j, t in enumerate(new) if e.get(t, -1e9) > e.get(s, -1e9)], default=0))
                    new.insert(min(pos, len(new)), s)
                res[b][q] = new[:25]
        return res

    variants = {v: insert(*kp) for v, kp in GRID.items()}
    t1, k6, k7 = None, None, {}
    t1 = pd.read_parquet(ROOT/'artifacts/K6/type1_np250_v1/molecules.parquet').set_index('molecule_id')
    train = pd.read_parquet(ROOT/'data/fastweb/competition/train.parquet', columns=['inchikey14', 'normalized_smiles'])
    t1_smiles = t1.inchikey14.map(train.drop_duplicates('inchikey14').set_index('inchikey14').normalized_smiles)
    k6 = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules_metric.parquet').set_index('molecule_id')
    k6 = k6[~k6.in_train_metric & (k6.truth_metric.fillna('') != '')]
    for r in glob.glob(str(ROOT/'artifacts/k2_replay/r_k7v2_s?')):
        info = json.loads(Path(r, 'k2_run_info.json').read_text())
        k7.update(json.loads(Path(info['contract']).read_text())['truth'])
    mk = metric_keys(list(t1_smiles.dropna()) + [s for d in [lists] + list(variants.values()) for L in d.values() for x in L.values() for s in x])
    t1_truth = {q: mk.get(s) for q, s in t1_smiles.items()}
    cv2 = json.loads(COHORT_V2.read_text())['truth']
    truths = {'K6': k6.truth_metric.to_dict(), 'K7': k7, 'T1': t1_truth, 'T1thin': t1_truth, 'T2np': cv2, 'T3np': cv2}
    leak = set(pd.read_parquet(G2_KEYS, columns=['key']).key)   # truths the generator saw in training (raw/metric mismatch)
    groups = {'K6t2': ('K6', list(k6.index[k6.type_metric == 2])), 'K6t3': ('K6', list(k6.index[k6.type_metric == 3])),
              'K7': ('K7', list(k7)), 'T1': ('T1', list(t1.index)), 'T1thin': ('T1thin', list(t1.index)),
              'T2np': ('T2np', list(cv2)), 'T3np': ('T3np', list(cv2))}
    groups = {g: (b, [q for q in qs if truths[b].get(q) not in leak or g in ('T1', 'T1thin', 'K6t2')])
              for g, (b, qs) in groups.items() if b in BENCH}
    print('queries per group after generator-leak filter', {g: len(qs) for g, (b, qs) in groups.items()}, flush=True)

    def evaluate(v, split):
        return {g: compare(lists[b], v[b], truths[b], mk, [q for q in qs if q in lists[b] and (split == 'all' or k11.half(q) == split)])
                for g, (b, qs) in groups.items()}
    cal = {k: evaluate(v, 'cal') for k, v in variants.items()}
    obj = {k: sum(MIX[g] * cal[k][g]['delta'] for g in MIX if g in cal[k]) for k in variants}
    sel = max(obj, key=obj.get)
    rep = dict(gated={b: int(fire[b].sum()) for b in BENCH}, generated_rows=len(G), cal_objective=obj, selected=sel,
               ver=evaluate(variants[sel], 'ver'), all={k: evaluate(v, 'all') for k, v in variants.items()})
    (out/f'g4_insert{a.tag}.json').write_text(json.dumps(rep, indent=1, default=float))
    print(json.dumps(dict(cal_objective=obj, selected=sel), indent=1))
    for g, v in rep['ver'].items():
        print('ver', sel, g, {x: (round(y, 4) if isinstance(y, float) else y) for x, y in v.items()}, flush=True)


if __name__ == '__main__':
    main()
