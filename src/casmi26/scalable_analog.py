"""Indexed prefilter for Goal 4 analog propagation.

The expensive spectral scorer is unchanged.  This module only replaces its
linear scan over every reference with an exact sorted-neutral-mass lookup, so
the returned ranking is equivalent to the Goal 4 implementation for the same
mass window and leakage policy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
import math
import time

import numpy as np

from .analog_propagation import (
    AnalogHit,
    AnalogLeakageError,
    AnalogReference,
    LeakagePolicy,
    retrieve_analogs,
    spectrum_content_hash,
)
from .schemas import ProcessedSpectrum


@dataclass(frozen=True, slots=True)
class IndexedAnalogReport:
    total_reference_spectra: int
    total_reference_identities: int
    mass_window_reference_spectra: int
    scored_reference_spectra: int
    reduction_fraction: float
    returned_analogs: int
    elapsed_seconds: float
    backend: str = "numpy_searchsorted_exact_mass_prefilter"

    def to_dict(self) -> dict[str, int | float | str]:
        return asdict(self)


class ScalableAnalogIndex:
    """Immutable exact mass index over an analog spectral library."""

    def __init__(self, references: Sequence[AnalogReference]) -> None:
        if not references:
            raise ValueError("At least one analog reference is required")
        reference_ids = [reference.reference_id for reference in references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("Analog reference ids must be unique")
        for reference in references:
            if not math.isfinite(reference.neutral_mass) or reference.neutral_mass <= 0.0:
                raise ValueError(
                    f"Invalid neutral mass for analog reference {reference.reference_id}"
                )
        self._references = tuple(
            sorted(
                references,
                key=lambda item: (
                    item.neutral_mass,
                    item.inchikey14,
                    item.reference_id,
                ),
            )
        )
        self._masses = np.asarray(
            [reference.neutral_mass for reference in self._references],
            dtype=np.float64,
        )
        self._identities = frozenset(
            reference.inchikey14 for reference in self._references
        )
        self._content_hashes = frozenset(
            spectrum_content_hash(reference.spectrum) for reference in self._references
        )

    def __len__(self) -> int:
        return len(self._references)

    @property
    def identity_count(self) -> int:
        return len(self._identities)

    @property
    def masses(self) -> np.ndarray:
        view = self._masses.view()
        view.flags.writeable = False
        return view

    def _assert_policy(self, policy: LeakagePolicy) -> None:
        forbidden_identities = self._identities & policy.forbidden_inchikey14
        if forbidden_identities:
            example = min(forbidden_identities)
            raise AnalogLeakageError(
                f"Forbidden holdout identity in indexed analog library: {example}"
            )
        if (
            not policy.allow_same_identity
            and policy.query_inchikey14
            and policy.query_inchikey14 in self._identities
        ):
            raise AnalogLeakageError(
                "Query identity in identity-disjoint indexed analog library: "
                f"{policy.query_inchikey14}"
            )
        forbidden_content = self._content_hashes & policy.forbidden_spectrum_hashes
        if forbidden_content:
            raise AnalogLeakageError(
                "Forbidden holdout spectrum content in indexed analog library"
            )

    def window(
        self,
        neutral_mass: float,
        *,
        mass_window_da: float,
    ) -> tuple[AnalogReference, ...]:
        if not math.isfinite(neutral_mass) or neutral_mass <= 0.0:
            raise ValueError("neutral_mass must be finite and positive")
        if not math.isfinite(mass_window_da) or mass_window_da <= 0.0:
            raise ValueError("mass_window_da must be finite and positive")
        left = int(np.searchsorted(self._masses, neutral_mass - mass_window_da, side="left"))
        right = int(np.searchsorted(self._masses, neutral_mass + mass_window_da, side="right"))
        return self._references[left:right]

    def retrieve(
        self,
        query_spectra: Sequence[ProcessedSpectrum],
        *,
        query_neutral_mass: float,
        policy: LeakagePolicy,
        mass_window_da: float = 200.0,
        top_k: int = 80,
        tolerance_da: float = 0.02,
        require_same_ion_mode: bool = True,
    ) -> tuple[list[AnalogHit], IndexedAnalogReport]:
        started = time.perf_counter()
        self._assert_policy(policy)
        references = self.window(
            query_neutral_mass,
            mass_window_da=mass_window_da,
        )
        query_modes = {spectrum.ion_mode for spectrum in query_spectra}
        scored_count = (
            sum(reference.spectrum.ion_mode in query_modes for reference in references)
            if require_same_ion_mode
            else len(references)
        )
        hits = retrieve_analogs(
            query_spectra,
            references,
            query_neutral_mass=query_neutral_mass,
            policy=policy,
            mass_window_da=mass_window_da,
            top_k=top_k,
            tolerance_da=tolerance_da,
            require_same_ion_mode=require_same_ion_mode,
        )
        elapsed = time.perf_counter() - started
        report = IndexedAnalogReport(
            total_reference_spectra=len(self),
            total_reference_identities=self.identity_count,
            mass_window_reference_spectra=len(references),
            scored_reference_spectra=int(scored_count),
            reduction_fraction=float(1.0 - len(references) / len(self)),
            returned_analogs=len(hits),
            elapsed_seconds=elapsed,
        )
        return hits, report
