from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from casmi26.data import ParquetSpectrumReader, PreprocessConfig, preprocess_spectrum
from casmi26.schemas import SpectrumRecord


def test_preprocess_filters_sorts_merges_and_limits_peaks() -> None:
    record = SpectrumRecord(
        spectrum_id="s1",
        molecule_id="m1",
        mz=np.asarray([105.0, 50.0, 50.0, np.nan, 250.0, 75.0]),
        intensity=np.asarray([0.5, 1.0, 0.2, 0.3, 1.0, 0.001]),
        precursor_mz=200.0,
        adduct="[M+H]+",
        ion_mode="positive",
    )
    result = preprocess_spectrum(
        record,
        PreprocessConfig(intensity_floor=0.01, max_peaks=10, intensity_transform="none"),
    )
    assert result.mz.tolist() == [50.0, 105.0]
    assert np.linalg.norm(result.intensity) == pytest.approx(1.0)
    assert result.neutral_mass is not None
    assert result.quality["input_peak_count"] == 6.0


def test_preprocess_rejects_misaligned_arrays() -> None:
    record = SpectrumRecord(
        spectrum_id="bad",
        molecule_id="m1",
        mz=np.asarray([1.0, 2.0]),
        intensity=np.asarray([1.0]),
        precursor_mz=100.0,
        adduct="[M+H]+",
        ion_mode="positive",
    )
    with pytest.raises(ValueError, match="Misaligned"):
        preprocess_spectrum(record)


def test_parquet_reader_supports_test_schema(tmp_path: Path) -> None:
    path = tmp_path / "test.parquet"
    table = pa.Table.from_pylist(
        [
            {
                "molecule_id": "m1",
                "spectrum_id": "s1",
                "ms2_mzs": [50.0, 75.0],
                "ms2_normalized_intensities": [1.0, 0.5],
                "base_peak_intensity": 1000.0,
                "adduct": "[M+H]+",
                "ionization_mode": "positive",
                "instrument_type": "timsTOF",
                "precursor_mz": 101.0,
                "collision_energy_orig": "20",
                "collision_energy_ev": [20.0],
                "collision_energy_orig_units": "eV",
            }
        ]
    )
    pq.write_table(table, path)
    reader = ParquetSpectrumReader(path)
    records = list(reader.iter_records())
    assert reader.num_rows == 1
    assert not reader.is_train
    assert records[0].molecule_id == "m1"
    assert records[0].collision_energy_ev == (20.0,)

