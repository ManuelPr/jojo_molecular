"""Conservative insertion of external identities into a frozen base ranking."""

import numpy as np


def external_ranked_keys(variant):
    """Use the existing ranker only to order PubChem candidates among themselves."""
    probabilities = np.asarray(variant['probabilities'], dtype=float)
    if not np.isfinite(probabilities).all():
        raise ValueError('Non-finite PubChem ranker probabilities')
    seen, out = set(), []
    for index in np.argsort(-probabilities, kind='stable'):
        if not variant['external_flags'][index]:
            continue
        key = variant['keys'][index]
        if key not in seen:
            seen.add(key)
            out.append((key, variant['smiles'][index]))
    return out


def insert_external(base_smiles, external, canonical_key, *, slots=(4, 8, 12, 16, 20), limit=25):
    """Keep the base top-1 and insert distinct external structures at fixed slots."""
    if not base_smiles:
        return [smile for _, smile in external[:limit]]
    base_keys = [canonical_key(smile) for smile in base_smiles]
    if any(key is None for key in base_keys):
        raise ValueError('Invalid base identity')
    seen = set(base_keys)
    new = []
    for key, smile in external:
        if key not in seen:
            seen.add(key)
            new.append(smile)
    result, base_index, new_index = [], 0, 0
    for position in range(1, limit + 1):
        if position in slots and new_index < len(new):
            result.append(new[new_index]); new_index += 1
        elif base_index < len(base_smiles):
            result.append(base_smiles[base_index]); base_index += 1
        elif new_index < len(new):
            result.append(new[new_index]); new_index += 1
        else:
            break
    if result[0] != base_smiles[0] or len({canonical_key(s) for s in result}) != len(result):
        raise ValueError('Selective insertion contract failed')
    return result


def eligible_for_pubchem(base_variant, *, library_gate=.9, probability_gate=.3):
    if base_variant['library_max'] >= library_gate:
        return False
    probabilities = np.asarray(base_variant['probabilities'], dtype=float)
    if not len(probabilities):
        return True
    if not np.isfinite(probabilities).all():
        raise ValueError('Non-finite base ranker probabilities')
    return float(probabilities.max()) < probability_gate
