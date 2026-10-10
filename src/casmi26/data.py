from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .chemistry import neutral_mass_from_mz
from .schemas import ProcessedSpectrum, SpectrumRecord


SHARED_COLUMNS = {
    "ms2_mzs",
    "ms2_normalized_intensities",
    "precursor_mz",
    "adduct",
    "ionization_mode",
    "collision_energy_ev",
    "instrument_type",
    "base_peak_intensity",
}

TRAIN_LABEL_COLUMNS = {
    "normalized_smiles",
    "inchikey14",
    "molecular_formula",
    "ingest_lib",
}


@dataclass(frozen=True, slots=True)
class PreprocessConfig:
    intensity_floor: float = 0.001
    max_peaks: int = 256
    precursor_margin_da: float = 2.0
    intensity_transform: str = "sqrt"


class ParquetSpectrumReader:
    """Streaming reader for both competition train and test parquet files."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self._file = pq.ParquetFile(self.path)
        names = set(self._file.schema_arrow.names)
        missing = SHARED_COLUMNS - names
        if missing:
            raise ValueError(f"Missing required spectrum columns: {sorted(missing)}")
        self.is_train = TRAIN_LABEL_COLUMNS.issubset(names)

    @property
    def num_rows(self) -> int:
        return self._file.metadata.num_rows

    @property
    def schema(self) -> pa.Schema:
        return self._file.schema_arrow

    def iter_records(
        self,
        *,
        batch_size: int = 8_192,
        max_rows: int | None = None,
        columns: Sequence[str] | None = None,
    ) -> Iterator[SpectrumRecord]:
        available = set(self.schema.names)
        default_columns = [
            "molecule_id" if "molecule_id" in available else None,
            "spectrum_id" if "spectrum_id" in available else None,
            "ms2_mzs",
            "ms2_normalized_intensities",
            "precursor_mz",
            "adduct",
            "ionization_mode",
            "collision_energy_ev",
            "instrument_type",
            "base_peak_intensity",
            "normalized_smiles" if "normalized_smiles" in available else None,
            "inchikey14" if "inchikey14" in available else None,
            "molecular_formula" if "molecular_formula" in available else None,
            "ingest_lib" if "ingest_lib" in available else None,
        ]
        selected = list(columns) if columns is not None else [c for c in default_columns if c]
        unknown = set(selected) - available
        if unknown:
            raise ValueError(f"Unknown parquet columns: {sorted(unknown)}")

        emitted = 0
        for batch in self._file.iter_batches(batch_size=batch_size, columns=selected):
            for row in batch.to_pylist():
                if max_rows is not None and emitted >= max_rows:
                    return
                emitted += 1
                yield self._row_to_record(row, emitted)

    def _row_to_record(self, row: dict, row_number: int) -> SpectrumRecord:
        molecule_id = row.get("molecule_id") or row.get("inchikey14") or f"row_{row_number}"
        spectrum_id = row.get("spectrum_id") or f"{molecule_id}_{row_number}"
        energies = row.get("collision_energy_ev") or ()
        base_peak = row.get("base_peak_intensity")
        return SpectrumRecord(
            spectrum_id=str(spectrum_id),
            molecule_id=str(molecule_id),
            mz=np.asarray(row.get("ms2_mzs") or (), dtype=np.float64),
            intensity=np.asarray(row.get("ms2_normalized_intensities") or (), dtype=np.float64),
            precursor_mz=float(row.get("precursor_mz") or math.nan),
            adduct=str(row.get("adduct") or ""),
            ion_mode=str(row.get("ionization_mode") or ""),
            collision_energy_ev=tuple(float(v) for v in energies if v is not None),
            instrument=row.get("instrument_type"),
            base_peak_intensity=float(base_peak) if base_peak is not None else None,
            normalized_smiles=row.get("normalized_smiles"),
            inchikey14=row.get("inchikey14"),
            molecular_formula=row.get("molecular_formula"),
            ingest_lib=row.get("ingest_lib"),
        )


def preprocess_spectrum(
    record: SpectrumRecord,
    config: PreprocessConfig = PreprocessConfig(),
) -> ProcessedSpectrum:
    mz = np.asarray(record.mz, dtype=np.float64)
    intensity = np.asarray(record.intensity, dtype=np.float64)
    if mz.ndim != 1 or intensity.ndim != 1 or mz.size != intensity.size:
        raise ValueError(f"Misaligned peak arrays for {record.spectrum_id}")
    if not math.isfinite(record.precursor_mz) or record.precursor_mz <= 0:
        raise ValueError(f"Invalid precursor m/z for {record.spectrum_id}")

    input_peaks = mz.size
    mask = np.isfinite(mz) & np.isfinite(intensity) & (mz > 0) & (intensity >= 0)
    mask &= mz <= record.precursor_mz + config.precursor_margin_da
    mz = mz[mask]
    intensity = intensity[mask]

    if intensity.size:
        max_intensity = float(intensity.max())
        if max_intensity > 0:
            intensity = intensity / max_intensity
        mask = intensity >= config.intensity_floor
        mz, intensity = mz[mask], intensity[mask]

    if mz.size:
        order = np.argsort(mz, kind="stable")
        mz, intensity = mz[order], intensity[order]
        unique_mz, inverse = np.unique(mz, return_inverse=True)
        if unique_mz.size != mz.size:
            merged = np.zeros(unique_mz.size, dtype=np.float64)
            np.maximum.at(merged, inverse, intensity)
            mz, intensity = unique_mz, merged

    if config.max_peaks > 0 and mz.size > config.max_peaks:
        top = np.argpartition(intensity, -config.max_peaks)[-config.max_peaks:]
        top = top[np.argsort(mz[top], kind="stable")]
        mz, intensity = mz[top], intensity[top]

    if config.intensity_transform == "sqrt":
        intensity = np.sqrt(intensity)
    elif config.intensity_transform == "log1p":
        intensity = np.log1p(1000.0 * intensity)
    elif config.intensity_transform != "none":
        raise ValueError(f"Unknown intensity transform: {config.intensity_transform}")

    if intensity.size:
        norm = float(np.linalg.norm(intensity))
        if norm > 0:
            intensity = intensity / norm

    return ProcessedSpectrum(
        spectrum_id=record.spectrum_id,
        molecule_id=record.molecule_id,
        mz=mz.astype(np.float32, copy=False),
        intensity=intensity.astype(np.float32, copy=False),
        precursor_mz=record.precursor_mz,
        neutral_mass=neutral_mass_from_mz(record.precursor_mz, record.adduct),
        adduct=record.adduct,
        ion_mode=record.ion_mode,
        collision_energy_ev=record.collision_energy_ev,
        instrument=record.instrument,
        quality={
            "input_peak_count": float(input_peaks),
            "retained_peak_count": float(mz.size),
            "retained_fraction": float(mz.size / input_peaks) if input_peaks else 0.0,
            "base_peak_intensity": float(record.base_peak_intensity or 0.0),
        },
        normalized_smiles=record.normalized_smiles,
        inchikey14=record.inchikey14,
        molecular_formula=record.molecular_formula,
        ingest_lib=record.ingest_lib,
    )


def read_processed(
    path: str | Path,
    *,
    config: PreprocessConfig = PreprocessConfig(),
    max_rows: int | None = None,
) -> Iterator[ProcessedSpectrum]:
    for record in ParquetSpectrumReader(path).iter_records(max_rows=max_rows):
        yield preprocess_spectrum(record, config)

