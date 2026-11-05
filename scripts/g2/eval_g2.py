"""G2 recall evaluation on the clean benches: can the decoder put the truth among its samples?

Per query: fingerprint = mean sigmoid of the fp head of a sanpier-family scorer (default bgv4) over the query spectra;
formulas = oracle (truth) and the formula of the base final_c477 leader (what the kernel would use). For each formula, n
samples with formula masking; kept = parsed, exact formula (with H), dedup by official metric identity, ranked by sample
count. Reports recall @all/@100/@25 per bench/type and per formula source, and how many hits are new vs the base final 25.
Usage: CASMI_ROOT=<main> eval_g2.py --run artifacts/G2/run_v1 --gpu 0 [--n 256] -> <run>/eval_recall.json
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
import torch

ROOT = Path(os.environ.get('CASMI_ROOT', '/home/mpernigotto/jojo_molecular'))
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent/'unseen'), str(ROOT/'artifacts/k2_replay/src')]
from g2 import Generator  # noqa: E402
from eval_smiles_level import canonicalize_smiles_to_ik14  # noqa: E402
from eval_ensemble_480 import half  # noqa: E402

BUNDLES = ROOT/'data/fastweb/scorers_2026-11-05/bundles'


def formula_counts(formula, elements):
    from rdkit.Chem import rdMolDescriptors  # noqa: F401
    import re
    c = Counter()
    for e, k in re.findall(r'([A-Z][a-z]?)(\d*)', formula):
        c[e] += int(k) if k else 1
    return [c.get(e, 0) for e in elements], set(c) - set(elements)


def mol_formula(smiles):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdMolDescriptors
    RDLogger.DisableLog('rdApp.*')
    m = Chem.MolFromSmiles(smiles) if isinstance(smiles, str) else None
    return rdMolDescriptors.CalcMolFormula(m) if m is not None else None


def fp_predictions(bundle, spectra, device):
    import neural_scores
    model, feat, cfg = neural_scores.load_model(str(bundle), 'final_model.pt', device)
    out = {}
    with torch.inference_mode():
        for mid, g in spectra.groupby('molecule_id', sort=False):
            rec = []
            for r in g.itertuples(index=False):
                try:
                    pk, n = feat.peaks(r.ms2_mzs, r.ms2_normalized_intensities, r.precursor_mz, cfg['max_peaks'])
                    if n < cfg['min_peaks']:
                        continue
                    m, a = feat.metadata(r.precursor_mz, r.adduct, r.ionization_mode, r.collision_energy_ev)
                    rec.append((pk, n, m, a))
                except (ValueError, TypeError):
                    continue
            if not rec:
                continue
            x = torch.tensor(np.stack([v[0] for v in rec]), device=device)
            L = torch.tensor([v[1] for v in rec], device=device, dtype=torch.long)
            M = torch.tensor(np.stack([v[2] for v in rec]), device=device)
            A = torch.tensor([v[3] for v in rec], device=device, dtype=torch.long)
            _, P = model.encode_spectra(x, L, M, A)
            out[str(mid)] = torch.sigmoid(P).mean(0).float().cpu().numpy()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--gpu', default='0')
    ap.add_argument('--n', type=int, default=256)
    ap.add_argument('--fp_arm', default='bgv4')
    ap.add_argument('--type2_sample', type=int, default=150)
    ap.add_argument('--fp_bundle', default=None)
    ap.add_argument('--tag', default='')
    ap.add_argument('--temperature', type=float, default=1.0)
    a = ap.parse_args()
    dev = f'cuda:{a.gpu}'
    gen = Generator(a.run, dev)
    k6 = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules_metric.parquet').set_index('molecule_id')
    k6 = k6[~k6.in_train_metric & (k6.truth_metric.fillna('') != '')]
    k6mol = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules.parquet').set_index('molecule_id')
    smi_col = next(c for c in ['smiles', 'normalized_smiles', 'truth_smiles'] if c in k6mol.columns)
    queries = {}
    t2 = sorted(k6.index[k6.type_metric == 2], key=lambda q: half(q) + q)[:a.type2_sample]
    for q in list(k6.index[k6.type_metric == 3]) + t2:
        queries[q] = dict(bench='K6', type=int(k6.type_metric[q]), truth=k6.truth_metric[q], smiles=k6mol[smi_col].get(q))
    allk6 = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules_metric.parquet').set_index('molecule_id')
    key_smiles = {k: k6mol[smi_col].get(q) for q, k in allk6.truth_metric.dropna().items()}
    for r in glob.glob(str(ROOT/'artifacts/k2_replay/r_k7v2_s?')):
        info = json.loads(Path(r, 'k2_run_info.json').read_text())
        con = json.loads(Path(info['contract']).read_text())
        for q, k in con['truth'].items():
            queries[q] = dict(bench='K7', type=3, truth=k, smiles=key_smiles.get(k))
    spectra, finals = [], {}
    for pat in ['r2_k6_s?', 'r_k7v2_s?']:
        for r in sorted(glob.glob(str(ROOT/'artifacts/k2_replay'/pat))):
            s = pd.read_parquet(Path(r)/'effective_query_spectra.parquet')
            spectra.append(s[s.molecule_id.astype(str).isin(queries)])
            c = pd.read_parquet(Path(r)/'k2_export/candidates.parquet', columns=['query_id', 'arm', 'stage', 'rank', 'smiles', 'candidate_key'])
            f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
            finals.update({q: g for q, g in f.groupby('query_id')})
    spectra = pd.concat(spectra)
    fps = fp_predictions(Path(a.fp_bundle) if a.fp_bundle else BUNDLES/a.fp_arm, spectra, dev)
    print('queries', len(queries), 'with fp', len(fps), flush=True)
    rows = []
    for i, (q, info) in enumerate(queries.items()):
        if q not in fps or q not in finals:
            continue
        fin = finals[q]
        base_keys = set(fin.candidate_key)
        sources = {}
        if info['smiles']:
            f = mol_formula(info['smiles'])
            if f:
                sources['oracle'] = f
        lf = mol_formula(fin.smiles.iloc[0])
        if lf:
            sources['leader'] = lf
        for src, formula in sources.items():
            counts, extra = formula_counts(formula, gen.elements)
            if extra:
                continue
            samples = gen.sample(fps[q], counts, n=a.n, temperature=a.temperature)
            cnt = Counter()
            for s in samples:
                if s and mol_formula(s) == formula:
                    k = canonicalize_smiles_to_ik14(s)
                    if k:
                        cnt[k] += 1
            ranked = [k for k, _ in cnt.most_common()]
            r = ranked.index(info['truth']) + 1 if info['truth'] in ranked else None
            rows.append(dict(query_id=q, bench=info['bench'], type=info['type'], source=src, formula=formula,
                             formula_ok=(formula == sources.get('oracle')), n_valid=sum(cnt.values()), n_unique=len(cnt),
                             truth_rank=r, truth_in_base=info['truth'] in base_keys))
        if (i + 1) % 50 == 0:
            print(i + 1, 'queries', flush=True)
    d = pd.DataFrame(rows)
    d.to_parquet(Path(a.run)/f'eval_recall{a.tag}.parquet', index=False)
    rep = {}
    for (b, t, src), g in d.groupby(['bench', 'type', 'source']):
        rr = g.truth_rank
        rep[f'{b}/type{t}/{src}'] = dict(n=len(g), formula_ok=float(g.formula_ok.mean()), valid_frac=float(g.n_valid.mean() / a.n),
                                         unique=float(g.n_unique.mean()), recall_all=float(rr.notna().mean()),
                                         recall_100=float((rr <= 100).mean()), recall_25=float((rr <= 25).mean()),
                                         recall_10=float((rr <= 10).mean()),
                                         new_vs_base=int((rr.notna() & ~g.truth_in_base).sum()),
                                         mrr_gen=float((1 / rr).fillna(0).mean()))
    (Path(a.run)/f'eval_recall{a.tag}.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    main()
