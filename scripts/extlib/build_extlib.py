"""X1: external reference library of public MS/MS spectra whose structures are NOT in train.parquet.

Host ruling (discussion 750684, 2026-10-27): "You are welcome to use more recent updates of the data sources used in
train.parquet." Sources (all newer releases of train's ingest_lib sources):
  GNPS full library (ALL_GNPS_NO_PROPOGATED, pulled 2026-10-31), MassBank 2026.03, MSnLib v8 (Zenodo 23494858, CC BY 4.0).
A spectrum is kept when the official metric identity (stereo removed, canonical tautomer, InChIKey14; frozen cell 47) of its
structure is not among the train metric keys (pool_meta.key where train_sid >= 0). Output: one row per spectrum with
ionmode (+1/-1), prec, mz, it (base peak 1, peaks <= prec + 0.5, at most MAX_PEAKS by intensity), key, smiles, source,
instrument, adduct. Also writes a per-structure table and a summary.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

MAIN = Path('/home/mpernigotto/jojo_molecular')
EXT = MAIN/'data/external'
POOL_META = MAIN/'data/fastweb/casmi26-attributed-v4g-reproduction-assets-v6/casmi26-v2-pool/pool_meta.parquet'
MAX_PEAKS = 150
MIN_PEAKS = 3

_TAUT = None


def metric_key(smiles):
    """Official metric identity (frozen notebook cell 47): stereo removed, canonical tautomer, InChIKey14."""
    global _TAUT
    from rdkit import Chem, RDLogger
    from rdkit.Chem.MolStandardize import rdMolStandardize
    RDLogger.DisableLog('rdApp.*')
    if _TAUT is None:
        _TAUT = rdMolStandardize.TautomerEnumerator()
    if not isinstance(smiles, str) or not smiles:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        Chem.RemoveStereochemistry(mol)
        return Chem.MolToInchiKey(_TAUT.Canonicalize(mol))[:14]
    except Exception:
        return None


def to_array(v):
    if isinstance(v, str):
        return np.array([float(x) for x in v.split(',') if x], np.float64)
    return np.asarray(v, np.float64)


def mode_of(v):
    s = str(v).strip().lower()
    if s.startswith('pos') or s in ('+', 'p', '1'):
        return 1
    if s.startswith('neg') or s in ('-', 'n', '-1'):
        return -1
    return 0


def load_sources():
    parts = []
    g = pd.read_parquet(EXT/'gnps_2026.03/gnps_2026.03.parquet',
                        columns=['precursor_mz', 'ms_level', 'instrument', 'ion_mode', 'library', 'smiles', 'spectrum_id',
                                 'mzs', 'intensities', 'adduct'])
    g = g[g.ms_level.astype(str).isin(['2', '2.0'])]
    g = g[~g.library.astype(str).str.upper().str.contains('NIST')]  # NIST-derived annotations are prohibited
    parts.append(pd.DataFrame(dict(source='gnps:' + g.library.astype(str), spectrum_id=g.spectrum_id.astype(str),
                                   smiles=g.smiles, adduct=g.adduct.astype(str), ionmode=g.ion_mode.map(mode_of),
                                   prec=pd.to_numeric(g.precursor_mz, errors='coerce'), instrument=g.instrument.astype(str),
                                   mzs=g.mzs, its=g.intensities)))
    m = pd.read_parquet(EXT/'massbank_2026.03/massbank_2026.03.parquet',
                        columns=['record_id', 'smiles', 'adduct', 'spectrum_type', 'precursor_mz', 'instrument_type',
                                 'ion_mode', 'mzs', 'intensities'])
    m = m[m.spectrum_type.astype(str).str.upper().isin(['MS2', 'MS/MS'])]
    parts.append(pd.DataFrame(dict(source='massbank', spectrum_id=m.record_id.astype(str), smiles=m.smiles,
                                   adduct=m.adduct.astype(str), ionmode=m.ion_mode.map(mode_of),
                                   prec=pd.to_numeric(m.precursor_mz, errors='coerce'),
                                   instrument=m.instrument_type.astype(str), mzs=m.mzs, its=m.intensities)))
    s = pd.read_parquet(EXT/'msnlib_v8_msg/msnlib_ms2.parquet',
                        columns=['identifier', 'mzs', 'intensities', 'smiles', 'adduct', 'precursor_mz', 'instrument_type',
                                 'ionmode', 'source_file'])
    parts.append(pd.DataFrame(dict(source='msnlib:' + s.source_file.str.replace('_ms2.mgf', '', regex=False),
                                   spectrum_id=s.identifier.astype(str), smiles=s.smiles, adduct=s.adduct.astype(str),
                                   ionmode=s.ionmode.map(mode_of), prec=pd.to_numeric(s.precursor_mz, errors='coerce'),
                                   instrument=s.instrument_type.astype(str), mzs=s.mzs, its=s.intensities)))
    return pd.concat(parts, ignore_index=True)


def clean_peaks(args):
    mzs, its, prec = args
    try:
        m, i = to_array(mzs), to_array(its)
    except Exception:
        return None
    if len(m) != len(i) or len(m) == 0 or not np.isfinite(prec):
        return None
    keep = np.isfinite(m) & np.isfinite(i) & (i > 0) & (m <= prec + 0.5)
    m, i = m[keep], i[keep]
    if len(m) < MIN_PEAKS:
        return None
    if len(m) > MAX_PEAKS:
        top = np.argsort(-i)[:MAX_PEAKS]
        m, i = m[top], i[top]
    o = np.argsort(m)
    m, i = m[o], i[o]
    return m.astype(np.float32), (i / i.max()).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(MAIN/'artifacts/X1/extlib_v1'))
    ap.add_argument('--workers', type=int, default=28)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    d = load_sources()
    n0 = len(d)
    d = d[(d.ionmode != 0) & d.prec.notna()]
    d = d[d.smiles.notna() & (d.smiles.astype(str).str.len() > 0) & (d.smiles.astype(str) != 'N/A')]
    print('spectra', n0, '-> with mode/prec/smiles', len(d), flush=True)

    smiles = sorted(set(d.smiles.astype(str)))
    with ProcessPoolExecutor(a.workers) as ex:
        keys = dict(zip(smiles, ex.map(metric_key, smiles, chunksize=256)))
    d['key'] = d.smiles.astype(str).map(keys)
    d = d[d.key.notna()]
    train = set(pd.read_parquet(POOL_META, columns=['key', 'train_sid']).query('train_sid >= 0').key)
    d['in_train'] = d.key.isin(train)
    print('structures', d.key.nunique(), 'in train', d[d.in_train].key.nunique(), flush=True)

    x = d[~d.in_train].copy()
    with ProcessPoolExecutor(a.workers) as ex:
        peaks = list(ex.map(clean_peaks, zip(x.mzs, x.its, x.prec), chunksize=512))
    x['ok'] = [p is not None for p in peaks]
    x['mz'] = [p[0] if p is not None else None for p in peaks]
    x['it'] = [p[1] if p is not None else None for p in peaks]
    x = x[x.ok].drop(columns=['mzs', 'its', 'ok', 'in_train'])
    # one canonical SMILES per key (most frequent)
    canon = x.groupby('key').smiles.agg(lambda s: s.value_counts().index[0])
    x['smiles_canonical'] = x.key.map(canon)
    x = x.reset_index(drop=True)
    x.to_parquet(out/'extlib_refs.parquet', index=False)

    per = x.groupby('key').agg(smiles=('smiles_canonical', 'first'), n_spectra=('prec', 'size'),
                              sources=('source', lambda s: ';'.join(sorted(set(s)))),
                              instruments=('instrument', lambda s: ';'.join(sorted(set(s))[:6]))).reset_index()
    per.to_parquet(out/'extlib_structures.parquet', index=False)
    summary = dict(spectra_in=int(n0), spectra_out=int(len(x)), structures_out=int(per.shape[0]),
                   by_source_spectra=x.source.str.split(':').str[0].value_counts().to_dict(),
                   by_source_structures=x.groupby(x.source.str.split(':').str[0]).key.nunique().to_dict(),
                   msnlib_files=x[x.source.str.startswith('msnlib')].groupby('source').key.nunique().to_dict(),
                   ionmode=x.ionmode.value_counts().to_dict(), train_keys=len(train))
    json.dump(summary, open(out/'summary.json', 'w'), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
