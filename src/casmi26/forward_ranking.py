"""Evidence fusion that preserves unsupported cases and exposes candidate recall."""
import math
import numpy as np


def fuse_forward(base_scores, forward_scores, weight=1.0, *, protected=False):
    base = np.asarray(base_scores, dtype=np.float64)
    if base.ndim != 1 or not np.isfinite(base).all() or not math.isfinite(weight) or weight < 0:
        raise ValueError('Invalid ranking scores/weight')
    if len(forward_scores) != len(base):
        raise ValueError('Misaligned forward scores')
    forward = np.array([np.nan if value is None else float(value) for value in forward_scores])
    if np.isinf(forward).any():
        raise ValueError('Infinite forward score')
    valid = np.isfinite(forward)
    if protected or weight == 0 or valid.sum() < 2:
        return base.copy()
    # Missing scores receive no forward term; their base score is retained.
    # Ranker probabilities use log odds to avoid near-zero/near-one compression.
    clipped = np.clip(base, 1e-6, 1 - 1e-6)
    odds = np.log(clipped / (1 - clipped))
    sd = odds.std()
    normalized = (odds - odds.mean()) / sd if sd > 1e-12 else np.zeros_like(odds)
    scale = forward[valid].std()
    if scale <= 1e-12:
        return base.copy()
    terms = np.zeros(len(base))
    terms[valid] = (forward[valid] - forward[valid].mean()) / scale
    return normalized + weight * terms


def ranked_unique(smiles, scores, canonical_key, top_k=25):
    if len(smiles) != len(scores):
        raise ValueError('Misaligned candidate scores')
    seen, ranked = set(), []
    for i in np.argsort(-np.asarray(scores), kind='stable'):
        key = canonical_key(smiles[i])
        if key is None:
            raise ValueError('Invalid candidate identity')
        if key not in seen:
            seen.add(key)
            ranked.append(int(i))
            if len(ranked) == top_k:
                break
    return ranked


def reciprocal_rank(keys, truth, top_k=25):
    try:
        position = list(keys[:top_k]).index(truth) + 1
    except ValueError:
        return 0.0
    return 1.0 / position


def submission_smiles(variant, forward, *, weight=2., forward_top_k=40, library_gate=.9):
    """Apply the validated fusion and top25-then-deduplicate writer."""
    smis, keys = variant['smiles'], variant['keys']
    base = np.asarray(variant['probabilities'])
    if len(smis) != len(keys) or len(smis) != len(base):
        raise ValueError('Misaligned submission candidates')
    if not smis:
        return []
    seen, selected = set(), set()
    for i in np.argsort(-base, kind='stable'):
        if keys[i] in seen:
            continue
        seen.add(keys[i]); selected.add(smis[i])
        if len(selected) == forward_top_k:
            break
    scores = fuse_forward(base, [forward.get(s) if s in selected else None for s in smis], weight,
                          protected=variant['library_max'] >= library_gate)
    output, seen = [], set()
    for i in np.argsort(-scores)[:25]:
        if keys[i] not in seen:
            seen.add(keys[i]); output.append(smis[i])
    return output


def paired_bootstrap(before, after, *, seed=26, repetitions=2000):
    before, after = np.asarray(before, float), np.asarray(after, float)
    if before.shape != after.shape or before.ndim != 1 or not len(before):
        raise ValueError('Invalid paired metric arrays')
    if not np.isfinite(before).all() or not np.isfinite(after).all():
        raise ValueError('Invalid paired metrics')
    delta = after - before
    rng = np.random.default_rng(seed)
    values = delta[rng.integers(0, len(delta), size=(repetitions, len(delta)))].mean(1)
    return {'delta': float(delta.mean()), 'ci95': np.quantile(values, [0.025, 0.975]).tolist(),
            'improved_queries': int((delta > 0).sum()), 'worsened_queries': int((delta < 0).sum())}
