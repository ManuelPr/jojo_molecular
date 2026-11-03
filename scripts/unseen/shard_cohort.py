"""Split the K6 unseen cohort into replay shards (stratified by type) and write K2 input dirs plus CPU/GPU job lists."""
import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SLUG = 'enveda-CASMI26-molecule-id-mass-spectra'
DATASETS = ROOT/'data/fastweb/k2_input_ext_shard0/datasets'  # same pinned dataset links as the K2 replays


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    p.add_argument('--shards', type=int, default=9)
    p.add_argument('--tag', default='k6')
    a = p.parse_args()
    comp = a.cohort/'competition'
    contract = json.loads((comp/'contract.json').read_text())
    mols = pd.read_parquet(a.cohort/'molecules.parquet').sort_values(['type', 'molecule_id'])
    mols['shard'] = range(len(mols))
    mols['shard'] %= a.shards  # round robin within the type ordering -> each shard gets both types
    test = pd.read_parquet(comp/'test.parquet')
    cpu_jobs, gpu_jobs = [], []
    for k in range(a.shards):
        ids = set(mols[mols.shard == k].molecule_id)
        sd = a.cohort/f'shard_{k}'/'competition'
        sd.mkdir(parents=True, exist_ok=True)
        test[test.molecule_id.isin(ids)].to_parquet(sd/'test.parquet', index=False)
        pd.DataFrame(dict(molecule_id=sorted(ids), smiles=';'.join(['CCO']*25))).to_csv(sd/'sample_submission.csv', index=False)
        if not (sd/'train.parquet').exists():
            (sd/'train.parquet').symlink_to((comp/'train.parquet').resolve())
        c = dict(contract, query_count=len(ids), spectrum_count=int(test.molecule_id.isin(ids).sum()), shard=k,
                 truth={q: t for q, t in contract['truth'].items() if q in ids})
        (sd/'contract.json').write_text(json.dumps(c, indent=1))
        inp = ROOT/f'data/fastweb/k2_input_{a.tag}_s{k}'
        cdir = inp/'competitions'/SLUG
        cdir.mkdir(parents=True, exist_ok=True)
        for f in ['contract.json', 'sample_submission.csv', 'test.parquet', 'train.parquet']:
            if not (cdir/f).exists():
                (cdir/f).symlink_to((sd/f).resolve() if f != 'train.parquet' else (comp/'train.parquet').resolve())
        if not (inp/'datasets').exists():
            (inp/'datasets').mkdir()
            for owner in DATASETS.iterdir():
                (inp/'datasets'/owner.name).mkdir()
                for link in owner.iterdir():
                    (inp/'datasets'/owner.name/link.name).symlink_to(link.resolve())
        rel = lambda x: str(Path(x).resolve().relative_to(ROOT))
        cpu_out = f'artifacts/k2_replay/cpu_{a.tag}_s{k}'
        cpu_jobs.append(dict(name=f'{a.tag}_s{k}', input=rel(inp), contract=rel(sd/'contract.json'), output=cpu_out))
        gpu_jobs.append(dict(name=f'{a.tag}_s{k}', input=rel(inp), contract=rel(sd/'contract.json'),
                             output=f'artifacts/k2_replay/r_{a.tag}_s{k}', wait_for=f'{cpu_out}/k2_cpu_phase_done.json',
                             env=dict(K2_REUSE_CHANNELS=str(ROOT/cpu_out))))
    (ROOT/f'artifacts/k2_replay/cpu_{a.tag}_jobs.json').write_text(json.dumps(cpu_jobs, indent=1))
    (ROOT/f'artifacts/k2_replay/gpu_{a.tag}_jobs.json').write_text(json.dumps(gpu_jobs, indent=1))
    mols[['molecule_id', 'inchikey14', 'type', 'np_library', 'shard']].to_parquet(a.cohort/'shards.parquet', index=False)
    print(mols.groupby(['shard', 'type']).size().unstack().to_string())


if __name__ == '__main__':
    main()
