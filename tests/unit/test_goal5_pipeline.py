from __future__ import annotations

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from casmi26.candidate_catalogs import CatalogRecord
from casmi26.chemistry import canonical_inchikey14
from casmi26.domain_validation import make_domain_validation_plan
from casmi26.goal5_pipeline import (
    Goal5ExperimentConfig,
    _mass_anchor_order_for_union,
    collect_domain_spectra,
    evaluate_goal5_stage,
)
from casmi26.schemas import CandidateHit, ProcessedSpectrum


SMILES = ("CCO", "CCCO", "CCCCO", "CCN", "CCCN", "CCCCN", "CCOC", "CCNC")


def _catalog(smiles_values=SMILES) -> tuple[CatalogRecord, ...]:
    result = []
    for index, smiles in enumerate(smiles_values):
        molecule = Chem.MolFromSmiles(smiles)
        key = canonical_inchikey14(smiles)
        assert molecule is not None and key is not None
        result.append(
            CatalogRecord(
                candidate_id=key,
                inchikey14=key,
                smiles=smiles,
                exact_mass=float(Descriptors.ExactMolWt(molecule)),
                formula=rdMolDescriptors.CalcMolFormula(molecule),
                sources=("fixture",),
                source_ids=(f"row-{index}",),
            )
        )
    return tuple(result)


def _processed(
    spectrum_id: str,
    record: CatalogRecord,
    *,
    source: str,
    offset: float,
) -> ProcessedSpectrum:
    return ProcessedSpectrum(
        spectrum_id=spectrum_id,
        molecule_id=record.inchikey14,
        mz=np.asarray([20.0 + offset, 30.0 + offset, 40.0 + offset]),
        intensity=np.asarray([1.0, 0.7, 0.4]),
        precursor_mz=record.exact_mass + 1.007276466621,
        neutral_mass=record.exact_mass,
        adduct="[M+H]+",
        ion_mode="positive",
        collision_energy_ev=(20.0,),
        instrument="timsTOF",
        quality={"retained_fraction": 1.0},
        normalized_smiles=record.smiles,
        inchikey14=record.inchikey14,
        molecular_formula=record.formula,
        ingest_lib=source,
    )


def _domain_fixture():
    catalog = _catalog()
    spectra = []
    for index, record in enumerate(catalog[:5]):
        spectra.extend(
            [
                _processed(
                    f"q-{index}-1",
                    record,
                    source="enveda-np-examples",
                    offset=index + 0.01,
                ),
                _processed(
                    f"q-{index}-2",
                    record,
                    source="enveda-np-examples",
                    offset=index + 0.02,
                ),
                _processed(
                    f"r-{index}",
                    record,
                    source="other-library",
                    offset=index + 0.03,
                ),
            ]
        )
    for index, record in enumerate(catalog[5:], start=5):
        spectra.append(
            _processed(
                f"background-{index}",
                record,
                source="other-library",
                offset=index + 0.03,
            )
        )
    plan = make_domain_validation_plan(
        spectra,
        candidate_identity_keys=[item.inchikey14 for item in catalog],
        prior_final_identity_keys=("Z" * 14,),
        sealed_fraction=0.2,
        seed=2027,
    )
    return catalog, spectra, plan


def test_goal5_stage_keeps_index_equivalent_and_structure_absent_truth_absent() -> None:
    catalog, spectra, plan = _domain_fixture()
    results = evaluate_goal5_stage(
        plan,
        spectra,
        {"C0": catalog[:7], "C1": catalog},
        stage="development",
        config=Goal5ExperimentConfig(
            fixed_pool_size=5,
            dynamic_pool_size=7,
            cheap_stage_size=5,
            expensive_stage_size=3,
            analog_top_k=3,
            fingerprint_bits=64,
            bootstrap_samples=20,
        ),
    )
    for condition in results["conditions"].values():
        assert condition["evaluations"]["E8"] == condition["evaluations"]["E9"]
        assert condition["resources"]["E9"]["candidate_rows"] > 0
        assert condition["analog_index"]["reference_spectra"] > 0
    absent = results["conditions"]["C_structure_absent"]
    for experiment in ("E7", "E8", "E9", "E10", "E12"):
        assert absent["evaluations"][experiment]["pool_recall"] == 0.0


def test_collect_domain_spectra_reads_only_selected_identities(tmp_path) -> None:
    catalog = _catalog()[:4]
    rows = []
    for index, record in enumerate(catalog):
        for acquisition in range(2):
            rows.append(
                {
                    "spectrum_id": f"s-{index}-{acquisition}",
                    "molecule_id": record.inchikey14,
                    "ms2_mzs": [20.0, 30.0],
                    "ms2_normalized_intensities": [1.0, 0.5],
                    "precursor_mz": record.exact_mass + 1.007276466621,
                    "adduct": "[M+H]+",
                    "ionization_mode": "positive",
                    "collision_energy_ev": [20.0],
                    "instrument_type": "timsTOF",
                    "base_peak_intensity": 1000.0,
                    "normalized_smiles": record.smiles,
                    "inchikey14": record.inchikey14,
                    "molecular_formula": record.formula,
                    "ingest_lib": "enveda-np-examples" if index < 2 else "other",
                }
            )
    for acquisition in range(5):
        record = catalog[0]
        rows.append(
            {
                "spectrum_id": f"external-0-{acquisition}",
                "molecule_id": record.inchikey14,
                "ms2_mzs": [21.0 + acquisition, 31.0 + acquisition],
                "ms2_normalized_intensities": [1.0, 0.4],
                "precursor_mz": record.exact_mass + 1.007276466621,
                "adduct": "[M+H]+",
                "ionization_mode": "positive",
                "collision_energy_ev": [25.0],
                "instrument_type": "Orbitrap",
                "base_peak_intensity": 900.0,
                "normalized_smiles": record.smiles,
                "inchikey14": record.inchikey14,
                "molecular_formula": record.formula,
                "ingest_lib": "other-library",
            }
        )
    path = tmp_path / "train.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path)
    spectra, report = collect_domain_spectra(
        path,
        catalog_identity_keys=[item.inchikey14 for item in catalog],
        prior_final_identity_keys=("Z" * 14,),
        config=Goal5ExperimentConfig(
            background_reference_identities=1,
            spectra_per_background_identity=1,
            reference_spectra_per_domain_identity=2,
            fingerprint_bits=64,
        ),
    )
    assert report.scan_rows == len(rows)
    assert report.domain_identity_count == 2
    assert report.retained_domain_spectrum_count == 6
    assert report.retained_background_spectrum_count == 1
    assert len(spectra) == 7


def test_e12_mass_anchor_never_introduces_candidates_outside_union() -> None:
    def hit(candidate_id: str) -> CandidateHit:
        return CandidateHit(candidate_id, "C", "fixture", 1, 1.0, {})

    mass_hits = [hit("A"), hit("B"), hit("C"), hit("D")]
    union_hits = [hit("A"), hit("C"), hit("X")]
    order = _mass_anchor_order_for_union(mass_hits, union_hits)
    assert order == ["A", "C", "X"]
    assert set(order) == {item.candidate_id for item in union_hits}
