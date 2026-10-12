from __future__ import annotations

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from casmi26.analog_propagation import AnalogReference
from casmi26.candidate_catalogs import CatalogRecord
from casmi26.chemistry import canonical_inchikey14
from casmi26.recovery_inference import (
    RecoveryInferenceConfig,
    predict_frozen_e6_on_c1,
)
from casmi26.goal4_pipeline import Goal4ExperimentConfig
from casmi26.scalable_retrieval import ScalableMassFormulaIndex
from casmi26.schemas import ProcessedSpectrum


def _record(smiles: str) -> CatalogRecord:
    molecule = Chem.MolFromSmiles(smiles)
    key = canonical_inchikey14(smiles)
    assert molecule is not None and key is not None
    return CatalogRecord(
        candidate_id=key,
        inchikey14=key,
        smiles=smiles,
        exact_mass=float(Descriptors.ExactMolWt(molecule)),
        formula=rdMolDescriptors.CalcMolFormula(molecule),
        sources=("fixture",),
    )


def _spectrum(identifier: str, mass: float, peak: float) -> ProcessedSpectrum:
    return ProcessedSpectrum(
        spectrum_id=identifier,
        molecule_id=identifier,
        mz=np.asarray([peak, peak + 10.0], dtype=np.float32),
        intensity=np.asarray([1.0, 0.5], dtype=np.float32),
        precursor_mz=mass + 1.007276466621,
        neutral_mass=mass,
        adduct="[M+H]+",
        ion_mode="positive",
        collision_energy_ev=(20.0,),
        instrument="fixture",
        quality={"retained_fraction": 1.0},
    )


def test_recovery_c1_ranking_is_bounded_and_has_no_fallback() -> None:
    records = tuple(_record(smiles) for smiles in ("CCO", "CCN", "CCC"))
    index = ScalableMassFormulaIndex.build(records, tier_name="C1_train_unique")
    reference_spectrum = _spectrum("reference", records[0].exact_mass, 20.0)
    reference = AnalogReference(
        reference_id="reference",
        structure_id=records[0].inchikey14,
        inchikey14=records[0].inchikey14,
        neutral_mass=records[0].exact_mass,
        spectrum=reference_spectrum,
        fingerprint=np.zeros(64, dtype=np.float32),
        formula=records[0].formula,
        source="fixture",
    )
    predictions, report = predict_frozen_e6_on_c1(
        {"query": [_spectrum("query", records[0].exact_mass, 21.0)]},
        index,
        [reference],
        config=RecoveryInferenceConfig(
            realistic_catalog_size=1,
            retrieval_pool_size=3,
            output_size=2,
            fingerprint_bits=64,
            expected_c1_structure_count=3,
        ),
    )
    assert len(predictions["query"]) == 2
    assert report["query_count"] == 1
    assert report["per_query"]["query"]["retrieved_candidates"] == 3


def test_recovery_refuses_wrong_c1_artifact() -> None:
    records = tuple(_record(smiles) for smiles in ("CCO", "CCN", "CCC"))
    index = ScalableMassFormulaIndex.build(records, tier_name="C1_train_unique")
    with pytest.raises(RuntimeError, match="Unexpected C1 structure count"):
        predict_frozen_e6_on_c1(
            {},
            index,
            [object()],
            config=RecoveryInferenceConfig(
                realistic_catalog_size=1,
                retrieval_pool_size=2,
                output_size=1,
                expected_c1_structure_count=4,
            ),
        )


def test_recovery_reference_sampling_matches_frozen_goal4_e6() -> None:
    assert (
        RecoveryInferenceConfig().spectra_per_identity
        == Goal4ExperimentConfig().spectra_per_identity
        == 3
    )
