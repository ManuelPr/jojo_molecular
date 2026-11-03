"""Cost of wider class-3 generation on type 1 (T1) and on clean K6 types 2/3: final C477 lists, base vs generator runs,
official metric identity on truth and candidate SMILES. K6 drops molecules whose metric identity is a train identity.

Usage: analyze_gen_cost.py [t1_variant_pattern] [k6_variant_pattern] [tag]
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/unseen'))
from eval_smiles_level import metric_keys  # noqa: E402


def final_lists(pattern):
    runs = [r for r in sorted(glob.glob(str(ROOT/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]
    c = pd.concat([pd.read_parquet(Path(r)/'k2_export/candidates.parquet') for r in runs])
    f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
    return f.groupby('query_id').smiles.apply(list).to_dict(), len(runs)


def rr(smiles, truth, mk):
    seen = []
    for s in smiles:
        k = mk.get(s)
        if k and k not in seen:
            seen.append(k)
    return 1/(seen.index(truth)+1) if truth in seen[:25] else 0.0


def keep_top(base, var, k):
    """C477's first k structures, then the variant list (deduplicated by SMILES)."""
    out = {}
    for q in var:
        head = base.get(q, [])[:k]
        out[q] = head + [s for s in var[q] if s not in head]
    return out


def compare(base, var, truth, mk, groups):
    out = {}
    for g, qs in groups.items():
        qs = [q for q in qs if q in base and q in var]
        if not qs:
            continue
        b = np.array([rr(base[q], truth[q], mk) for q in qs])
        v = np.array([rr(var[q], truth[q], mk) for q in qs])
        d = v - b
        bt = d[np.random.default_rng(0).integers(0, len(d), (5000, len(d)))].mean(1)
        out[g] = dict(n=len(qs), base_mrr=round(b.mean(), 4), var_mrr=round(v.mean(), 4), delta=round(d.mean(), 4),
                      ci95=np.quantile(bt, [.025, .975]).round(4).tolist(), improved=int((d > 0).sum()),
                      worsened=int((d < 0).sum()), base_top1=int((b == 1).sum()), var_top1=int((v == 1).sum()),
                      base_present=int((b > 0).sum()), var_present=int((v > 0).sum()))
    return out


def main():
    t1_pat = sys.argv[1] if len(sys.argv) > 1 else 'artifacts/k2_replay/r_t1gen_np250'
    k6_pat = sys.argv[2] if len(sys.argv) > 2 else 'artifacts/k2_replay/r_k6gen_s?'
    tag = sys.argv[3] if len(sys.argv) > 3 else 'genwide'
    rep = {}
    # T1: truths are train structures, their metric identity comes from the train SMILES
    t1 = pd.read_parquet(ROOT/'artifacts/K6/type1_np250_v1/molecules.parquet').set_index('molecule_id')
    train = pd.read_parquet(ROOT/'data/fastweb/competition/train.parquet', columns=['inchikey14', 'normalized_smiles'])
    t1_smiles = t1.inchikey14.map(train.drop_duplicates('inchikey14').set_index('inchikey14').normalized_smiles)
    tb, _ = final_lists('artifacts/k2_replay/r_t1_np250')
    tv, nt = final_lists(t1_pat)
    # K6: truth_metric already computed with the official identity
    k6 = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules_metric.parquet').set_index('molecule_id')
    k6 = k6[~k6.in_train_metric & (k6.truth_metric.fillna('') != '')]
    kb, _ = final_lists('artifacts/k2_replay/r2_k6_s?')
    kv, nk = final_lists(k6_pat)
    mk = metric_keys(list(t1_smiles.dropna()) + [s for d in (tb, tv, kb, kv) for L in d.values() for s in L])
    t1_truth = {q: mk.get(s) for q, s in t1_smiles.items()}
    rep['T1'] = dict(runs=nt, **compare(tb, tv, t1_truth, mk, {'type1': list(t1.index)}))
    rep['T1_keep1'] = compare(tb, keep_top(tb, tv, 1), t1_truth, mk, {'type1': list(t1.index)})
    k6_truth = k6.truth_metric.to_dict()
    groups = {f'type{t}': list(k6.index[k6.type_metric == t]) for t in (2, 3)}
    groups['all'] = list(k6.index)
    rep['K6_clean'] = dict(runs=nk, **compare(kb, kv, k6_truth, mk, groups))
    rep['K6_clean_keep1'] = compare(kb, keep_top(kb, kv, 1), k6_truth, mk, groups)
    (ROOT/f'artifacts/K6/gen_cost_{tag}.json').write_text(json.dumps(rep, indent=1, default=float))
    print(json.dumps(rep, indent=1, default=float))


if __name__ == '__main__':
    main()
