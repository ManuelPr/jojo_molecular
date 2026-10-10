from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import MACCSkeys, rdFingerprintGenerator

from .chemistry import canonical_smiles
from .goal3_contracts import FingerprintSpec, SpectrumBatch
from .schemas import ProcessedSpectrum


# Zero is deliberately reserved for values not seen by a trained model.
DEFAULT_ADDUCT_VOCAB: tuple[str, ...] = (
    "[M+H]+",
    "[M+NH4]+",
    "[M-H2O+H]+",
    "[M+H-H2O]+",
    "[M-2H2O+H]+",
    "[M+H-2H2O]+",
    "[M+Na]+",
    "[M+K]+",
    "[M-H]-",
    "[M-H2O-H]-",
    "[M+CH2O2-H]-",
    "[M+CHO2]-",
    "[M+Cl]-",
    "[M]+",
    "[M]-",
    "[M+2H]2+",
    "[M-2H]2-",
    "[2M+H]+",
    "[2M+Na]+",
    "[2M-H]-",
)
DEFAULT_ION_MODE_VOCAB: tuple[str, ...] = ("positive", "negative")


def _category_map(vocabulary: Sequence[str]) -> dict[str, int]:
    if len(set(vocabulary)) != len(vocabulary):
        raise ValueError("Categorical vocabularies may not contain duplicates")
    return {str(value).strip().lower(): index + 1 for index, value in enumerate(vocabulary)}


def _molecule_from_smiles(smiles: str) -> Chem.Mol:
    normalized = canonical_smiles(smiles)
    if normalized is None:
        raise ValueError(f"Cannot generate fingerprint from invalid SMILES: {smiles!r}")
    molecule = Chem.MolFromSmiles(normalized)
    if molecule is None:  # defensive: canonical_smiles has already parsed it
        raise ValueError(f"RDKit could not parse canonical SMILES: {normalized!r}")
    return molecule


def molecular_fingerprint(
    smiles: str,
    spec: FingerprintSpec = FingerprintSpec(),
    *,
    dtype: np.dtype | type = np.uint8,
) -> np.ndarray:
    """Return a canonical-tautomer RDKit fingerprint as a dense bit vector.

    Canonicalizing before featurization makes training labels consistent with
    the competition identity definition. Invalid SMILES fail loudly instead of
    silently becoming an all-zero label.
    """

    molecule = _molecule_from_smiles(smiles)
    if spec.kind == "morgan":
        generator = rdFingerprintGenerator.GetMorganGenerator(
            radius=spec.radius,
            fpSize=spec.n_bits,
            includeChirality=spec.use_chirality,
        )
        fingerprint = generator.GetFingerprint(molecule)
    elif spec.kind == "maccs":
        fingerprint = MACCSkeys.GenMACCSKeys(molecule)
    else:  # FingerprintSpec constrains this, but protects deserialized inputs.
        raise ValueError(f"Unsupported fingerprint kind: {spec.kind!r}")

    result = np.zeros((spec.n_bits,), dtype=np.uint8)
    DataStructs.ConvertToNumpyArray(fingerprint, result)
    return result.astype(dtype, copy=False)


def fingerprint_batch(
    smiles: Sequence[str],
    spec: FingerprintSpec = FingerprintSpec(),
    *,
    dtype: np.dtype | type = np.uint8,
) -> np.ndarray:
    """Generate fingerprints without changing the caller's sample order."""

    if not smiles:
        return np.empty((0, spec.n_bits), dtype=dtype)
    return np.stack(
        [molecular_fingerprint(value, spec, dtype=dtype) for value in smiles],
        axis=0,
    )


def _finite_collision_energy(values: Sequence[float]) -> float:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return float(np.mean(finite, dtype=np.float64)) if finite else 0.0


def _selected_peak_indices(
    mz: np.ndarray,
    intensity: np.ndarray,
    max_peaks: int,
) -> np.ndarray:
    valid = np.flatnonzero(
        np.isfinite(mz) & np.isfinite(intensity) & (mz > 0.0) & (intensity >= 0.0)
    )
    if valid.size > max_peaks:
        # lexsort's last key is primary: high intensity first, then low m/z,
        # then original position. The final m/z sort gives positional order.
        priority = np.lexsort((valid, mz[valid], -intensity[valid]))
        valid = valid[priority[:max_peaks]]
    order = np.lexsort((valid, -intensity[valid], mz[valid]))
    return valid[order]


def batch_processed_spectra(
    spectra: Sequence[ProcessedSpectrum],
    *,
    max_peaks: int = 256,
    adduct_vocabulary: Sequence[str] = DEFAULT_ADDUCT_VOCAB,
    ion_mode_vocabulary: Sequence[str] = DEFAULT_ION_MODE_VOCAB,
) -> SpectrumBatch:
    """Create a deterministic, padded, framework-neutral model batch.

    Padding is zero and marked false in ``peak_mask``. Neutral loss is measured
    from precursor m/z because fragment peaks are observed m/z values; the
    separate precursor feature uses adduct-corrected neutral mass when known.
    """

    if max_peaks <= 0:
        raise ValueError("max_peaks must be positive")
    adduct_map = _category_map(adduct_vocabulary)
    ion_mode_map = _category_map(ion_mode_vocabulary)
    batch_size = len(spectra)
    mz_batch = np.zeros((batch_size, max_peaks), dtype=np.float32)
    intensity_batch = np.zeros_like(mz_batch)
    neutral_loss_batch = np.zeros_like(mz_batch)
    peak_mask = np.zeros((batch_size, max_peaks), dtype=np.bool_)
    precursor_mass = np.zeros((batch_size,), dtype=np.float32)
    collision_energy = np.zeros((batch_size,), dtype=np.float32)
    adduct_index = np.zeros((batch_size,), dtype=np.int64)
    ion_mode_index = np.zeros((batch_size,), dtype=np.int64)

    for row, spectrum in enumerate(spectra):
        mz = np.asarray(spectrum.mz, dtype=np.float64)
        intensity = np.asarray(spectrum.intensity, dtype=np.float64)
        if mz.ndim != 1 or intensity.ndim != 1 or mz.shape != intensity.shape:
            raise ValueError(f"Misaligned peak arrays for {spectrum.spectrum_id}")
        indices = _selected_peak_indices(mz, intensity, max_peaks)
        count = indices.size
        if count:
            selected_mz = mz[indices]
            selected_intensity = intensity[indices]
            mz_batch[row, :count] = selected_mz
            intensity_batch[row, :count] = selected_intensity
            neutral_loss_batch[row, :count] = np.maximum(
                float(spectrum.precursor_mz) - selected_mz,
                0.0,
            )
            peak_mask[row, :count] = True

        mass = spectrum.neutral_mass
        if mass is None or not math.isfinite(float(mass)) or float(mass) <= 0.0:
            mass = spectrum.precursor_mz
        if not math.isfinite(float(mass)) or float(mass) <= 0.0:
            raise ValueError(f"Invalid precursor mass for {spectrum.spectrum_id}")
        precursor_mass[row] = float(mass)
        collision_energy[row] = _finite_collision_energy(spectrum.collision_energy_ev)
        adduct_index[row] = adduct_map.get(spectrum.adduct.strip().lower(), 0)
        ion_mode_index[row] = ion_mode_map.get(spectrum.ion_mode.strip().lower(), 0)

    return SpectrumBatch(
        mz=mz_batch,
        intensity=intensity_batch,
        neutral_loss=neutral_loss_batch,
        peak_mask=peak_mask,
        precursor_mass=precursor_mass,
        collision_energy=collision_energy,
        adduct_index=adduct_index,
        ion_mode_index=ion_mode_index,
    )


def _spectrum_vector(
    spectrum: ProcessedSpectrum,
    *,
    max_mz: float,
    bin_width: float,
) -> np.ndarray:
    bins = int(math.ceil(max_mz / bin_width))
    mz = np.asarray(spectrum.mz, dtype=np.float64)
    intensity = np.asarray(spectrum.intensity, dtype=np.float64)
    valid = np.isfinite(mz) & np.isfinite(intensity) & (mz >= 0.0) & (mz < max_mz)
    mz = mz[valid]
    intensity = np.maximum(intensity[valid], 0.0)
    vector = np.zeros((bins * 2 + 3,), dtype=np.float32)
    if mz.size:
        fragment_bins = np.floor(mz / bin_width).astype(np.int64)
        np.maximum.at(vector[:bins], fragment_bins, intensity)
        losses = np.maximum(float(spectrum.precursor_mz) - mz, 0.0)
        loss_valid = losses < max_mz
        loss_bins = np.floor(losses[loss_valid] / bin_width).astype(np.int64)
        np.maximum.at(vector[bins : 2 * bins], loss_bins, intensity[loss_valid])
    scale = max(float(np.linalg.norm(vector[: 2 * bins])), 1e-12)
    vector[: 2 * bins] /= scale
    vector[-3] = min(float(spectrum.precursor_mz) / max_mz, 2.0)
    vector[-2] = _finite_collision_energy(spectrum.collision_energy_ev) / 100.0
    vector[-1] = 1.0 if spectrum.ion_mode.strip().lower() == "positive" else -1.0
    return vector


class FingerprintKNNBaseline:
    """Small deterministic, non-neural spectrum-to-fingerprint baseline."""

    def __init__(self, *, n_neighbors: int = 5, max_mz: float = 1_200.0, bin_width: float = 5.0):
        if n_neighbors <= 0 or max_mz <= 0.0 or bin_width <= 0.0:
            raise ValueError("n_neighbors, max_mz and bin_width must be positive")
        self.n_neighbors = int(n_neighbors)
        self.max_mz = float(max_mz)
        self.bin_width = float(bin_width)
        self._features: np.ndarray | None = None
        self._targets: np.ndarray | None = None

    def fit(
        self,
        spectra: Sequence[ProcessedSpectrum],
        targets: np.ndarray,
    ) -> "FingerprintKNNBaseline":
        y = np.asarray(targets, dtype=np.float32)
        if y.ndim != 2 or y.shape[0] != len(spectra) or y.shape[1] == 0:
            raise ValueError("targets must have shape [len(spectra), fingerprint_bits]")
        if not spectra:
            raise ValueError("At least one training spectrum is required")
        if not np.isfinite(y).all() or np.any((y < 0.0) | (y > 1.0)):
            raise ValueError("Fingerprint targets must be finite values in [0, 1]")
        self._features = np.stack(
            [_spectrum_vector(s, max_mz=self.max_mz, bin_width=self.bin_width) for s in spectra]
        )
        self._targets = y.copy()
        return self

    def predict_proba(self, spectra: Sequence[ProcessedSpectrum]) -> np.ndarray:
        if self._features is None or self._targets is None:
            raise ValueError("FingerprintKNNBaseline must be fitted before prediction")
        if not spectra:
            return np.empty((0, self._targets.shape[1]), dtype=np.float32)
        queries = np.stack(
            [_spectrum_vector(s, max_mz=self.max_mz, bin_width=self.bin_width) for s in spectra]
        )
        train_norm = np.linalg.norm(self._features, axis=1)
        query_norm = np.linalg.norm(queries, axis=1)
        similarities = queries @ self._features.T
        similarities /= np.maximum(query_norm[:, None] * train_norm[None, :], 1e-12)
        k = min(self.n_neighbors, self._features.shape[0])
        result = np.empty((queries.shape[0], self._targets.shape[1]), dtype=np.float32)
        for row in range(queries.shape[0]):
            # Stable sorting makes equal-similarity behavior reproducible.
            neighbors = np.argsort(-similarities[row], kind="stable")[:k]
            weights = np.maximum(similarities[row, neighbors], 0.0) + 1e-6
            result[row] = np.average(self._targets[neighbors], axis=0, weights=weights)
        return result

    def predict(self, spectra: Sequence[ProcessedSpectrum], *, threshold: float = 0.5) -> np.ndarray:
        return self.predict_proba(spectra) >= threshold


NonNeuralFingerprintBaseline = FingerprintKNNBaseline


def fingerprint_metrics(
    predictions: np.ndarray,
    targets: np.ndarray,
    *,
    threshold: float = 0.5,
    from_logits: bool = False,
) -> dict[str, float]:
    """Return robust micro and sample-level multilabel fingerprint metrics."""

    prediction = np.asarray(predictions, dtype=np.float64)
    truth = np.asarray(targets)
    if prediction.shape != truth.shape or prediction.ndim != 2:
        raise ValueError("predictions and targets must share shape [samples, bits]")
    if prediction.size == 0 or not np.isfinite(prediction).all():
        raise ValueError("predictions must be non-empty and finite")
    if from_logits:
        prediction = _stable_sigmoid(prediction)
    predicted = prediction >= threshold
    actual = truth.astype(bool)
    tp = int(np.count_nonzero(predicted & actual))
    fp = int(np.count_nonzero(predicted & ~actual))
    fn = int(np.count_nonzero(~predicted & actual))
    union = np.count_nonzero(predicted | actual, axis=1)
    intersection = np.count_nonzero(predicted & actual, axis=1)
    sample_jaccard = np.divide(
        intersection,
        union,
        out=np.ones_like(intersection, dtype=np.float64),
        where=union != 0,
    )
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "binary_accuracy": float(np.mean(predicted == actual)),
        "micro_precision": float(precision),
        "micro_recall": float(recall),
        "micro_f1": float(2.0 * precision * recall / (precision + recall))
        if precision + recall
        else 0.0,
        "micro_jaccard": float(tp / (tp + fp + fn)) if tp + fp + fn else 1.0,
        "mean_sample_jaccard": float(np.mean(sample_jaccard)),
    }


def candidate_compatibility_scores(
    prediction: np.ndarray,
    candidate_fingerprints: np.ndarray,
    *,
    from_logits: bool = True,
    method: str = "log_likelihood",
    bit_weights: np.ndarray | None = None,
    epsilon: float = 1e-7,
) -> np.ndarray:
    """Score candidate fingerprints against one spectrum prediction.

    ``log_likelihood`` is the mean Bernoulli log likelihood and preserves
    negative evidence (predicted-absent bits). ``soft_tanimoto`` is useful as a
    bounded, familiar diagnostic score.
    """

    values = np.asarray(prediction, dtype=np.float64)
    candidates = np.asarray(candidate_fingerprints, dtype=np.float64)
    if values.ndim != 1 or candidates.ndim != 2 or candidates.shape[1] != values.size:
        raise ValueError("Expected prediction [bits] and candidates [candidates, bits]")
    if not np.isfinite(values).all() or not np.isfinite(candidates).all():
        raise ValueError("Compatibility inputs must be finite")
    probabilities = _stable_sigmoid(values) if from_logits else values
    probabilities = np.clip(probabilities, epsilon, 1.0 - epsilon)
    weights = np.ones_like(values)
    if bit_weights is not None:
        weights = np.asarray(bit_weights, dtype=np.float64)
        if weights.shape != values.shape or not np.isfinite(weights).all() or np.any(weights < 0.0):
            raise ValueError("bit_weights must be finite, non-negative, and match prediction")
    if not np.any(weights > 0.0):
        raise ValueError("At least one bit weight must be positive")

    if method in {"log_likelihood", "bernoulli"}:
        scores = candidates * np.log(probabilities) + (1.0 - candidates) * np.log1p(-probabilities)
        return np.average(scores, axis=1, weights=weights)
    if method in {"soft_tanimoto", "tanimoto"}:
        weighted_probability = probabilities * weights
        intersection = candidates @ weighted_probability
        denominator = (
            np.sum(weighted_probability)
            + np.sum(candidates * weights[None, :], axis=1)
            - intersection
        )
        return np.divide(intersection, denominator, out=np.zeros_like(intersection), where=denominator > 0)
    raise ValueError(f"Unknown compatibility method: {method!r}")


def _stable_sigmoid(values: np.ndarray) -> np.ndarray:
    result = np.empty_like(values, dtype=np.float64)
    nonnegative = values >= 0.0
    result[nonnegative] = 1.0 / (1.0 + np.exp(-values[nonnegative]))
    exponent = np.exp(values[~nonnegative])
    result[~nonnegative] = exponent / (1.0 + exponent)
    return result


def rank_candidate_fingerprints(
    prediction: np.ndarray,
    candidates: Mapping[str, np.ndarray],
    **score_kwargs: object,
) -> list[tuple[str, float]]:
    """Score and deterministically rank an id-to-fingerprint mapping."""

    candidate_ids = list(candidates)
    if not candidate_ids:
        return []
    matrix = np.stack([np.asarray(candidates[key]) for key in candidate_ids])
    scores = candidate_compatibility_scores(prediction, matrix, **score_kwargs)
    order = sorted(range(len(candidate_ids)), key=lambda index: (-float(scores[index]), candidate_ids[index]))
    return [(candidate_ids[index], float(scores[index])) for index in order]


# Readable aliases for callers that treat batching/fingerprinting as collators.
compute_fingerprint = molecular_fingerprint
collate_spectra = batch_processed_spectra
