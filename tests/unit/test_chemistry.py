import math

import pytest

from casmi26.chemistry import (
    ADDUCTS,
    canonical_inchikey14,
    exact_mass_from_smiles,
    exact_mass_from_formula,
    mz_from_neutral_mass,
    neutral_mass_from_mz,
    rdkit_version,
)


TEN_TEST_ADDUCTS = [
    "[M+H]+",
    "[M+NH4]+",
    "[M-H2O+H]+",
    "[M-2H2O+H]+",
    "[M+Na]+",
    "[M+K]+",
    "[M-H]-",
    "[M-H2O-H]-",
    "[M+CH2O2-H]-",
    "[M+Cl]-",
]

TRAIN_MULTIMER_ADDUCTS = ["[2M+H]+", "[2M+Na]+", "[2M-H]-"]


@pytest.mark.parametrize("adduct", TEN_TEST_ADDUCTS)
def test_adduct_mass_round_trip(adduct: str) -> None:
    assert adduct in ADDUCTS
    expected_mass = 348.123456
    mz = mz_from_neutral_mass(expected_mass, adduct)
    assert mz is not None
    actual_mass = neutral_mass_from_mz(mz, adduct)
    assert actual_mass == pytest.approx(expected_mass, abs=1e-9)


@pytest.mark.parametrize("adduct", TRAIN_MULTIMER_ADDUCTS)
def test_train_multimer_adduct_mass_round_trip(adduct: str) -> None:
    expected_mass = 348.123456
    mz = mz_from_neutral_mass(expected_mass, adduct)
    assert mz is not None
    assert neutral_mass_from_mz(mz, adduct) == pytest.approx(expected_mass, abs=1e-9)


def test_unknown_adduct_fails_closed() -> None:
    assert neutral_mass_from_mz(100.0, "[M+MAGIC]+") is None


def test_exact_mass_is_derived_from_structure() -> None:
    assert exact_mass_from_smiles("O") == pytest.approx(18.010564684, abs=1e-8)
    assert exact_mass_from_smiles("not-a-smiles") is None


def test_exact_mass_from_formula_matches_structure_and_fails_closed() -> None:
    assert exact_mass_from_formula("C2H6O") == pytest.approx(
        exact_mass_from_smiles("CCO"), abs=1e-8
    )
    assert exact_mass_from_formula("C6H12O6") == pytest.approx(180.063388104, abs=1e-8)
    assert exact_mass_from_formula("C6H12O6+") is None
    assert exact_mass_from_formula("C0H2") is None


def test_tautomer_canonical_key_and_invalid_smiles() -> None:
    assert canonical_inchikey14("CCO") == canonical_inchikey14("OCC")
    assert canonical_inchikey14("not-a-smiles") is None


def test_exact_competition_rdkit_version() -> None:
    assert rdkit_version() == "2026.03.3"
