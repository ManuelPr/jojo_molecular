from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re

from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors
from rdkit.Chem.MolStandardize import rdMolStandardize


PROTON_MASS = 1.007276466621
WATER_MASS = 18.01056468403
AMMONIUM_MASS = 18.03382555335
SODIUM_ION_MASS = 22.989218
POTASSIUM_ION_MASS = 38.963158
FORMIC_ACID_MASS = 46.0054793036
CHLORIDE_ION_MASS = 34.969401261


@dataclass(frozen=True, slots=True)
class AdductSpec:
    multiplier: int
    charge: int
    mass_delta: float


ADDUCTS: dict[str, AdductSpec] = {
    "[M+H]+": AdductSpec(1, 1, PROTON_MASS),
    "[M+NH4]+": AdductSpec(1, 1, AMMONIUM_MASS),
    "[M-H2O+H]+": AdductSpec(1, 1, PROTON_MASS - WATER_MASS),
    "[M+H-H2O]+": AdductSpec(1, 1, PROTON_MASS - WATER_MASS),
    "[M-2H2O+H]+": AdductSpec(1, 1, PROTON_MASS - 2 * WATER_MASS),
    "[M+H-2H2O]+": AdductSpec(1, 1, PROTON_MASS - 2 * WATER_MASS),
    "[M+Na]+": AdductSpec(1, 1, SODIUM_ION_MASS),
    "[M+K]+": AdductSpec(1, 1, POTASSIUM_ION_MASS),
    "[M-H]-": AdductSpec(1, -1, -PROTON_MASS),
    "[M-H2O-H]-": AdductSpec(1, -1, -WATER_MASS - PROTON_MASS),
    "[M+CH2O2-H]-": AdductSpec(1, -1, FORMIC_ACID_MASS - PROTON_MASS),
    "[M+CHO2]-": AdductSpec(1, -1, FORMIC_ACID_MASS - PROTON_MASS),
    "[M+Cl]-": AdductSpec(1, -1, CHLORIDE_ION_MASS),
    "[M]+": AdductSpec(1, 1, 0.0),
    "[M]-": AdductSpec(1, -1, 0.0),
    "[M+2H]2+": AdductSpec(1, 2, 2 * PROTON_MASS),
    "[M-2H]2-": AdductSpec(1, -2, -2 * PROTON_MASS),
    "[2M+H]+": AdductSpec(2, 1, PROTON_MASS),
    "[2M+Na]+": AdductSpec(2, 1, SODIUM_ION_MASS),
    "[2M-H]-": AdductSpec(2, -1, -PROTON_MASS),
}


_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


def neutral_mass_from_mz(precursor_mz: float, adduct: str) -> float | None:
    """Convert precursor m/z to neutral monoisotopic mass.

    Unknown adducts return ``None`` rather than applying an unsafe proton-only
    approximation.
    """

    spec = ADDUCTS.get(adduct)
    if spec is None or not math.isfinite(precursor_mz) or precursor_mz <= 0:
        return None
    return (precursor_mz * abs(spec.charge) - spec.mass_delta) / spec.multiplier


def mz_from_neutral_mass(neutral_mass: float, adduct: str) -> float | None:
    spec = ADDUCTS.get(adduct)
    if spec is None or not math.isfinite(neutral_mass) or neutral_mass <= 0:
        return None
    return (neutral_mass * spec.multiplier + spec.mass_delta) / abs(spec.charge)


@lru_cache(maxsize=200_000)
def canonical_inchikey14(smiles: str) -> str | None:
    """Return the competition comparison key for a SMILES string.

    This mirrors the official scorer: parse with RDKit, canonicalize the
    tautomer with default ``TautomerEnumerator`` settings, then use the first
    block of the InChIKey.
    """

    if not isinstance(smiles, str) or not smiles.strip():
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        canonical = rdMolStandardize.TautomerEnumerator().Canonicalize(mol)
        key = Chem.MolToInchiKey(canonical)
        return key[:14] if key else None
    except Exception:
        return None


@lru_cache(maxsize=200_000)
def canonical_smiles(smiles: str) -> str | None:
    if not isinstance(smiles, str) or not smiles.strip():
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        canonical = rdMolStandardize.TautomerEnumerator().Canonicalize(mol)
        return Chem.MolToSmiles(canonical, canonical=True, isomericSmiles=True)
    except Exception:
        return None


@lru_cache(maxsize=200_000)
def exact_mass_from_smiles(smiles: str) -> float | None:
    """Return RDKit monoisotopic mass without using spectral observations."""

    if not isinstance(smiles, str) or not smiles.strip():
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return float(Descriptors.ExactMolWt(mol))
    except Exception:
        return None


@lru_cache(maxsize=200_000)
def exact_mass_from_formula(formula: str) -> float | None:
    """Compute neutral monoisotopic mass from a plain molecular formula.

    Competition formulas are simple element/count strings. Parentheses,
    isotope annotations, dot-disconnected adducts, and explicit charges fail
    closed so callers can fall back to structure-based calculation.
    """

    if not isinstance(formula, str) or not formula.strip():
        return None
    value = formula.strip()
    position = 0
    mass = 0.0
    periodic_table = Chem.GetPeriodicTable()
    for match in _FORMULA_TOKEN.finditer(value):
        if match.start() != position:
            return None
        symbol, raw_count = match.groups()
        atomic_number = int(periodic_table.GetAtomicNumber(symbol))
        if atomic_number <= 0:
            return None
        count = int(raw_count) if raw_count else 1
        if count <= 0:
            return None
        mass += float(periodic_table.GetMostCommonIsotopeMass(atomic_number)) * count
        position = match.end()
    if position != len(value) or position == 0 or not math.isfinite(mass):
        return None
    return mass


def rdkit_version() -> str:
    return rdBase.rdkitVersion
