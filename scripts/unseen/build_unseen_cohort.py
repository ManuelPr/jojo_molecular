"""K6: cohort of molecules with public MS/MS spectra but absent from the competition train (unseen by every public model).

Sources: GNPS full library (2026-03) and MassBank 2026.03, parsed by parse_gnps_mgf.py / parse_msp.py. A molecule is kept
when its InChIKey14 is not among the 275,810 train identities, at least one spectrum has a test adduct, the neutral mass is
157-1159 Da and the precursor agrees with structure + adduct within 30 ppm. Each molecule is labelled
  type 2: structure in a pipeline catalog (pool train+COCONUT, ChEBI/LIPID MAPS, PubChemLite) or in the PubChem tier
  type 3: in none of them
(type 1 needs reference spectra of the molecule, which unseen molecules do not have). Output: competition-format test,
sample submission, train symlink and a K2 contract with no reference exclusions.
"""
import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'data/fastweb/casmi26-attributed-v4g-reproduction-assets-v6'
TRAIN = ROOT/'data/fastweb/competition/train.parquet'
ADDUCTS = {  # test adducts -> neutral-mass offset
    '[M+H]+': 1.007276, '[M-H]-': -1.007276, '[M+Na]+': 22.989218, '[M+NH4]+': 18.033823, '[M+K]+': 38.963158,
    '[M+Cl]-': 34.969402, '[M+CH2O2-H]-': 44.998201}
ALIASES = {'M+H': '[M+H]+', '[M+H]': '[M+H]+', 'M-H': '[M-H]-', '[M-H]': '[M-H]-', 'M+Na': '[M+Na]+', '[M+Na]': '[M+Na]+',
           'M+NH4': '[M+NH4]+', '[M+NH4]': '[M+NH4]+', 'M+K': '[M+K]+', '[M+K]': '[M+K]+', 'M+Cl': '[M+Cl]-',
           '[M+Cl]': '[M+Cl]-', 'M+FA-H': '[M+CH2O2-H]-', '[M+FA-H]-': '[M+CH2O2-H]-', 'M+HCOO': '[M+CH2O2-H]-',
           '[M+HCOO]-': '[M+CH2O2-H]-', 'M+CH2O2-H': '[M+CH2O2-H]-'}
NP_LIBRARIES = {'BMDMS-NP', 'TUEBINGEN-NATURAL-PRODUCT-COLLECTION', 'GNPS-NIH-NATURALPRODUCTSLIBRARY', 'MIADB',
                'ELIXDB-LICHEN-DATABASE', 'NEO-MSMS', 'LEAFBOT', 'MassBank:RIKEN_NPDepo'}
MAX_SPECTRA = 16


def load_spectra():
    g = pd.read_parquet(ROOT/'data/external/gnps_2026.03/gnps_2026.03.parquet')
    g = g[g.ms_level.fillna('2').astype(str).eq('2')]
    g = g.assign(source='gnps', record=g.spectrum_id, instrument_type=g.instrument)
    m = pd.read_parquet(ROOT/'data/external/massbank_2026.03/massbank_2026.03.parquet')
    m = m[m.spectrum_type.eq('MS2')]
    m = m.assign(source='massbank', record=m.record_id,
                 library='MassBank:' + m.record_id.str.extract(r'MSBNK-([A-Za-z0-9_]+)-')[0].fillna(''))
    cols = ['source', 'record', 'library', 'smiles', 'inchikey14', 'adduct', 'precursor_mz', 'instrument_type', 'mzs',
            'intensities']
    return pd.concat([g[cols], m[cols]], ignore_index=True)


def structure_info(smiles):
    from rdkit import Chem, RDLogger
    from rdkit.Chem.Descriptors import ExactMolWt
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    RDLogger.DisableLog('rdApp.*')
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None or any(a.GetFormalCharge() for a in mol.GetAtoms()) or len(Chem.GetMolFrags(mol)) != 1:
        return None
    return dict(mass=ExactMolWt(mol), formula=CalcMolFormula(mol), ik14=Chem.MolToInchiKey(mol)[:14],
                smiles=Chem.MolToSmiles(mol))


def catalog_keys():
    keys = set(pd.read_parquet(ASSETS/'casmi26-v2-pool/pool_meta.parquet', columns=['key']).key)
    for f in ['coconut-casmi26-candidates/coco_meta.pkl', 'casmi-chebi-lmsd-structures/bio_meta.pkl',
              'chebi-lipidmaps-casmi26/bio_meta.pkl', 'casmi26-pubchemlite-cc0-candidate-fingerprints/pubchemlite_meta.pkl']:
        keys |= set(pickle.load(open(ASSETS/f, 'rb'))['keys'])
    return keys


def in_pubchem_tier(rows, ppm=5.0):
    """rows: (ik14, neutral mass). True when an exact-mass PubChem-tier SMILES has the same InChIKey14."""
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    mass = np.load(ASSETS/'pubchem_tier__pc_mass.npy', mmap_mode='r')
    off = np.load(ASSETS/'pubchem_tier__pc_off.npy', mmap_mode='r')
    smi = np.load(ASSETS/'pubchem_tier__pc_smiles.npy', mmap_mode='r')
    out = {}
    for ik, m in rows:
        lo, hi = np.searchsorted(mass, [m*(1-ppm*1e-6), m*(1+ppm*1e-6)])
        hit = False
        for j in range(lo, hi):
            mol = Chem.MolFromSmiles(bytes(smi[off[j]:off[j+1]]).decode())
            if mol is not None and Chem.MolToInchiKey(mol)[:14] == ik:
                hit = True
                break
        out[ik] = (hit, int(hi-lo))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=ROOT/'artifacts/K6/unseen_v1')
    p.add_argument('--workers', type=int, default=24)
    a = p.parse_args()
    train_keys = set(pd.read_parquet(TRAIN, columns=['inchikey14']).inchikey14)
    s = load_spectra()
    s = s[s.inchikey14.notna() & ~s.inchikey14.isin(train_keys)].copy()
    s['adduct'] = s.adduct.fillna('').str.strip().map(lambda x: ALIASES.get(x, x))
    s = s[s.adduct.isin(ADDUCTS)]
    info = {smi: structure_info(smi) for smi in s.smiles.unique()}
    s['sinfo'] = s.smiles.map(info)
    s = s[s['sinfo'].notna()]
    s['ik14'] = s['sinfo'].map(lambda d: d['ik14'])
    s = s[s.ik14.eq(s.inchikey14) & ~s.ik14.isin(train_keys)]
    s['mass'] = s['sinfo'].map(lambda d: d['mass'])
    s['ppm'] = ((s.precursor_mz - s.adduct.map(ADDUCTS)) - s.mass) / s.mass * 1e6
    s['n_peaks'] = s.mzs.map(len)
    s = s[s.ppm.abs().le(30) & s.mass.between(157, 1159) & s.n_peaks.ge(3)]
    s = s.sort_values(['ik14', 'n_peaks'], ascending=[True, False]).groupby('ik14').head(MAX_SPECTRA)

    mols = s.groupby('ik14').agg(smiles=('sinfo', lambda x: x.iloc[0]['smiles']), formula=('sinfo', lambda x: x.iloc[0]['formula']),
                                 mass=('mass', 'first'), n_spectra=('record', 'size'),
                                 libraries=('library', lambda x: sorted(set(x))), sources=('source', lambda x: sorted(set(x))))
    mols['np_library'] = mols.libraries.map(lambda L: bool(set(L) & NP_LIBRARIES))
    keys = catalog_keys()
    mols['in_local_catalog'] = mols.index.isin(keys)
    from concurrent.futures import ProcessPoolExecutor
    rows = list(zip(mols.index, mols.mass))
    chunks = [rows[i::a.workers] for i in range(a.workers)]
    tier = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for part in ex.map(in_pubchem_tier, chunks):
            tier.update(part)
    mols['in_pubchem_tier'] = [tier[k][0] for k in mols.index]
    mols['pubchem_tier_same_mass'] = [tier[k][1] for k in mols.index]
    mols['type'] = np.where(mols.in_local_catalog | mols.in_pubchem_tier, 2, 3)
    mols['molecule_id'] = [f'k6-unseen-{i:04d}' for i in range(len(mols))]

    s = s.join(mols[['molecule_id']], on='ik14')
    norm = [np.asarray(i, float)/max(i) for i in s.intensities]
    test = pd.DataFrame(dict(
        molecule_id=s.molecule_id.values, spectrum_id=[f's_k6_{i:06d}' for i in range(len(s))],
        ms2_mzs=[np.asarray(m, float) for m in s.mzs], ms2_normalized_intensities=norm,
        base_peak_intensity=[float(max(i)) for i in s.intensities], adduct=s.adduct.values,
        ionization_mode=np.where(s.adduct.str.endswith('-'), 'negative', 'positive'),
        instrument_type=s.instrument_type.fillna('unknown').values, precursor_mz=s.precursor_mz.values,
        collision_energy_orig=None, collision_energy_ev=[None]*len(s), collision_energy_orig_units='unknown'))  # as cohort v4

    comp = a.out/'competition'
    comp.mkdir(parents=True, exist_ok=True)
    test.to_parquet(comp/'test.parquet', index=False)
    pd.DataFrame(dict(molecule_id=mols.molecule_id, smiles=';'.join(['CCO']*25))).to_csv(comp/'sample_submission.csv', index=False)
    if not (comp/'train.parquet').exists():
        (comp/'train.parquet').symlink_to(TRAIN)
    contract = dict(query_count=len(mols), spectrum_count=len(test), truth=dict(zip(mols.molecule_id, mols.index)),
                    excluded_raw_identities=[], excluded_canonical_identities=[], collateral_canonical_identities=[],
                    validation='K6 unseen: public spectra whose identities are absent from the competition train',
                    types=mols.type.value_counts().sort_index().to_dict())
    (comp/'contract.json').write_text(json.dumps(contract, indent=1, default=int))
    mols.reset_index().rename(columns={'ik14': 'inchikey14'}).to_parquet(a.out/'molecules.parquet', index=False)
    summary = dict(molecules=len(mols), spectra=len(test),
                   by_type=mols.type.value_counts().sort_index().to_dict(),
                   np_library_by_type=mols[mols.np_library].type.value_counts().sort_index().to_dict(),
                   by_source=mols.sources.map('+'.join).value_counts().to_dict(),
                   adducts=test.adduct.value_counts().to_dict(), instruments=test.instrument_type.value_counts().head(10).to_dict())
    (a.out/'summary.json').write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == '__main__':
    main()
