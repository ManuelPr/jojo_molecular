"""Parse a NIST-format MSP library into a parquet of MS2 spectra (one row per record)."""
import sys
from pathlib import Path
import pandas as pd

KEYS = {'Name': 'name', 'DB#': 'record_id', 'InChIKey': 'inchikey', 'SMILES': 'smiles', 'Precursor_type': 'adduct',
        'Spectrum_type': 'spectrum_type', 'PrecursorMZ': 'precursor_mz', 'Instrument_type': 'instrument_type',
        'Instrument': 'instrument', 'Ion_mode': 'ion_mode', 'Collision_energy': 'collision_energy', 'Formula': 'formula'}


def records(path):
    rec, mz, it, in_peaks = {}, [], [], False
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        if not line.strip():
            if rec:
                yield dict(rec, mzs=mz, intensities=it)
            rec, mz, it, in_peaks = {}, [], [], False
            continue
        if in_peaks:
            parts = line.replace('\t', ' ').split()
            if len(parts) >= 2:
                mz.append(float(parts[0])); it.append(float(parts[1]))
            continue
        key, _, val = line.partition(':')
        if key == 'Num Peaks':
            in_peaks = True
        elif key in KEYS and KEYS[key] not in rec:
            rec[KEYS[key]] = val.strip()
    if rec:
        yield dict(rec, mzs=mz, intensities=it)


if __name__ == '__main__':
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    df = pd.DataFrame(records(src))
    df['precursor_mz'] = pd.to_numeric(df.precursor_mz, errors='coerce')
    df['inchikey14'] = df.inchikey.str[:14]
    df.to_parquet(out, index=False)
    print(len(df), 'records ->', out)
