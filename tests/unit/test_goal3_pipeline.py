from __future__ import annotations

from casmi26.goal3_pipeline import (
    Goal3Dataset,
    Goal3ExperimentConfig,
    _catalog_for_mode,
)
from casmi26.mass_retrieval import StructureCandidate


def test_controlled_and_realistic_catalog_selection_are_distinct() -> None:
    candidates = tuple(
        StructureCandidate(
            candidate_id=f"ID{index:012d}",
            smiles="CC",
            exact_mass=30.0 + index,
            formula="C2H6",
        )
        for index in range(6)
    )
    frozen = (candidates[-1].candidate_id,)
    dataset = Goal3Dataset(
        spectra=(),
        source_catalog=candidates,
        source_candidate_ids=tuple(item.candidate_id for item in candidates),
        frozen_identity_keys=frozen,
        metadata={},
    )
    config = Goal3ExperimentConfig(
        controlled_catalog_size=2,
        realistic_catalog_size=2,
    )
    controlled, controlled_trace = _catalog_for_mode(dataset, "controlled", config)
    realistic, realistic_trace = _catalog_for_mode(dataset, "realistic", config)
    assert frozen[0] in {item.candidate_id for item in controlled}
    assert frozen[0] not in {item.candidate_id for item in realistic}
    assert controlled_trace.target_ids_consulted == frozen
    assert realistic_trace.target_ids_consulted == ()
