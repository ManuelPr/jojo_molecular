# Goal 5 — DreaMS frozen probe

## Decision

Status: **NOT RUN / environment-blocked**, not a negative model result.

The frozen-probe interface, exact cosine index, multi-acquisition aggregation,
MGF boundary and optional upstream runner are implemented and unit-tested.  The
official DreaMS checkpoint was not executed in Goal 5 because the current
offline Kaggle runtime cannot reproduce the upstream environment without a
separate Python 3.11 wheelhouse and a new 1.24 GB checkpoint asset.  No claim is
made about DreaMS accuracy.

This is an allowed Goal 5 outcome: the scaled mass/analog retrieval and the new
domain validation are the priority gates.  A dependency experiment that cannot
yet produce a trustworthy same-pool MRR comparison must not delay or contaminate
those gates.

## Upstream evidence frozen on 2026-10-10

- Repository: <https://github.com/pluskal-lab/DreaMS>
- Audited HEAD: `dbec3a0b514a99e5056cfccde4559fda8cfe8129`
- License: MIT.
- Published embedding API: `dreams.api.dreams_embeddings(...)`, returning a
  1,024-dimensional representation per spectrum.
- Checkpoint record: <https://zenodo.org/records/10997887>
- `embedding_model.ckpt`: 1,241,290,418 bytes,
  MD5 `4f6913c242b219b75e667dd1ed5add59`.
- `ssl_model.ckpt`: 1,392,710,212 bytes,
  MD5 `4deee91dd4486c2b6cbcde1f200b8f50`.

The embedding checkpoint alone is sufficient for the planned probe.  The
upstream public API does not expose the paper's fine-tuned fingerprint or
similarity checkpoint as an available named model; therefore this goal does not
treat a frozen spectrum embedding as a spectrum-to-structure predictor.

## Reproducibility blocker

The official package pins, among other dependencies:

| Dependency | Upstream pin | CASMI/Kaggle environment |
|---|---:|---:|
| Python | documented setup uses 3.11 | current Kaggle runtime is 3.13 |
| NumPy | 1.25.0 | project requires 2.x |
| PyTorch | 2.2.1 | Kaggle Goal 3 observed 2.11 on Python 3.13 |
| PyArrow | 15.0.2 | project uses 18–23 |
| RDKit | 2023.9.6 | official metric environment frozen at 2026.03.3 |
| pyOpenMS | 3.4.0 | absent from the offline asset bundle |
| `msml` | Git dependency | unavailable with internet disabled |

PyTorch 2.2.1 does not provide the required CPython 3.13 wheel.  Installing the
upstream package into the competition environment would also downgrade the
canonicalization stack used to reproduce the official metric.  Relaxing these
pins ad hoc would no longer be a reproducible upstream probe.  Enabling internet
inside the inference notebook would violate the verified offline submission
contract.

The correct remedy is an isolated Python 3.11 embedding job with:

1. a complete hashed Linux wheelhouse;
2. the embedding checkpoint stored as a versioned Kaggle dataset;
3. a fixed upstream source commit;
4. exported float32 embeddings plus row IDs and hashes;
5. downstream retrieval performed in the normal CASMI environment.

That remedy is technically feasible, but it is a distinct packaging and
compatibility experiment.  It was not silently approximated in Goal 5.

## Implemented probe contract

`src/casmi26/dreams_probe.py` provides:

- lazy import of the official API, with no training entry point;
- deterministic MGF export;
- finite/non-zero embedding validation;
- blockwise cosine search over memory-mapped reference embeddings;
- maximum similarity per unique InChIKey14;
- explicit same-identity exclusion for identity-disjoint protocols;
- max, mean and reciprocal-rank multi-spectrum aggregation;
- MRR/Hit evaluation using the project metric contract.

The frozen configuration is in `configs/goal5_dreams_frozen.yaml`; the isolated
runner is `scripts/run_dreams_frozen_probe.py`.  Six focused tests pass.  These
tests validate plumbing and leakage guards only, not scientific utility.

## Required experiment before promotion

The next probe must compare, on the exact same candidate pools and fixed split:

1. E6 spectral analog similarity;
2. DreaMS cosine retrieval;
3. E6 plus one DreaMS feature;
4. inference time, peak RAM/VRAM and embedding artifact size.

It must report A (library-visible) and B (structure-known/spectra-hidden)
separately.  Condition C cannot obtain exact-structure recall from a spectral
embedding alone and must not be presented as evidence of candidate generation.
Promotion requires a positive paired MRR@25 interval or a material retrieval
gain at acceptable cost.  Until then DreaMS remains an optional Goal 6 probe,
not part of the submission pipeline.
