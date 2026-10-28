"""Convert public ICEBERG predictions with bounded peak memory and identity audits."""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from rdkit import Chem, rdBase
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem.MolStandardize import rdMolStandardize

from casmi26.chemistry import canonical_inchikey14

SCHEMA = pa.schema([
    ("normalized_smiles", pa.string()), ("smiles", pa.string()),
    ("inchikey14", pa.string()), ("atlas_inchikey14", pa.string()),
    ("formula", pa.string()), ("ms2_mzs", pa.list_(pa.float64())),
    ("ms2_normalized_intensities", pa.list_(pa.float32())),
    ("precursor_mz", pa.float64()), ("adduct", pa.string()),
    ("ionization_mode", pa.string()), ("collision_energy_ev", pa.float64()),
    ("ingest_lib", pa.string()), ("instrument_type", pa.string()),
    ("molecule_id", pa.string()), ("spectrum_id", pa.string()), ("is_simulated", pa.bool_()),
])


@lru_cache(maxsize=65536)
def normalize_structure(smiles):
    """Use the official transformations once, deriving key and SMILES together."""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None, None, None
        Chem.RemoveStereochemistry(mol)
        mol = rdMolStandardize.TautomerEnumerator().Canonicalize(mol)
        key = Chem.MolToInchiKey(mol)[:14]
        return key or None, Chem.MolToSmiles(mol, isomericSmiles=False), rdMolDescriptors.CalcMolFormula(mol)
    except (ValueError, RuntimeError):
        return None, None, None


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def iter_mgf(path: Path, *, selected: set[int] | None = None, headers_only=False):
    """Yield (block index, headers, peaks), rejecting broken blocks and gzip CRCs.

    Pass one stores headers only. Pass two materializes only selected spectra.
    """
    opener = gzip.open if path.suffix == ".gz" else open
    head, peaks, index, wanted = None, [], -1, False
    with opener(path, "rt", encoding="utf-8") as handle:
        for number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith(("#", ";", "!")):
                continue
            if line == "BEGIN IONS":
                if head is not None:
                    raise ValueError(f"{path}:{number}: nested BEGIN IONS")
                index += 1
                head, peaks = {}, []
                wanted = selected is None or index in selected
            elif line == "END IONS":
                if head is None:
                    raise ValueError(f"{path}:{number}: unmatched END IONS")
                if wanted:
                    yield index, head, peaks
                head = None
            elif head is None:
                raise ValueError(f"{path}:{number}: content outside MGF block")
            elif "=" in line:
                key, value = line.split("=", 1)
                if key.upper() in {"SMILES", "INCHIKEY", "ADDUCT", "PEPMASS",
                                   "COLLISION_ENERGY", "FORMULA", "CHARGE"}:
                    head[key.upper()] = value
            elif wanted and not headers_only:
                try:
                    mz, intensity = line.split()[:2]
                    peaks.append((float(mz), float(intensity)))
                except ValueError as exc:
                    raise ValueError(f"{path}:{number}: invalid peak") from exc
    if head is not None:
        raise ValueError(f"{path}: unterminated MGF block")
    if index < 0:
        raise ValueError(f"{path}: no MGF blocks")


def clean_peaks(peaks):
    values = np.asarray(peaks, dtype=np.float64).reshape(-1, 2)
    valid = np.isfinite(values).all(axis=1) & (values > 0).all(axis=1)
    values = values[valid]
    mz, inverse = np.unique(values[:, 0], return_inverse=True)
    intensity = np.bincount(inverse, weights=values[:, 1])
    if not np.isfinite(intensity).all():
        raise ValueError("Non-finite summed intensity")
    return mz, intensity / intensity.max() if len(intensity) else intensity


def read_exclusions(paths: list[Path]) -> tuple[set[str], list[dict]]:
    """Read canonical InChIKey14 lists; parquet means exclude every listed key."""
    keys, sources = set(), []
    for path in paths:
        if path.suffix == ".parquet":
            columns = pq.read_schema(path).names
            column = next((c for c in ("key", "inchikey14", "canonical_inchikey14") if c in columns), None)
            if column is None:
                raise ValueError(f"{path}: no canonical identity column")
            values = pq.read_table(path, columns=[column]).column(0).to_pylist()
        else:
            values = [s.strip() for s in path.read_text().splitlines()
                      if s.strip() and not s.lstrip().startswith("#")]
        if any(not isinstance(k, str) or not re.fullmatch(r"[A-Z]{14}", k) for k in values):
            raise ValueError(f"{path}: expected canonical 14-letter InChIKeys")
        keys.update(values)
        sources.append({"path": str(path.resolve()), "sha256": sha256(path), "identities": len(set(values))})
    return keys, sources


def convert_file(path: Path, out: Path, *, quantiles=(.25, .5, .8), max_structures=400,
                 min_peaks=3, seed=20261028, excluded=frozenset(), exclusion_sources=(), force=False):
    if max_structures < 1 or min_peaks < 1:
        raise ValueError("max_structures and min_peaks must be positive")
    if not quantiles or any(not math.isfinite(q) or not 0 <= q <= 1 for q in quantiles):
        raise ValueError("CE quantiles must be finite and within [0, 1]")
    if rdBase.rdkitVersion != "2026.03.3":
        raise RuntimeError(f"Official identity requires RDKit 2026.03.3, got {rdBase.rdkitVersion}")
    out.mkdir(parents=True, exist_ok=True)
    stem = path.name.removesuffix(".gz").removesuffix(".mgf")
    target, manifest = out / f"{stem}.parquet", out / f"{stem}.manifest.json"
    recipe = dict(version=2, source_sha256=sha256(path), converter_sha256=sha256(Path(__file__)),
                  rdkit=rdBase.rdkitVersion, quantiles=list(quantiles), max_structures=max_structures,
                  min_peaks=min_peaks, seed=seed,
                  exclusions_sha256=hashlib.sha256("\n".join(sorted(excluded)).encode()).hexdigest(),
                  supported_adduct="[M+H]+", selection="lowest SHA256(seed:canonical_identity)")
    if target.exists() or manifest.exists():
        if target.exists() and manifest.exists():
            old = json.loads(manifest.read_text())
            if old["recipe"] == recipe and old["output_sha256"] == sha256(target):
                return {**old, "cache_hit": True}
        if not force:
            raise ValueError(f"{target}: stale/incomplete shard; choose a new output directory or --force")

    acquisitions = defaultdict(dict)
    structures, normalized, counts, excluded_seen = {}, {}, Counter(), set()
    for index, head, _ in iter_mgf(path, headers_only=True):
        counts["input_spectra"] += 1
        smiles = head.get("SMILES", "")
        if smiles not in normalized:
            normalized[smiles] = normalize_structure(smiles)
        key, canonical, formula = normalized[smiles]
        if not key:
            counts["invalid_structure_spectra"] += 1
            continue
        if key in excluded:
            counts["excluded_identity_spectra"] += 1
            excluded_seen.add(key)
            continue
        if head.get("ADDUCT") != "[M+H]+" or head.get("CHARGE", "1+") != "1+":
            counts["unsupported_adduct_spectra"] += 1
            continue
        if head.get("FORMULA") != formula:
            counts["formula_mismatch_spectra"] += 1
            continue
        try:
            precursor = float(head["PEPMASS"].split()[0])
            ce = float(head["COLLISION_ENERGY"])
            if not math.isfinite(precursor) or precursor <= 0 or not math.isfinite(ce) or ce < 0:
                raise ValueError("Invalid precursor or energy")
        except (KeyError, ValueError, IndexError):
            counts["invalid_metadata_spectra"] += 1
            continue
        raw_key = head.get("INCHIKEY", "")[:14]
        if raw_key != key:
            counts["normalized_identity_changed_spectra"] += 1
        structures[key] = (canonical, formula)
        # A tautomer family gets one acquisition per CE, not extra sampling weight.
        candidate = (raw_key, smiles, index)
        previous = acquisitions[key].get(ce)
        if previous is None or candidate < previous:
            acquisitions[key][ce] = candidate

    keys = sorted(acquisitions, key=lambda k: hashlib.sha256(f"{seed}:{k}".encode()).digest())[:max_structures]
    selected = {}
    unstable = set()
    for key in keys:
        # Default RDKit enumeration limits can make canonicalization non-idempotent.
        # prepare.py canonicalizes these output SMILES again: reject any identity
        # that would change there rather than silently invalidating exclusions.
        if canonical_inchikey14(structures[key][0]) != key:
            unstable.add(key)
            continue
        energies = sorted(acquisitions[key])
        for i in sorted({round(q * (len(energies) - 1)) for q in quantiles}):
            selected[acquisitions[key][energies[i]][2]] = key

    rows = []
    for index, head, peaks in iter_mgf(path, selected=set(selected)):
        mz, intensity = clean_peaks(peaks)
        if len(mz) < min_peaks:
            counts["too_few_peaks_spectra"] += 1
            continue
        key = selected[index]
        canonical, formula = structures[key]
        rows.append(dict(normalized_smiles=canonical, smiles=canonical, inchikey14=key,
                         atlas_inchikey14=head.get("INCHIKEY", "")[:14], formula=formula,
                         ms2_mzs=mz.tolist(), ms2_normalized_intensities=intensity.tolist(),
                         precursor_mz=float(head["PEPMASS"].split()[0]), adduct=head["ADDUCT"],
                         ionization_mode="positive", collision_energy_ev=float(head["COLLISION_ENERGY"]),
                         ingest_lib="iceberg_atlas", instrument_type="ICEBERG",
                         molecule_id=f"iceberg_atlas:{key}", spectrum_id=f"{stem}:{index}", is_simulated=True))
    counts.update(eligible_structures=len(acquisitions), excluded_structures=len(excluded_seen),
                  selected_structures=len(keys), written_structures=len({r["inchikey14"] for r in rows}),
                  written_spectra=len(rows), cap_dropped_structures=max(0, len(acquisitions) - len(keys)),
                  unstable_identity_structures=len(unstable))
    temporary = target.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), temporary, compression="zstd")
    temporary.replace(target)
    report = dict(recipe=recipe, input=str(path.resolve()), output=str(target.resolve()),
                  output_sha256=sha256(target), output_bytes=target.stat().st_size,
                  exclusions=list(exclusion_sources), counts=dict(counts), cache_hit=False,
                  unstable_identities=sorted(unstable),
                  identity="stereo-stripped tautomer-canonical InChIKey14",
                  limitation="Simulated spectra, not experimental references. Per-formula cap is a training sample, not complete atlas coverage.")
    temporary = manifest.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(manifest)
    return report
