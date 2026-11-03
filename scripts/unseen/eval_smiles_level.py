"""Re-evaluate the dense-channel variants at SMILES level with the official metric identity (stereo removed, RDKit tautomer
canonicalisation, InChIKey14) on both the truth and every candidate, as the competition scorer does.

Earlier K6/T1 numbers compared raw InChIKey14 truths with export keys that are metric identities (tautomer-standardised),
so tautomerisable molecules could be miscounted. Parameters are not re-chosen here: w and delta stay as fixed before.
Variants: jm (local, w=0.5), fp1 (FPNet local, w=2), fp2 (FPNet local + PubChem tier, delta=1, w=2).
"""
import glob
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/unseen'))
import jm_channel_merge as J  # noqa: E402
from fpnet_pubchem import channel_lists  # noqa: E402
from jm_retrieval import catalog  # noqa: E402


def canonicalize_smiles_to_ik14(smiles):
    """Official metric identity (frozen notebook cell 47): stereo removed, canonical tautomer, InChIKey14."""
    from rdkit import Chem, RDLogger
    from rdkit.Chem.MolStandardize import rdMolStandardize
    RDLogger.DisableLog('rdApp.*')
    global _TAUT
    if '_TAUT' not in globals():
        _TAUT = rdMolStandardize.TautomerEnumerator()
    if not isinstance(smiles, str):
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        Chem.RemoveStereochemistry(mol)
        return Chem.MolToInchiKey(_TAUT.Canonicalize(mol))[:14]
    except (ValueError, RuntimeError, TypeError):
        return None


def metric_keys(smiles, workers=24):
    smiles = sorted(set(s for s in smiles if isinstance(s, str)))
    with ProcessPoolExecutor(workers) as ex:
        return dict(zip(smiles, ex.map(canonicalize_smiles_to_ik14, smiles, chunksize=200)))


def dedup(keys):
    return [k for k in dict.fromkeys(keys) if k is not None]


def main():
    cat = catalog().set_index('key').smiles
    benches = {
        'K6': dict(mols=pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/molecules.parquet').set_index('molecule_id'),
                   runs='artifacts/k2_replay/r2_k6_s?', jm='artifacts/K6/jm_retrieval_lists_v1.parquet',
                   fp='artifacts/K6/bakeoff/fpnet5_scores.parquet', pc='artifacts/K6/fpnet5_pubchem_scores_k6.parquet'),
        'T1': dict(mols=pd.read_parquet(ROOT/'artifacts/K6/type1_np250_v1/molecules.parquet').set_index('molecule_id'),
                   runs='artifacts/k2_replay/r_t1_np250', jm='artifacts/K6/jm_retrieval_lists_t1.parquet',
                   fp='artifacts/K6/bakeoff_t1_fpnet5_scores.parquet', pc='artifacts/K6/fpnet5_pubchem_scores_t1.parquet')}
    train = pd.read_parquet(ROOT/'data/fastweb/competition/train.parquet', columns=['inchikey14', 'normalized_smiles'])
    t1_smiles = train.drop_duplicates('inchikey14').set_index('inchikey14').normalized_smiles
    report = {}
    for name, b in benches.items():
        mols = b['mols']
        truth_smiles = mols.smiles if 'smiles' in mols else mols.inchikey14.map(t1_smiles)
        c = pd.concat([pd.read_parquet(r+'/k2_export/candidates.parquet') for r in sorted(glob.glob(str(ROOT/b['runs'])))])
        f = c[(c.arm == 'sanpier') & (c.stage == 'final_c477')].sort_values(['query_id', 'rank'])
        c477 = f.groupby('query_id').smiles.apply(list).to_dict()
        jm = pd.read_parquet(ROOT/b['jm']).sort_values(['molecule_id', 'jm_rank'])
        jm_lists = jm.groupby('molecule_id').smiles.apply(list).to_dict()
        fp = pd.read_parquet(ROOT/b['fp']).assign(src='local')
        pc = pd.read_parquet(ROOT/b['pc'])
        pc_smiles = pc.drop_duplicates(['molecule_id', 'key']).set_index(['molecule_id', 'key']).smiles.to_dict()
        to_smiles = lambda q, keys: [cat.get(k) if k in cat.index else pc_smiles.get((q, k)) for k in keys]
        fp1 = {q: to_smiles(q, k) for q, k in channel_lists(fp, delta=1e9).items()}
        fp2 = {q: to_smiles(q, k) for q, k in channel_lists(pd.concat([fp, pc[['molecule_id', 'key', 'score', 'src']]])).items()}
        allsmi = list(truth_smiles.dropna()) + [s for d in (c477, jm_lists, fp1, fp2) for L in d.values() for s in L]
        mk = metric_keys(allsmi)
        truth = {q: mk.get(s) for q, s in truth_smiles.items()}
        queries = sorted(set(c477) & set(mols.index))
        part = {q: ('cal' if int(hashlib.sha256(q.encode()).hexdigest(), 16) % 2 == 0 else 'ver') for q in queries}
        base = {q: J.rr(dedup(mk.get(s) for s in c477[q]), truth[q]) for q in queries}
        rng = np.random.default_rng(0)
        report[name] = {'C477_mrr_by_type': {}}
        for t in sorted(set(mols.type[queries])):
            xs = [q for q in queries if mols.type[q] == t]
            report[name]['C477_mrr_by_type'][int(t)] = round(float(np.mean([base[q] for q in xs])), 4)
        for var, lists, w in (('jm', jm_lists, 0.5), ('fp1', fp1, 2.0), ('fp2', fp2, 2.0)):
            res = {}
            for t in sorted(set(mols.type[queries])):
                for p in (('ver',) if name == 'K6' else ('all',)):
                    xs = [q for q in queries if mols.type[q] == t and (p == 'all' or part[q] == p)]
                    d = np.array([J.rr(J.merged(dedup(mk.get(s) for s in c477[q]), dedup(mk.get(s) for s in lists.get(q, [])), w),
                                       truth[q]) - base[q] for q in xs])
                    bt = d[rng.integers(0, len(d), (5000, len(d)))].mean(1)
                    res[f'type{int(t)}_{p}'] = dict(n=len(xs), delta=round(float(d.mean()), 4),
                                                    ci95=np.quantile(bt, [.025, .975]).round(4).tolist(),
                                                    improved=int((d > 0).sum()), worsened=int((d < 0).sum()))
            report[name][var] = res
        print(name, json.dumps(report[name], indent=1), flush=True)
    (ROOT/'artifacts/K6/eval_smiles_level_v1.json').write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
