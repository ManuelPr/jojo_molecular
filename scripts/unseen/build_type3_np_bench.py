"""K7 step 2: NP type-3 bench. 276 natural products from K6 type 2 (unseen by every public model) are made novel for the
pipeline: withheld from the local catalogs (Codex's catalog guards, contract from prepare_k2_catalog_withheld.py) and from
the PubChem channel (K2_PUBCHEM_EXCLUDE wrapper in k2_runner.py). Truths are official metric identities.

Writes, per shard: competition dir (test, sample submission, train symlink, contract, query_contract), K2 input dir, plus
the crosswalk for the composition prefilter, the PubChem exclusion JSON and CPU/GPU job lists.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SLUG = 'enveda-CASMI26-molecule-id-mass-spectra'
OUT = ROOT/'artifacts/K7/np_type3_v2'  # v2: drops molecules whose metric identity is a train identity
V1 = ROOT/'artifacts/K7/np_type3_v1'
DATASETS = ROOT/'data/fastweb/k2_input_ext_shard0/datasets'
ASSETS = ROOT/'data/fastweb/casmi26-attributed-v4g-reproduction-assets-v6'
SHARDS = 2


def main():
    mols = pd.read_parquet(V1/'molecules_k7.parquet').drop(columns=['k7_id', 'shard'])
    mols = mols[~mols.in_train_metric].sort_values('molecule_id').reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    mols['k7_id'] = [f'k7-np3-{i:04d}' for i in range(len(mols))]
    k6test = pd.read_parquet(ROOT/'artifacts/K6/unseen_v1/competition/test.parquet')
    idmap = dict(zip(mols.molecule_id, mols.k7_id))
    test = k6test[k6test.molecule_id.isin(idmap)].assign(molecule_id=lambda d: d.molecule_id.map(idmap))
    pd.DataFrame(dict(scorer_key=mols.truth_metric, smiles=mols.smiles)).to_parquet(OUT/'crosswalk.parquet', index=False)
    off = np.load(ASSETS/'pubchem_tier__pc_off.npy', mmap_mode='r')
    smi = np.load(ASSETS/'pubchem_tier__pc_smiles.npy', mmap_mode='r')
    rows = np.array(sorted({j for h in mols.pubchem_rows for j in h}), dtype=np.int64)
    np.save(OUT/'pubchem_excluded_rows.npy', rows)
    excl = dict(smiles=sorted({bytes(smi[off[j]:off[j+1]]).decode() for j in rows}),
                raw=sorted(set(mols.inchikey14)), metric=sorted(set(mols.truth_metric)))
    (OUT/'pubchem_exclude.json').write_text(json.dumps(excl))
    mols['shard'] = np.arange(len(mols)) % SHARDS
    mols.to_parquet(OUT/'molecules_k7.parquet', index=False)
    cpu, gpu = [], []
    for k in range(SHARDS):
        sel = mols[mols.shard == k]
        comp = OUT/f'shard_{k}'/'competition'
        comp.mkdir(parents=True, exist_ok=True)
        test[test.molecule_id.isin(set(sel.k7_id))].to_parquet(comp/'test.parquet', index=False)
        pd.DataFrame(dict(molecule_id=sel.k7_id, smiles=';'.join(['CCO']*25))).to_csv(comp/'sample_submission.csv', index=False)
        pd.DataFrame(dict(molecule_id=sel.k7_id, truth=sel.truth_metric)).to_parquet(comp/'query_contract.parquet', index=False)
        if not (comp/'train.parquet').exists():
            (comp/'train.parquet').symlink_to(ROOT/'data/fastweb/competition/train.parquet')
        # all 276 identities withheld in every shard (as in cohort v4), truths are metric identities
        contract = dict(query_count=len(sel), spectrum_count=int(test.molecule_id.isin(set(sel.k7_id)).sum()),
                        truth=dict(zip(sel.k7_id, sel.truth_metric)),
                        excluded_canonical_identities=sorted(set(mols.truth_metric)),
                        excluded_raw_identities=sorted(set(mols.inchikey14) | set(mols.truth_metric)),
                        collateral_canonical_identities=[], shard=k,
                        validation='K7 NP type 3: K6 natural products withheld from local catalogs and PubChem channel')
        (comp/'contract.json').write_text(json.dumps(contract, indent=1))
        inp = ROOT/f'data/fastweb/k2_input_k7v2_s{k}'
        cdir = inp/'competitions'/SLUG
        cdir.mkdir(parents=True, exist_ok=True)
        for f in ['contract.json', 'sample_submission.csv', 'test.parquet', 'train.parquet', 'query_contract.parquet']:
            if not (cdir/f).exists():
                (cdir/f).symlink_to((comp/f).resolve())
        if not (inp/'datasets').exists():
            (inp/'datasets').mkdir()
            for owner in DATASETS.iterdir():
                (inp/'datasets'/owner.name).mkdir()
                for link in owner.iterdir():
                    (inp/'datasets'/owner.name/link.name).symlink_to(link.resolve())
        rel = lambda x: str(Path(x).resolve().relative_to(ROOT))
        cat = OUT/f'catalogs/shard_{k}/contract.json'
        env = dict(K2_PUBCHEM_EXCLUDE=str(OUT/'pubchem_exclude.json'))
        cpu.append(dict(name=f'k7v2_s{k}', input=rel(inp), contract=rel(comp/'contract.json'), catalog_contract=rel(cat),
                        output=f'artifacts/k2_replay/cpu_k7v2_s{k}', env=env))
        gpu.append(dict(name=f'k7v2_s{k}', input=rel(inp), contract=rel(comp/'contract.json'), catalog_contract=rel(cat),
                        output=f'artifacts/k2_replay/r_k7v2_s{k}', wait_for=f'artifacts/k2_replay/cpu_k7v2_s{k}/k2_cpu_phase_done.json',
                        env=dict(env, K2_REUSE_CHANNELS=str(ROOT/f'artifacts/k2_replay/cpu_k7v2_s{k}'), K2_GPU_PROBE='torch')))
    (ROOT/'artifacts/k2_replay/cpu_k7v2_jobs.json').write_text(json.dumps(cpu, indent=1))
    (ROOT/'artifacts/k2_replay/gpu_k7v2_jobs.json').write_text(json.dumps(gpu, indent=1))
    print('molecules', len(mols), 'spectra', len(test), 'pubchem excluded smiles', len(excl['smiles']),
          'shards', mols.shard.value_counts().to_dict())


if __name__ == '__main__':
    main()
