"""Parse the GNPS full-library MGF into a parquet of MS2 spectra with InChIKey14 (RDKit from SMILES/InChI)."""
import sys
from pathlib import Path

import pandas as pd

FIELDS = {'PEPMASS': 'precursor_mz', 'SOURCE_INSTRUMENT': 'instrument', 'IONMODE': 'ion_mode', 'ORGANISM': 'library',
          'NAME': 'name', 'SMILES': 'smiles', 'INCHI': 'inchi', 'INCHIAUX': 'inchiaux', 'SPECTRUMID': 'spectrum_id',
          'MSLEVEL': 'ms_level', 'LIBRARYQUALITY': 'quality', 'ADDUCT': 'adduct_field'}


def records(path):
    rec, mz, it = None, [], []
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line == 'BEGIN IONS':
            rec, mz, it = {}, [], []
        elif line == 'END IONS':
            if rec is not None:
                yield dict(rec, mzs=mz, intensities=it)
            rec = None
        elif rec is not None:
            if line[:1].isdigit():
                parts = line.split()
                if len(parts) >= 2:
                    mz.append(float(parts[0])); it.append(float(parts[1]))
            else:
                key, _, val = line.partition('=')
                if key in FIELDS:
                    rec[FIELDS[key]] = val.strip()


def ik14(smiles, inchi):
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    for make in ((lambda: Chem.MolFromSmiles(smiles)) if smiles and smiles not in ('N/A', ' ') else None,
                 (lambda: Chem.MolFromInchi(inchi)) if inchi and inchi.startswith('InChI=') else None):
        if make is None:
            continue
        try:
            mol = make()
            if mol is not None:
                return Chem.MolToInchiKey(mol)[:14]
        except Exception:
            pass
    return None


if __name__ == '__main__':
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    df = pd.DataFrame(records(src))
    df['precursor_mz'] = pd.to_numeric(df.precursor_mz.str.split().str[0], errors='coerce')
    df['adduct'] = df.get('adduct_field').fillna(df.name.str.extract(r'\s(\[?M[^\s]*)$')[0]) \
        if 'adduct_field' in df else df.name.str.extract(r'\s(\[?M[^\s]*)$')[0]
    for col in ('smiles', 'inchi'):
        df[col] = df[col].fillna('') if col in df else ''
    keys = df[['smiles', 'inchi']].drop_duplicates()
    keys['inchikey14'] = [ik14(s, i) for s, i in zip(keys.smiles, keys.inchi)]
    df = df.merge(keys, on=['smiles', 'inchi'], how='left')
    df.to_parquet(out, index=False)
    print(len(df), 'spectra,', df.inchikey14.notna().sum(), 'with structure ->', out)
