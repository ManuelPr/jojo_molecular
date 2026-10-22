"""Conservative promotion of independently ranked external candidates."""
import math


def promote_consensus(original, external, base_keys, scores, *, eligible):
    """Inputs are metric identities. Return ranking and a diagnostic reason.

    The external lead must strictly beat every other scored candidate in the
    supplied base/external union, with at least two scored identities per source.
    Eligibility is supplied by the calling recipe, never by hidden labels.
    """
    original, external = list(original), list(dict.fromkeys(external))
    if len(original) != len(set(original)) or any(k is None for k in original):
        raise ValueError('Original ranking must contain distinct valid identities')
    if not eligible:
        return original, 'protected_or_unconfident'
    if not original or not external:
        return original, 'missing_candidates'
    lead = external[0]
    base_keys = set(base_keys)
    if lead in base_keys:
        return original, 'not_external'
    finite = {k: float(v) for k, v in scores.items()
              if v is not None and math.isfinite(float(v))}
    base_scored = base_keys.intersection(finite)
    external_scored = set(external).difference(base_keys).intersection(finite)
    if len(base_scored) < 2 or len(external_scored) < 2 or lead not in finite:
        return original, 'insufficient_forward_coverage'
    rivals = (base_scored | external_scored) - {lead}
    if any(finite[lead] <= finite[k] for k in rivals):
        return original, 'no_strict_forward_agreement'
    if original[0] == lead:
        return original, 'already_first'
    return ([lead] + [k for k in original if k != lead])[:25], 'promoted'
