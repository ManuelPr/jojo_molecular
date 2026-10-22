# Public notebook gap after submission 57184698

Checked 2026-10-14. Our measured public MRR@25 is **0.338**. Public notebook
sources were pulled with the authenticated Kaggle CLI into the ignored
`artifacts/public_notebook_audit/` directory; source code and notebook markdown
were inspected. The Kaggle pages below are the primary source for displayed
scores. A `Best Score` is a historical version score and does not necessarily
describe the current notebook version.

| Notebook | Displayed score evidence | What the accessible source actually does |
|---|---|---|
| [Ahmed v4m](https://www.kaggle.com/code/ahmedberatozer/casmi26-v4m-inference) | Public 0.378, v1 | Train+COCONUT engine with FPNet full bank, generated candidates enabled, PubChem-only channel behind a gate, ICEBERG isomer reranking. The extracted v1 code invokes ICEBERG; a mounted GLACIER asset alone is not evidence of its use. |
| [Dmitrii, From Spectra to Structures](https://www.kaggle.com/code/dmitriigluzdov/casmi-26-from-spectra-to-structures) | Best 0.411 v36 (indexed Kaggle page) | Long EDA followed by a substantially reused two-engine / PubChem / simulator E006 pipeline. This is not an independent newly trained model. |
| [Flexon, Public Baseline Adaptation](https://www.kaggle.com/code/flexonafft/casmi26-public-baseline-adaptation-experiments?scriptVersionId=357683876) | Public 0.440 v89; [v90](https://www.kaggle.com/code/flexonafft/casmi26-public-baseline-adaptation-experiments?scriptVersionId=357684123) 0.415 | Exact downloaded v89 and v90 notebooks have 35 cells. Source differs only in the header (cell 1) and final experiment (cell 35): v89 sets `MODE='dual'`; v90 sets `MODE='joint'`. The two-engine / PubChem / simulator E006 core in cells 2–34 is source-identical. |
| [Canqiang E006](https://www.kaggle.com/code/canqiang/casmi26-e006-window-40-ice-fallback-true) and [Ahmed v7c](https://www.kaggle.com/code/ahmedberatozer/casmi26-v7c-e006-fraggap) | 0.440 and 0.441 respectively are stated by the downloaded notebook authors; not independently confirmed against their specific Kaggle page/version in this audit | E006 adds metric-identity fusion within 40 and ICEBERG fallback where GLACIER has no usable score; v7c adds a MetFrag-lite fragment fallback where neither simulator covers the molecule. |

The accessible higher-scoring family shares substantial code and assets; these
are not independent demonstrations that each feature adds to public MRR.
`saddamaditya/casmi26-dual-band-massbank-iceberg-sota` contains an almost
identical inherited core to Ahmed v7c (first 100k extracted characters: 0.996
difflib similarity). Its title mentions MassBank, but the extracted code contains
no explicit `MassBank` reference; do not credit the score to that source without
an ablation. Author-reported incremental leaderboard deltas are hypotheses for
our design, not independently reproduced effects.

## Architecture gap versus our 0.338 notebook

1. **Candidate coverage.** Ours retrieves from 712,199 train+COCONUT
   structures. Higher-scoring notebooks additionally search an approximately
   105 million-structure PubChem tier for identities absent from the base pool.
   They gate entry when direct-library evidence is strong, use fingerprint
   shortlist/popularity priors, and sometimes add ChEBI/LIPID MAPS or generated
   candidates. Our own blind PubChem join worsened standard development MRR,
   which argues for a selective branch rather than a blanket union.
2. **Ranking.** Ours uses the frozen public two FPNet checkpoints and eight
   31-feature HistGradientBoosting rankers. Ahmed v4n descendants use a fuller
   fingerprint bank and a four-booster LightGBM ranker, plus a separate BIO/AFIX
   two-ranker engine. They combine two ranked lists by reciprocal-rank fusion
   after deduplicating the scorer's tautomer-canonical InChIKey14 identities.
3. **Simulator coverage.** Ours runs GLACIER on eligible [M+H]+ top-40
   candidates only when library confidence is below 0.9. The other family uses
   ICEBERG as a complementary simulator, especially when GLACIER has no score,
   and reranks same-formula isomer groups. Later E006/v7c variants add fragment
   evidence when neither simulator scores a candidate group.
4. **Final output.** Their final audit fills available top-25 slots with distinct
   scorer identities. Our original writer cuts raw top-25 first and only then
   deduplicates, so it may output fewer than 25 structures. This can affect
   tail recall but does not by itself explain the public score gap.

No hidden query labels, per-class scores, candidate recall or simulator coverage
are exposed by Kaggle for these runs. A public-score difference cannot isolate
which component helped. The user-facing take-away is a **coverage and routing**
gap, with isomer ranking another plausible contributor. The most diagnostic
next offline experiment is to compare the frozen 0.338 recipe against a gated
PubChem-only branch on an identity-held-out, different-acquisition cohort;
measure candidate recall before MRR. ICEBERG fallback and metric-safe tail
completion can then be tested one at a time. No new official submission was
authorized by this audit.

## Exact Flexon v89 to v90 comparison

The Kaggle CLI denied the version-specific pull, but the public v89 page's
**Download .ipynb** action worked. The downloaded v89 SHA256 is
`c43e870c92bd67b2f0c0245c1b4064cfb1c49a1cbc81ffac349bee4708ad55a1`;
the user-supplied v90 SHA256 is
`ea0290602632249a6e10cf6e270f17da82486c7d1d4cb007092a4ca2c327e13d`.
Both source notebooks were parsed as JSON; no cells were executed locally.

- **v89, 0.440:** for weak-library molecules with both polarities, retrieve
  separate positive and negative PubChem lists, combine them with the existing
  PubChem list by reciprocal-rank fusion, then retain the original gated slots,
  any confident PubChem top-1 promotion, engine fusion and same-formula simulator
  rerank. Single-polarity molecules are outside this experimental overlay.
- **v90, 0.415:** for all weak-library molecules, pool the E006 output, main
  top-60, Engine2 top-40 and PubChem top-25, then rank by standardized common
  FPNet fit + 0.25 popularity + standardized reciprocal-rank support. This
  replaces the fixed PubChem slots and can change top-1. The fallback preserves
  E006 only when required evidence is incomplete.

The observed public delta is **-0.025 MRR@25**. Since cells 2–34 are identical,
the broad ranking overlay is the specific source-level change associated with
the lower score; the public results do not prove that the overlay alone caused
every lost match. The visible commit runs both process only 12 placeholder
molecules and report `eligible=0`, `changed_rows=0`, `measured_score=None` for
their respective overlays. Those smoke outputs cannot establish hidden-rerun
eligibility or ablate the overlay. Even the v89 0.440 cannot be attributed to
dual-polarity retrieval without the hidden-rerun audit; its own header calls
0.440 the user-confirmed E006 baseline.

Implication for our experiments: preserve strong library and gated candidate
routes when adding PubChem; avoid globally replacing a working top-1 ranker
with a heuristic until an identity-held-out paired test shows a gain. The
immediate offline comparison remains E006-like gated retrieval versus a
joint-pool ranker with per-molecule changed-top1 and candidate-recall audits.

Additional first-party context: [competitor discussion on held-out isomers and
novelty](https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra/discussion/743254).
