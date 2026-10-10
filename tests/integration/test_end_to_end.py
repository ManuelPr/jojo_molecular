from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from rdkit import Chem

from casmi26.chemistry import canonical_inchikey14
from casmi26.pipeline import MiniTrainConfig, run_mini_training
from casmi26.submission import validate_submission


SMILES = [
    "CCO",
    "CCN",
    "CCC",
    "CCCl",
    "CCBr",
    "CC(=O)O",
    "CC(C)O",
    "c1ccccc1",
    "c1ccncc1",
    "CCOC",
    "CCS",
    "CC#N",
]


def _train_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, smiles in enumerate(SMILES):
        key = canonical_inchikey14(smiles)
        assert key is not None
        signature = [50.0 + idx, 90.0 + idx * 0.7, 130.0 + idx * 0.3]
        for replicate in range(2):
            shift = 0.003 * replicate
            rows.append(
                {
                    "ingest_lib": "synthetic",
                    "normalized_smiles": smiles,
                    "inchikey": Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)),
                    "inchikey14": key,
                    "molecular_formula": f"SYN{idx}",
                    "ionization_mode": "positive",
                    "instrument_type": "timsTOF",
                    "adduct": "[M+H]+",
                    "adduct_orig": "[M+H]+",
                    "precursor_mz": 250.0,
                    "precursor_error_ppm": 0.0,
                    "ms2_mzs": [value + shift for value in signature],
                    "ms2_normalized_intensities": [1.0, 0.6, 0.25],
                    "num_peaks": 3,
                    "base_peak_intensity": 10000.0,
                    "collision_energy_ev": [20.0 + 10 * replicate],
                    "collision_energy_orig": str(20 + 10 * replicate),
                    "collision_energy_orig_units": "eV",
                }
            )
    return rows


def _test_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(3):
        rows.append(
            {
                "molecule_id": f"m_{idx}",
                "spectrum_id": f"s_{idx}",
                "ms2_mzs": [50.001 + idx, 90.001 + idx * 0.7, 130.001 + idx * 0.3],
                "ms2_normalized_intensities": [1.0, 0.6, 0.25],
                "base_peak_intensity": 10000.0,
                "adduct": "[M+H]+",
                "ionization_mode": "positive",
                "instrument_type": "timsTOF",
                "precursor_mz": 250.0,
                "collision_energy_orig": "20",
                "collision_energy_ev": [20.0],
                "collision_energy_orig_units": "eV",
            }
        )
    return rows


@pytest.mark.integration
def test_end_to_end_mini_pipeline(tmp_path: Path) -> None:
    train_path = tmp_path / "train.parquet"
    test_path = tmp_path / "test.parquet"
    output = tmp_path / "run"
    pq.write_table(pa.Table.from_pylist(_train_rows()), train_path)
    pq.write_table(pa.Table.from_pylist(_test_rows()), test_path)

    metrics = run_mini_training(
        train_path,
        test_path,
        output,
        config=MiniTrainConfig(
            max_molecules=12,
            max_scan_rows=100,
            top_k=12,
            validation_fraction=0.25,
        ),
    )
    assert metrics["library_molecules"] == 12
    assert metrics["training"]["positive_count"] > 0
    assert metrics["retrieval"]["recall_at_25"] == 1.0
    assert Path(output / "ranker.joblib").is_file()
    assert Path(output / "metrics.json").is_file()
    assert validate_submission(
        output / "submission.csv",
        expected_molecule_ids=["m_0", "m_1", "m_2"],
    ).valid

