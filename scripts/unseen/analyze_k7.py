"""K7 NP type-3 bench: C477 (base) vs wider class-3 generation (genwide), per stage and per molecule, with the official
metric identity on candidate SMILES (truths in the contracts are metric identities).
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


def load(pattern):
    runs = [r for r in sorted(glob.glob(str(ROOT/pattern))) if Path(r, 'k2_export/export_info.json').is_file()]
    c = pd.concat([pd.read_parquet(Path(r)/'k2_export/candidates.parquet') for r in runs])
    truth = {}
    for r in runs:
        info = json.loads(Path(r, 'k2_run_info.json').read_text())
        truth.update(json.loads(Path(info['contract']).read_text())['truth'])
    return c[(c.arm == 'base') | ((c.arm == 'sanpier') & (c.stage == 'final_c477'))], truth, len(runs)


def per_stage(c, truth, mk):
    c = c.assign(k=c.smiles.map(mk))
    c['hit'] = c.k == c.query_id.map(truth)
    out = {}
    for st, g in c.groupby('stage'):
        best = g[g.hit].groupby('query_id')['rank'].min()
        r = pd.Series(sorted(truth)).map(best)
        out[st] = dict(present=int(r.notna().sum()), top1=int((r == 1).sum()), top25=int((r <= 25).sum()),
                       mrr=round(float(np.where(r <= 25, 1/r, 0).mean()), 4))
    return out, c


def main():
    # argv: [variant run pattern, output tag]; default is genwide vs base
    pat, tag = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ('artifacts/k2_replay/r_k7v2gen_s?', 'v2')
    base, truth, nb = load('artifacts/k2_replay/r_k7v2_s?')
    gen, truth2, ng = load(pat)
    assert truth == truth2
    mk = metric_keys(list(base.smiles) + list(gen.smiles))
    sb, cb = per_stage(base, truth, mk)
    sg, cg = per_stage(gen, truth, mk)
    rep = dict(molecules=len(truth), variant=pat, runs=dict(base=nb, variant=ng), base=sb, var=sg)
    fb = cb[cb.stage == 'final_c477']; fg = cg[cg.stage == 'final_c477']
    rb = fb[fb.hit].groupby('query_id')['rank'].min(); rg = fg[fg.hit].groupby('query_id')['rank'].min()
    q = sorted(truth)
    d = np.array([(1/rg[x] if x in rg.index else 0) - (1/rb[x] if x in rb.index else 0) for x in q])
    rng = np.random.default_rng(0)
    bt = d[rng.integers(0, len(d), (5000, len(d)))].mean(1)
    rep['final_delta_variant_minus_base'] = dict(delta=round(float(d.mean()), 4), ci95=np.quantile(bt, [.025, .975]).round(4).tolist(),
                                                 improved=int((d > 0).sum()), worsened=int((d < 0).sum()))
    (ROOT/f'artifacts/K7/analysis_{tag}.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    main()
