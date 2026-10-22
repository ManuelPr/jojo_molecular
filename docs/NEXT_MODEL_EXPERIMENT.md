# Model experiment recommendation — 2026-10-13

User objective: test a credible route above public MRR@25 0.42 from measured
control 0.298. No model or ensemble guarantees the threshold.

Recommended hypothesis: expanded-candidate retrieval + learned ranking +
forward-spectrum reranking using GLACIER, then ICEBERG/GLACIER ensemble.
Evaluate incremental stages on fixed development, record canonical candidate
recall and ranking MRR separately, keep strong library matches protected by a
gate calibrated on validation. Public 0.298 recipe remains frozen.

## Evidence and access limits

- Author repository reports v4n/FPNet + two-engine fusion + PubChem join +
  ICEBERG/GLACIER + popularity reaching 0.420. This is an author claim, not our
  reproduced score. Source:
  https://github.com/gnshx/Enveda-CASMI-2026---Molecule-ID-From-Mass-Spectra
- Indexed Kaggle page for flexonafft shows best 0.436 V80 (separate current
  viewed V59 score 0.411). Exact V80 download returned 403, including after
  OAuth refresh. Slug redirects to casmi26-public-baseline-adaptation-experiments.
  Latest source not inspected; do not attribute exact architecture or promise
  reproduction of 0.436. Source:
  https://www.kaggle.com/code/flexonafft/casmi26-public-baseline-adaptation-experiments
- Official ms-pred repository supplies GLACIER/ICEBERG spectrum simulators.
  README distinguishes restricted NIST-trained weights from open MassSpecGym
  checkpoints; inspect chosen assets/provenance before integrating. Source:
  https://github.com/coleygroup/ms-pred
- External future-experiment gain estimates are hypotheses, not measured gains.

## Proposed controlled comparison

1. Frozen public-control 0.298 recipe: diagnostic baseline.
2. Expand candidate evidence with PubChem; remove premature top80 loss via
   measured recall before/after pruning. Rank all retained candidates together.
3. Add GLACIER forward-spectrum similarity at a fixed candidate pool; learn
   combination on development with identity separation and documented
   pretrained-overlap limitations.
4. Test ICEBERG + GLACIER ensemble and an upgraded fingerprint/ranker bank.
5. Prepare full offline rehearsal and seek explicit approval for a new official
   submission only after a measured validation improvement and runtime gate.

No new GPU job, training, dataset upload or submission started by this review.
