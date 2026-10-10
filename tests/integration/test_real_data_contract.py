from pathlib import Path

import pytest

from casmi26.data import ParquetSpectrumReader, preprocess_spectrum


@pytest.mark.real_data
def test_competition_parquet_contract_and_preprocessing() -> None:
    train_path = Path("data/train.parquet")
    test_path = Path("data/test.parquet")
    if not train_path.is_file() or not test_path.is_file():
        pytest.skip("Competition parquet files are not available")

    train_reader = ParquetSpectrumReader(train_path)
    test_reader = ParquetSpectrumReader(test_path)
    assert train_reader.is_train
    assert not test_reader.is_train
    assert train_reader.num_rows == 2_539_608
    assert test_reader.num_rows == 1_213

    for reader in (train_reader, test_reader):
        processed = [preprocess_spectrum(record) for record in reader.iter_records(max_rows=16)]
        assert len(processed) == 16
        assert all(spectrum.mz.size == spectrum.intensity.size for spectrum in processed)
        assert all(spectrum.precursor_mz > 0 for spectrum in processed)

