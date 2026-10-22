"""Bounded-memory retrieval from a mass-sorted, offset-encoded PubChem index."""
from dataclasses import dataclass
import heapq
import math
from pathlib import Path
from typing import Callable, Iterator

import numpy as np


@dataclass(frozen=True)
class PubChemEntry:
    index: int
    mass: float
    smiles: str


class PubChemMassIndex:
    def __init__(self, mass, offsets, buffer):
        self.mass, self.offsets, self.buffer = mass, offsets, buffer
        if mass.ndim != 1 or buffer.ndim != 1 or offsets.shape != (len(mass) + 1,):
            raise ValueError('Invalid PubChem index dimensions')
        if not np.issubdtype(offsets.dtype, np.integer) or buffer.dtype != np.uint8:
            raise ValueError('Invalid PubChem offset/buffer dtype')
        if offsets[0] != 0 or offsets[-1] != len(buffer):
            raise ValueError('Invalid PubChem buffer boundary')

    @classmethod
    def from_directory(cls, directory):
        directory = Path(directory)
        return cls(*(np.load(directory / name, mmap_mode='r') for name in ['pc_mass.npy', 'pc_off.npy', 'pc_smiles.npy']))

    def bounds(self, target: float, ppm: float) -> tuple[int, int]:
        if not math.isfinite(target) or target <= 0 or not math.isfinite(ppm) or not 0 < ppm < 1e6:
            raise ValueError('Invalid neutral mass or tolerance')
        radius = target * ppm * 1e-6
        return int(np.searchsorted(self.mass, target - radius, side='left')), int(np.searchsorted(self.mass, target + radius, side='right'))

    def iter_window(self, target: float, ppm: float) -> Iterator[PubChemEntry]:
        lo, hi = self.bounds(target, ppm)
        for i in range(lo, hi):
            a, b = int(self.offsets[i]), int(self.offsets[i + 1])
            if not 0 <= a < b <= len(self.buffer):
                raise ValueError('Invalid PubChem offset within window')
            mass = float(self.mass[i])
            if not math.isfinite(mass) or abs(mass - target) > target * ppm * 1e-6 + 1e-10:
                raise ValueError('Unsorted or invalid PubChem mass window')
            yield PubChemEntry(i, mass, bytes(self.buffer[a:b]).decode('ascii'))


def screen_pubchem(index: PubChemMassIndex, target: float, ppm: float, *,
                   coarse_score: Callable[[str], float | None], full_fingerprint: Callable,
                   logits, canonical_key: Callable[[str], str | None],
                   exclude_keys=(), coarse_limit=2000, top_k=50):
    """Screen every mass-window entry; canonicalize only full-scored finalists.

    Invalid structures are counted and skipped. No true label is consulted,
    no molecular source receives fixed output slots, and top-k ties are stable.
    Returned fingerprints let external candidates use the same final ranker.
    """
    if coarse_limit < 1 or top_k < 1:
        raise ValueError('Candidate limits must be positive')
    logits = np.asarray(logits, dtype=np.float32)
    if logits.ndim != 1 or not np.isfinite(logits).all():
        raise ValueError('Invalid fingerprint logits')
    heap, window_count, valid_coarse = [], 0, 0
    for entry in index.iter_window(target, ppm):
        window_count += 1
        value = coarse_score(entry.smiles)
        if value is None or not math.isfinite(value):
            continue
        valid_coarse += 1
        item = (float(value), -entry.index, entry)
        if len(heap) < coarse_limit:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)
    scored = []
    for _, _, entry in heap:
        fp = full_fingerprint(entry.smiles)
        if fp is None:
            continue
        fp = np.asarray(fp, dtype=np.uint8)
        if fp.shape != logits.shape or not np.isin(fp, [0, 1]).all():
            raise ValueError('Fingerprint contract differs from neural logits')
        scored.append((float(fp @ logits), entry.index, entry, fp))
    scored.sort(key=lambda x: (-x[0], x[1]))
    seen, output, excluded, invalid_identity = set(), [], 0, 0
    excluded_keys = set(exclude_keys)
    for score, _, entry, fp in scored:
        key = canonical_key(entry.smiles)
        if not key:
            invalid_identity += 1
            continue
        if key in seen:
            continue
        seen.add(key)
        if key in excluded_keys:
            excluded += 1
            continue
        output.append({'entry': entry, 'key': key, 'fingerprint': fp, 'neural_score': score})
        if len(output) == top_k:
            break
    return output, {'window_count': window_count, 'valid_coarse': valid_coarse,
                    'coarse_retained': len(heap), 'full_scored': len(scored),
                    'already_in_pool': excluded, 'invalid_identity': invalid_identity,
                    'added': len(output)}
