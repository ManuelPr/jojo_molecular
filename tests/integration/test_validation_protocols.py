from __future__ import annotations

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from casmi26.chemistry import (
    PROTON_MASS,
    canonical_inchikey14,
    exact_mass_from_smiles,
)
from casmi26.schemas import ProcessedSpectrum
from casmi26.validation_pipeline import (
    ValidationExperimentConfig,
    evaluate_validation_spectra,
)


def _fixture_spectra() -> list[ProcessedSpectrum]:
    smiles_values = ["C" * length for length in range(2, 14)]
    spectra: list[ProcessedSpectrum] = []
    for identity_index, smiles in enumerate(smiles_values):
        key = canonical_inchikey14(smiles)
        exact_mass = exact_mass_from_smiles(smiles)
        mol = Chem.MolFromSmiles(smiles)
        assert key is not None and exact_mass is not None and mol is not None
        formula = rdMolDescriptors.CalcMolFormula(mol)
        for acquisition in range(3):
            mz = np.asarray(
                [
                    15.0 + identity_index,
                    25.0 + 2 * identity_index + acquisition * 0.001,
                    35.0 + 3 * identity_index,
                ],
                dtype=np.float32,
            )
            intensity = np.asarray([0.8, 0.5, 0.2], dtype=np.float32)
            intensity /= np.linalg.norm(intensity)
            spectra.append(
                ProcessedSpectrum(
                    spectrum_id=f"s-{identity_index}-{acquisition}",
                    molecule_id=key,
                    mz=mz,
                    intensity=intensity,
                    precursor_mz=exact_mass + PROTON_MASS,
                    neutral_mass=exact_mass,
                    adduct="[M+H]+",
                    ion_mode="positive",
                    collision_energy_ev=(10.0 + acquisition,),
                    instrument="QTOF",
                    quality={"retained_peak_count": 3.0},
                    normalized_smiles=smiles,
                    inchikey14=key,
                    molecular_formula=formula,
                    ingest_lib="synthetic",
                )
            )
    return spectra


def test_three_validation_protocols_run_end_to_end(tmp_path) -> None:
    results = evaluate_validation_spectra(
        _fixture_spectra(),
        tmp_path,
        config=ValidationExperimentConfig(
            max_identities=12,
            max_scan_rows=100,
            validation_fraction=0.34,
            candidate_pool_size=100,
            bootstrap_samples=20,
        ),
    )

    assert set(results["protocols"]) == {
        "library_holdout",
        "molecule_disjoint",
        "novelty_holdout",
    }
    for protocol in results["protocols"].values():
        assert protocol["audit"]["passed"] is True
        assert protocol["evaluations"]["model_selection"]["supervised_ranker"]
        assert protocol["evaluations"]["final_evaluation"]["supervised_ranker"]

    known = results["protocols"]["molecule_disjoint"]["evaluations"]["all_validation"]
    novel = results["protocols"]["novelty_holdout"]["evaluations"]["all_validation"]
    assert known["nearest_mass"]["metrics"]["pool_recall"] == 1.0
    assert novel["nearest_mass"]["metrics"]["pool_recall"] == 0.0
    assert (tmp_path / "validation_results.json").is_file()
    assert len(list((tmp_path / "split_manifests").glob("*.json"))) == 3
