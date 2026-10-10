from __future__ import annotations

import numpy as np
import pytest

from casmi26.goal3_contracts import CandidatePoolAudit, FingerprintSpec, SpectrumBatch


def test_fingerprint_specs_validate_fixed_dimensions() -> None:
    assert FingerprintSpec().n_bits == 512
    assert FingerprintSpec(kind="maccs", n_bits=167).kind == "maccs"
    with pytest.raises(ValueError, match="167"):
        FingerprintSpec(kind="maccs", n_bits=512)


def test_spectrum_batch_validates_all_shapes() -> None:
    batch = SpectrumBatch(
        mz=np.zeros((2, 4), dtype=np.float32),
        intensity=np.zeros((2, 4), dtype=np.float32),
        neutral_loss=np.zeros((2, 4), dtype=np.float32),
        peak_mask=np.ones((2, 4), dtype=bool),
        precursor_mass=np.zeros(2, dtype=np.float32),
        collision_energy=np.zeros(2, dtype=np.float32),
        adduct_index=np.zeros(2, dtype=np.int64),
        ion_mode_index=np.zeros(2, dtype=np.int64),
    )
    assert batch.mz.shape == (2, 4)
    with pytest.raises(ValueError, match="intensity"):
        SpectrumBatch(
            mz=batch.mz,
            intensity=np.zeros((2, 3), dtype=np.float32),
            neutral_loss=batch.neutral_loss,
            peak_mask=batch.peak_mask,
            precursor_mass=batch.precursor_mass,
            collision_energy=batch.collision_energy,
            adduct_index=batch.adduct_index,
            ion_mode_index=batch.ion_mode_index,
        )


def test_candidate_pool_audit_rates() -> None:
    audit = CandidatePoolAudit(
        mode="realistic",
        query_count=4,
        catalog_size=100,
        target_in_catalog_count=3,
        target_in_pool_count=2,
        target_in_top25_count=1,
        explicit_target_injection_count=0,
        median_pool_size=50.0,
        median_same_formula_competitors=2.0,
        median_exact_mass_competitors=1.0,
    )
    assert audit.catalog_recall == 0.75
    assert audit.pool_recall == 0.5
    assert audit.recall_at_25 == 0.25
