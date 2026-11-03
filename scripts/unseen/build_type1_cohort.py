"""T1: realistic type-1 bench in the test domain. Queries = the 1,184 timsTOF spectra of the 250 enveda-np-examples molecules;
reference library = competition train without exactly those rows (each molecule keeps its spectra from RIKEN, GNPS, MoNA ...),
which is the hidden-test situation for a molecule present in public libraries. The pipeline and its models have seen these
identities (as for every real type-1 molecule); the bench measures what a change costs or gains on type 1, not novelty.
Output: K2 competition dir (test, filtered train, sample submission, contract) and an input dir with the pinned datasets.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SLUG = 'enveda-CASMI26-molecule-id-mass-spectra'
OUT = ROOT/'artifacts/K6/type1_np250_v1'
DATASETS = ROOT/'data/fastweb/k2_input_ext_shard0/datasets'


def main():
    train = pd.read_parquet(ROOT/'data/fastweb/competition/train.parquet')
    q = train[train.ingest_lib == 'enveda-np-examples'].copy()
    ref = train[train.ingest_lib != 'enveda-np-examples']
    keys = sorted(q.inchikey14.unique())
    ids = {k: f't1-np-{i:04d}' for i, k in enumerate(keys)}
    test = pd.DataFrame(dict(
        molecule_id=q.inchikey14.map(ids).values, spectrum_id=[f's_t1_{i:05d}' for i in range(len(q))],
        ms2_mzs=q.ms2_mzs.values, ms2_normalized_intensities=q.ms2_normalized_intensities.values,
        base_peak_intensity=q.base_peak_intensity.values, adduct=q.adduct.values, ionization_mode=q.ionization_mode.values,
        instrument_type=q.instrument_type.values, precursor_mz=q.precursor_mz.values,
        collision_energy_orig=q.collision_energy_orig.values, collision_energy_ev=q.collision_energy_ev.values,
        collision_energy_orig_units=q.collision_energy_orig_units.values))
    comp = OUT/'competition'
    comp.mkdir(parents=True, exist_ok=True)
    test.to_parquet(comp/'test.parquet', index=False)
    ref.to_parquet(comp/'train.parquet', index=False)
    pd.DataFrame(dict(molecule_id=sorted(ids.values()), smiles=';'.join(['CCO']*25))).to_csv(comp/'sample_submission.csv', index=False)
    other = ref[ref.inchikey14.isin(keys)].groupby('inchikey14').size()
    contract = dict(query_count=len(ids), spectrum_count=len(test), truth={v: k for k, v in ids.items()},
                    excluded_raw_identities=[], excluded_canonical_identities=[], collateral_canonical_identities=[],
                    removed_reference_rows=int(len(q)), validation='T1: enveda-np-examples queries, own spectra removed, '
                    'other-library spectra of the same molecule kept (type 1 in the test domain)',
                    reference_spectra_per_molecule=dict(min=int(other.min()), median=float(other.median()), max=int(other.max())))
    (comp/'contract.json').write_text(json.dumps(contract, indent=1))
    inp = ROOT/'data/fastweb/k2_input_t1_np250'
    cdir = inp/'competitions'/SLUG
    cdir.mkdir(parents=True, exist_ok=True)
    for f in ['contract.json', 'sample_submission.csv', 'test.parquet', 'train.parquet']:
        if not (cdir/f).exists():
            (cdir/f).symlink_to((comp/f).resolve())
    if not (inp/'datasets').exists():
        (inp/'datasets').mkdir()
        for owner in DATASETS.iterdir():
            (inp/'datasets'/owner.name).mkdir()
            for link in owner.iterdir():
                (inp/'datasets'/owner.name/link.name).symlink_to(link.resolve())
    print(json.dumps({k: v for k, v in contract.items() if k != 'truth'}, indent=1))


if __name__ == '__main__':
    main()
