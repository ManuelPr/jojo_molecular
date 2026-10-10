from __future__ import annotations

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from casmi26.chemistry import PROTON_MASS, canonical_inchikey14, exact_mass_from_smiles
from casmi26.fingerprints import molecular_fingerprint
from casmi26.goal3_contracts import FingerprintSpec
from casmi26.goal3_pipeline import (
    Goal3Dataset,
    Goal3ExperimentConfig,
    run_goal3_experiment,
)
from casmi26.goal3_training import OOFFingerprintResult
from casmi26.mass_retrieval import StructureCandidate
from casmi26.schemas import ProcessedSpectrum


def _dataset() -> Goal3Dataset:
    structures = []
    spectra = []
    for index, length in enumerate(range(2, 14)):
        smiles = "C" * length
        key = canonical_inchikey14(smiles)
        mass = exact_mass_from_smiles(smiles)
        molecule = Chem.MolFromSmiles(smiles)
        assert key is not None and mass is not None and molecule is not None
        formula = rdMolDescriptors.CalcMolFormula(molecule)
        structures.append(StructureCandidate(key, smiles, mass, formula, "synthetic"))
        for acquisition in range(3):
            mz = np.asarray(
                [15.0 + index, 25.0 + index + acquisition * 0.001, 35.0 + index],
                dtype=np.float32,
            )
            intensity = np.asarray([0.8, 0.5, 0.2], dtype=np.float32)
            intensity /= np.linalg.norm(intensity)
            spectra.append(
                ProcessedSpectrum(
                    spectrum_id=f"s-{index}-{acquisition}",
                    molecule_id=key,
                    mz=mz,
                    intensity=intensity,
                    precursor_mz=mass + PROTON_MASS,
                    neutral_mass=mass,
                    adduct="[M+H]+",
                    ion_mode="positive",
                    collision_energy_ev=(10.0 + acquisition,),
                    instrument="fixture",
                    quality={"retained_peak_count": 3.0},
                    normalized_smiles=smiles,
                    inchikey14=key,
                    molecular_formula=formula,
                    ingest_lib="synthetic",
                )
            )
    return Goal3Dataset(
        spectra=tuple(spectra),
        source_catalog=tuple(structures),
        source_candidate_ids=tuple(item.candidate_id for item in structures),
        frozen_identity_keys=tuple(item.candidate_id for item in structures),
        metadata={"fixture": True},
    )


def test_goal3_e0_e6_pipeline_with_strict_oof_contract(monkeypatch, tmp_path) -> None:
    dataset = _dataset()

    def fake_collect(*_args, **_kwargs):
        return dataset

    def fake_oof(train_spectra, train_targets, _groups, validation_spectra, **_kwargs):
        validation = np.stack(
            [
                molecular_fingerprint(
                    spectrum.normalized_smiles or "", FingerprintSpec(n_bits=64)
                )
                for spectrum in validation_spectra
            ]
        ).astype(np.float32)
        return OOFFingerprintResult(
            oof_probabilities=train_targets * 0.8 + 0.1,
            validation_probabilities=validation * 0.8 + 0.1,
            fold_reports=({"best_epoch": 1, "elapsed_seconds": 0.01},),
            final_report={"best_epoch": 1, "elapsed_seconds": 0.01},
            fold_by_group={str(value): index % 3 for index, value in enumerate(sorted(set(_groups)))},
        )

    monkeypatch.setattr("casmi26.goal3_pipeline.collect_goal3_dataset", fake_collect)
    monkeypatch.setattr("casmi26.goal3_pipeline.oof_fingerprint_predictions", fake_oof)
    results = run_goal3_experiment(
        "unused.parquet",
        "unused.txt",
        tmp_path,
        config=Goal3ExperimentConfig(
            controlled_catalog_size=12,
            realistic_catalog_size=12,
            candidate_pool_size=12,
            fingerprint_bits=64,
            fingerprint_epochs=1,
            fingerprint_batch_size=4,
            bootstrap_samples=10,
            hard_negatives_per_query=8,
            device="cpu",
        ),
    )
    assert results["leakage_audit"]["passed"] is True
    assert results["modes"]["realistic"]["benchmark_audit"]["violations"] == []
    for mode in ("controlled", "realistic"):
        final = results["modes"][mode]["evaluations"]["final_evaluation"]
        assert {"E0", "E1", "E2", "E3", "E4", "E5"} <= set(final)
        assert any(key.startswith("E6_") for key in final)
        for resource in results["modes"][mode]["experiment_resources"].values():
            assert resource["elapsed_seconds"] >= 0.0
            assert "max_observed_rss_bytes" in resource
            assert "peak_vram_bytes_since_process_start" in resource
    assert (tmp_path / "goal3_results.json").is_file()
