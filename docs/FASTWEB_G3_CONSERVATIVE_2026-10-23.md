# F0 top1-preserving G3 tail experiment — 23 October 2026

User authorized this experiment with “bho, falla”, following the explicit
proposal to retain F0 top1 and reorder only positions2–25 with G3.

Control F0 submission57552927 scored0.464; unrestricted G3 submission57554882
scored0.388. This experiment preserves the exact ordered first F0 candidate
and exact F0 top25 candidate multiset for every query. Only positions2–25 are
sorted by existing five-fold mean G3 scores; candidates missing G3 evidence
stay at the tail with stable original order. No new training or dataset upload.
The same private model datasetV1 and five pinned F0 research mounts are reused.
This cannot lose an already-correct F0 rank1 answer, but can still harm ranks2–25.

Notebook `mperni/casmi26-f0-g3-conservative-tail` version1 was pushed successfully.
Bundle: `kaggle/fastweb_g3_conservative_bundle/`. Build manifest records notebook
and inline overlay SHA256 plus unchanged model-manifest SHA256. The only new
prediction behavior is the final conservative overlay; F0 remains unchanged.

Detached finalizer:
`scripts/finalize_fastweb_g3_submission.py --version 1 --conservative`.
State: `artifacts/kaggle/g3-conservative-v1/submission-state.json`.
It waits for notebook COMPLETE, verifies output hash, model-manifest hash,
CSV structure, zero main errors and preservation assertions, then submits once.
Do not restart or submit manually without reconciling state.

Three focused tests passed (conservative output/receipt contract and existing
finalizer mutation guards); notebook code parsed and git diff --check passed.
No new allocation, venv changes, frozen-split changes, G2 or G4 training.
Official submission ID and score are not yet available; read live state.


## Conservative G3 official result — 23 October 2026

Authenticated Kaggle API confirms submission57563808 COMPLETE, public MRR@25
0.451. F0 control57552927 remains0.464; unrestricted G3 scored0.388.
Conservative tail ordering improves0.063 over unrestricted G3 but regresses
0.013 against F0. Preserve F0 as baseline; do not promote either G3 recipe.
The scored conservative recipe preserves F0 top1 and candidate set, so tail
ordering provides a net negative contribution on the public score. The
comparison with unrestricted G3 also changes pool membership (exact F0 top25
versus unrestricted fusion pool), so it does not isolate top1 protection alone.
No new training or submission launched during this check.
Snapshot: `artifacts/kaggle/g3-conservative-v1/official-results.json`.
