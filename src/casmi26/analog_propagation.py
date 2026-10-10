from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from collections.abc import Mapping, Sequence

import numpy as np

from .schemas import ProcessedSpectrum
from .spectral_evidence import (
    candidate_spectrum_compatibility,
    neutral_loss_similarity,
)


class AnalogLeakageError(ValueError):
    """Raised when a reference library violates the requested holdout policy."""


@dataclass(frozen=True, slots=True)
class AnalogReference:
    reference_id: str
    structure_id: str
    inchikey14: str
    neutral_mass: float
    spectrum: ProcessedSpectrum
    fingerprint: np.ndarray
    formula: str | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class AnalogCandidate:
    candidate_id: str
    inchikey14: str
    neutral_mass: float
    fingerprint: np.ndarray
    formula: str | None = None
    smiles: str | None = None


@dataclass(frozen=True, slots=True)
class AnalogHit:
    reference: AnalogReference
    spectral_similarity: float
    modified_cosine: float
    entropy_similarity: float
    neutral_loss_similarity: float
    shared_fragment_coverage: float
    same_adduct: float
    same_ion_mode: float
    same_instrument: float
    query_spectrum_id: str


@dataclass(frozen=True, slots=True)
class MassTransform:
    name: str
    delta_mass: float
    formula_delta: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class TransformMatch:
    transform: MassTransform
    error_da: float


@dataclass(frozen=True, slots=True)
class AnalogCandidateScore:
    candidate_id: str
    score: float
    features: Mapping[str, float]
    best_reference_id: str | None
    best_reference_inchikey14: str | None


@dataclass(frozen=True, slots=True)
class LeakagePolicy:
    forbidden_inchikey14: frozenset[str] = frozenset()
    forbidden_spectrum_hashes: frozenset[str] = frozenset()
    query_inchikey14: str | None = None
    allow_same_identity: bool = False

    def assert_reference_allowed(self, reference: AnalogReference) -> None:
        if reference.inchikey14 in self.forbidden_inchikey14:
            raise AnalogLeakageError(
                f"Forbidden holdout identity in analog library: {reference.inchikey14}"
            )
        if (
            not self.allow_same_identity
            and self.query_inchikey14
            and reference.inchikey14 == self.query_inchikey14
        ):
            raise AnalogLeakageError(
                f"Query identity in identity-disjoint analog library: {reference.inchikey14}"
            )
        digest = spectrum_content_hash(reference.spectrum)
        if digest in self.forbidden_spectrum_hashes:
            raise AnalogLeakageError(
                f"Forbidden holdout spectrum content in analog library: {reference.reference_id}"
            )


_TRANSFORMS: tuple[MassTransform, ...] = (
    MassTransform("hydrogenation", 2.0 * 1.00782503223, (("H", 2),)),
    MassTransform("dehydrogenation", -2.0 * 1.00782503223, (("H", -2),)),
    MassTransform("oxidation_or_hydroxylation", 15.99491461957, (("O", 1),)),
    MassTransform("deoxygenation", -15.99491461957, (("O", -1),)),
    MassTransform("methylation", 12.0 + 2.0 * 1.00782503223, (("C", 1), ("H", 2))),
    MassTransform("demethylation", -(12.0 + 2.0 * 1.00782503223), (("C", -1), ("H", -2))),
    MassTransform("hydration", 18.01056468403, (("H", 2), ("O", 1))),
    MassTransform("dehydration", -18.01056468403, (("H", -2), ("O", -1))),
    MassTransform(
        "acetylation",
        2.0 * 12.0 + 2.0 * 1.00782503223 + 15.99491461957,
        (("C", 2), ("H", 2), ("O", 1)),
    ),
    MassTransform(
        "deacetylation",
        -(2.0 * 12.0 + 2.0 * 1.00782503223 + 15.99491461957),
        (("C", -2), ("H", -2), ("O", -1)),
    ),
    MassTransform(
        "sulfation",
        31.9720711744 + 3.0 * 15.99491461957,
        (("S", 1), ("O", 3)),
    ),
    MassTransform(
        "phosphorylation",
        1.00782503223 + 30.97376199842 + 3.0 * 15.99491461957,
        (("H", 1), ("P", 1), ("O", 3)),
    ),
    MassTransform(
        "deoxyhexosylation",
        6.0 * 12.0 + 10.0 * 1.00782503223 + 4.0 * 15.99491461957,
        (("C", 6), ("H", 10), ("O", 4)),
    ),
    MassTransform(
        "hexosylation",
        6.0 * 12.0 + 10.0 * 1.00782503223 + 5.0 * 15.99491461957,
        (("C", 6), ("H", 10), ("O", 5)),
    ),
)


def spectrum_content_hash(spectrum: ProcessedSpectrum, *, decimals: int = 6) -> str:
    """Hash normalized spectral content, independent of row/spectrum identifiers."""

    mz = np.asarray(spectrum.mz, dtype=np.float64)
    intensity = np.asarray(spectrum.intensity, dtype=np.float64)
    if mz.shape != intensity.shape or mz.ndim != 1:
        raise ValueError("Spectrum peak arrays must be aligned vectors")
    if not np.isfinite(mz).all() or not np.isfinite(intensity).all():
        raise ValueError("Spectrum content hash requires finite peaks")
    order = np.lexsort((intensity, mz))
    normalized = intensity[order]
    if normalized.sum() > 0.0:
        normalized = normalized / normalized.sum()
    payload = np.column_stack(
        [np.round(mz[order], decimals), np.round(normalized, decimals)]
    ).astype("<f8", copy=False)
    # Do not include ids, instrument, adduct or source annotations: a copied
    # spectrum remains the same content even if its metadata was rewritten.
    metadata = f"{spectrum.precursor_mz:.{decimals}f}".encode("utf-8")
    digest = hashlib.sha256()
    digest.update(metadata)
    digest.update(payload.tobytes(order="C"))
    return digest.hexdigest()


def audit_reference_library(
    references: Sequence[AnalogReference],
    policy: LeakagePolicy,
    *,
    reject_duplicate_content: bool = True,
) -> dict[str, int]:
    seen_reference_ids: set[str] = set()
    seen_content: set[str] = set()
    duplicate_content = 0
    for reference in references:
        if reference.reference_id in seen_reference_ids:
            raise AnalogLeakageError(f"Duplicate analog reference id: {reference.reference_id}")
        seen_reference_ids.add(reference.reference_id)
        policy.assert_reference_allowed(reference)
        digest = spectrum_content_hash(reference.spectrum)
        if digest in seen_content:
            duplicate_content += 1
            if reject_duplicate_content:
                raise AnalogLeakageError(
                    f"Duplicate analog spectrum content: {reference.reference_id}"
                )
        seen_content.add(digest)
    return {
        "reference_count": len(references),
        "identity_count": len({reference.inchikey14 for reference in references}),
        "content_hash_count": len(seen_content),
        "duplicate_content_count": duplicate_content,
    }


def _mean_collision_energy(spectrum: ProcessedSpectrum) -> float | None:
    values = [float(value) for value in spectrum.collision_energy_ev if math.isfinite(float(value))]
    return float(np.mean(values)) if values else None


def _normalized_instrument(value: str | None) -> str:
    return "" if value is None else value.lower().replace("-", "").replace(" ", "")


def retrieve_analogs(
    query_spectra: Sequence[ProcessedSpectrum],
    references: Sequence[AnalogReference],
    *,
    query_neutral_mass: float,
    policy: LeakagePolicy,
    mass_window_da: float = 200.0,
    top_k: int = 80,
    tolerance_da: float = 0.02,
    require_same_ion_mode: bool = True,
) -> list[AnalogHit]:
    """Retrieve identity-disjoint analogs without consulting a target candidate."""

    if not query_spectra or top_k <= 0 or mass_window_da <= 0.0:
        raise ValueError("query_spectra, top_k, and mass_window_da must be non-empty/positive")
    if not math.isfinite(query_neutral_mass) or query_neutral_mass <= 0.0:
        raise ValueError("query_neutral_mass must be finite and positive")
    audit_reference_library(references, policy, reject_duplicate_content=False)
    best_by_identity: dict[str, AnalogHit] = {}
    for reference in references:
        if abs(reference.neutral_mass - query_neutral_mass) > mass_window_da:
            continue
        for query in query_spectra:
            if require_same_ion_mode and query.ion_mode != reference.spectrum.ion_mode:
                continue
            evidence = candidate_spectrum_compatibility(
                query.mz,
                query.intensity,
                reference.spectrum.mz,
                reference.spectrum.intensity,
                query_precursor_mz=query.precursor_mz,
                candidate_precursor_mz=reference.spectrum.precursor_mz,
                candidate_formula=reference.formula,
                query_collision_energy=_mean_collision_energy(query),
                candidate_collision_energy=_mean_collision_energy(reference.spectrum),
                query_adduct=query.adduct,
                candidate_adduct=reference.spectrum.adduct,
                tolerance_da=tolerance_da,
            )
            loss = neutral_loss_similarity(
                query.mz,
                query.intensity,
                reference.spectrum.mz,
                reference.spectrum.intensity,
                query_precursor_mz=query.precursor_mz,
                reference_precursor_mz=reference.spectrum.precursor_mz,
                tolerance_da=tolerance_da,
            )
            same_instrument = float(
                bool(_normalized_instrument(query.instrument))
                and _normalized_instrument(query.instrument)
                == _normalized_instrument(reference.spectrum.instrument)
            )
            # Entropy is direct evidence; modified cosine supplies mass-shifted
            # evidence. Instrument/adduct are modest reliability modifiers, not
            # target labels or hard proof of structural identity.
            spectral = (
                0.50 * evidence.modified_cosine
                + 0.30 * evidence.entropy_similarity
                + 0.20 * loss.score
            )
            reliability = 0.85 + 0.10 * same_instrument + 0.05 * evidence.same_adduct
            spectral = float(np.clip(spectral * reliability, 0.0, 1.0))
            hit = AnalogHit(
                reference=reference,
                spectral_similarity=spectral,
                modified_cosine=evidence.modified_cosine,
                entropy_similarity=evidence.entropy_similarity,
                neutral_loss_similarity=loss.score,
                shared_fragment_coverage=evidence.query_coverage,
                same_adduct=evidence.same_adduct,
                same_ion_mode=float(query.ion_mode == reference.spectrum.ion_mode),
                same_instrument=same_instrument,
                query_spectrum_id=query.spectrum_id,
            )
            previous = best_by_identity.get(reference.inchikey14)
            if previous is None or hit.spectral_similarity > previous.spectral_similarity:
                best_by_identity[reference.inchikey14] = hit
    return sorted(
        best_by_identity.values(),
        key=lambda hit: (
            -hit.spectral_similarity,
            -hit.same_instrument,
            hit.reference.reference_id,
        ),
    )[:top_k]


def plausible_mass_transforms(
    delta_mass: float,
    *,
    tolerance_da: float = 0.02,
) -> tuple[TransformMatch, ...]:
    """Return mass-consistent hypotheses, never a claimed transformation."""

    if not math.isfinite(delta_mass) or tolerance_da < 0.0:
        raise ValueError("delta_mass and tolerance_da must be finite/non-negative")
    matches = [
        TransformMatch(transform, float(delta_mass - transform.delta_mass))
        for transform in _TRANSFORMS
        if abs(delta_mass - transform.delta_mass) <= tolerance_da
    ]
    return tuple(sorted(matches, key=lambda match: (abs(match.error_da), match.transform.name)))


def fingerprint_tanimoto(left: np.ndarray, right: np.ndarray) -> float:
    lhs = np.asarray(left, dtype=np.bool_)
    rhs = np.asarray(right, dtype=np.bool_)
    if lhs.ndim != 1 or rhs.shape != lhs.shape:
        raise ValueError("Fingerprints must be aligned one-dimensional arrays")
    union = int(np.count_nonzero(lhs | rhs))
    if union == 0:
        return 1.0
    return float(np.count_nonzero(lhs & rhs) / union)


def _mass_alignment(candidate_mass: float, query_mass: float, ppm_scale: float) -> float:
    ppm = abs(candidate_mass - query_mass) / query_mass * 1e6
    return float(math.exp(-ppm / max(ppm_scale, 1e-12)))


def _transform_compatibility(delta_mass: float, *, tolerance_da: float) -> float:
    matches = plausible_mass_transforms(delta_mass, tolerance_da=tolerance_da)
    if not matches:
        return 0.0
    return float(math.exp(-abs(matches[0].error_da) / max(tolerance_da, 1e-12)))


def score_analog_candidates(
    candidates: Sequence[AnalogCandidate],
    analog_hits: Sequence[AnalogHit],
    *,
    query_neutral_mass: float,
    spectral_power: float = 3.0,
    transform_tolerance_da: float = 0.02,
    mass_ppm_scale: float = 10.0,
    include_transform: bool = True,
    include_adduct: bool = True,
) -> list[AnalogCandidateScore]:
    """Propagate analog evidence to an externally supplied fixed candidate pool."""

    if spectral_power <= 0.0 or mass_ppm_scale <= 0.0:
        raise ValueError("spectral_power and mass_ppm_scale must be positive")
    if not math.isfinite(query_neutral_mass) or query_neutral_mass <= 0.0:
        raise ValueError("query_neutral_mass must be positive")
    results: list[AnalogCandidateScore] = []
    for candidate in candidates:
        per_analog: list[tuple[float, AnalogHit, dict[str, float]]] = []
        for hit in analog_hits:
            structural = fingerprint_tanimoto(candidate.fingerprint, hit.reference.fingerprint)
            mass_alignment = _mass_alignment(
                candidate.neutral_mass, query_neutral_mass, mass_ppm_scale
            )
            query_delta = query_neutral_mass - hit.reference.neutral_mass
            transform = _transform_compatibility(
                query_delta, tolerance_da=transform_tolerance_da
            )
            chemistry = (
                0.55 * structural
                + 0.15 * hit.shared_fragment_coverage
                + 0.10 * hit.neutral_loss_similarity
                + (0.10 * transform if include_transform else 0.0)
                + (0.10 * hit.same_adduct if include_adduct else 0.0)
            )
            propagated = (
                hit.spectral_similarity**spectral_power * chemistry * mass_alignment
            )
            per_analog.append(
                (
                    propagated,
                    hit,
                    {
                        "structural_similarity": structural,
                        "mass_alignment": mass_alignment,
                        "transform_compatibility": transform,
                        "chemistry_support": chemistry,
                    },
                )
            )
        per_analog.sort(
            key=lambda item: (-item[0], item[1].reference.reference_id)
        )
        if per_analog:
            best_score, best_hit, components = per_analog[0]
            top3 = [item[0] for item in per_analog[:3]]
            features: dict[str, float] = {
                "analog_score": float(best_score),
                "analog_mean_top3": float(np.mean(top3)),
                "analog_best_spectral_similarity": best_hit.spectral_similarity,
                "analog_best_structural_similarity": components["structural_similarity"],
                "analog_best_neutral_loss_similarity": best_hit.neutral_loss_similarity,
                "analog_best_shared_fragment_coverage": best_hit.shared_fragment_coverage,
                "analog_mass_alignment": components["mass_alignment"],
                "analog_transform_compatibility": components["transform_compatibility"],
                "analog_adduct_compatibility": best_hit.same_adduct,
                "analog_same_instrument": best_hit.same_instrument,
                "analog_reference_count": float(len(per_analog)),
            }
            best_reference_id = best_hit.reference.reference_id
            best_reference_key = best_hit.reference.inchikey14
        else:
            best_score = 0.0
            features = {
                "analog_score": 0.0,
                "analog_mean_top3": 0.0,
                "analog_best_spectral_similarity": 0.0,
                "analog_best_structural_similarity": 0.0,
                "analog_best_neutral_loss_similarity": 0.0,
                "analog_best_shared_fragment_coverage": 0.0,
                "analog_mass_alignment": 0.0,
                "analog_transform_compatibility": 0.0,
                "analog_adduct_compatibility": 0.0,
                "analog_same_instrument": 0.0,
                "analog_reference_count": 0.0,
            }
            best_reference_id = None
            best_reference_key = None
        results.append(
            AnalogCandidateScore(
                candidate_id=candidate.candidate_id,
                score=float(best_score),
                features=features,
                best_reference_id=best_reference_id,
                best_reference_inchikey14=best_reference_key,
            )
        )
    return sorted(results, key=lambda result: (-result.score, result.candidate_id))


def propagate_analog_scores(
    query_spectra: Sequence[ProcessedSpectrum],
    candidates: Sequence[AnalogCandidate],
    references: Sequence[AnalogReference],
    *,
    query_neutral_mass: float,
    policy: LeakagePolicy,
    mass_window_da: float = 200.0,
    top_analogs: int = 80,
    tolerance_da: float = 0.02,
) -> tuple[list[AnalogCandidateScore], list[AnalogHit]]:
    hits = retrieve_analogs(
        query_spectra,
        references,
        query_neutral_mass=query_neutral_mass,
        policy=policy,
        mass_window_da=mass_window_da,
        top_k=top_analogs,
        tolerance_da=tolerance_da,
    )
    return (
        score_analog_candidates(
            candidates,
            hits,
            query_neutral_mass=query_neutral_mass,
        ),
        hits,
    )
