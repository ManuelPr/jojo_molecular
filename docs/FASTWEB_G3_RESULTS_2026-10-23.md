# F0 submission and completed G3 diagnostics — 23 October 2026

F0 submission **57552927**, notebook
[`mperni/casmi26-f0-gu-v492-research-control`](https://www.kaggle.com/code/mperni/casmi26-f0-gu-v492-research-control),
version1, was accepted at **09:09:58 Europe/Rome**. Latest official API check at
09:46 Europe/Rome: **PENDING**, public score empty. Official best remains0.440;
neither the historical public0.464 nor the local scores below are a new official
result. Exactly one new submission was accepted. Research G3 started after it.

## Completed comparison

200 new public-panel queries,957 spectra, disjoint from pilot16, with200 distinct
official scorer identities. All reference spectra of these identities were
excluded, retaining candidate structures. Fixed final pool:7,729 candidates,
36,810 candidate-spectrum pairs. True-candidate pool coverage200/200; main pool,
ranker Recall@100 and Recall@1000 also200/200. This cohort diagnoses **ranking**;
it supplies no evidence about recovery of absent or novel structures.

| Method | MRR@25 | Delta against actual F0 joint | Diagnostic paired95% interval |
|---|---:|---:|---:|
| Protonated GLACIER + ICE fallback |0.907538|−0.003333|—|
| N1 complement |0.907538|−0.003333|—|
| F0 joint ICE + GLACIER proxy |0.910871|0|—|
| G3 LightGBM, five-fold OOF |**0.981667**|**+0.070795**|[+0.042879,+0.101137]|
| G3 neural listwise, five-fold OOF |0.978333|+0.067462|[+0.040795,+0.095380]|

G1 joint versus protonated-only delta+0.003333 has a paired interval crossing
zero (about[−0.005,+0.0133]); proxy coverage alone is not a demonstrated robust
gain. Eligible proxy cohort13; complement applies to12, joint to13.

G3 uses the prespecified features and fixed hyperparameters recorded in
`FASTWEB_F0_SUBMISSION_G3_2026-10-23.md` and `train_g3_fusion.py`. No tuning on
these outcomes. Folds are grouped by official identity; preprocessing fits on
training folds only. No truth or identity feature. Queries without a true
candidate would contribute zero, although none are absent in this cohort.

Independent verification recalculated both learned-model metrics directly from
the saved OOF scores and confirmed equality of all200 query RR values between
the final F0 CSV and the G1 joint control.44 alternate SMILES representatives
were independently canonicalized. LightGBM improves24 queries and regresses1
relative to actual F0: `OGWKCGZFUXNPDA`, rank1→2. Neural improves25 and regresses1:
`NTBUBTCXACOEEC`, rank1→2. Protected-library diagnostic cohort is only6 queries;
mean delta+0.041667 for both learned models, insufficient as a broad library
safety assessment.

LightGBM exceeds neural by0.003333; paired interval[−0.0075,+0.015] includes
zero. Prefer LightGBM as the next research candidate because neural complexity
has not demonstrated an advantage here. **No G3 model is promoted or submitted.**

## Scientific limits

These high local scores are **not leaderboard estimates**. The panel is public,
the candidate structures are retained, and Full1/A+B/ranker/forward pretrained
exclusion is unverified. Identity-grouped OOF protects the new fusion learner;
it does not remove upstream training exposure. Bootstrap intervals describe
query variation and omit dependence from overlapping fold-training sets. There
is no sealed evaluation of this learned recipe. The previously inspected16
queries are excluded from the200-query fit/evaluation, but the larger panel
still is diagnostic. Validate on an audited excluded cohort before promotion.

## Compute and recovery

All research stayed in existing job2545, H100, existing venv. Frozen splits
are byte-identical. No G2 or new G4 experiment. The public control retains its
inherited generator. No new allocation or training-environment installation.

| Successful forward stage | Covered/scored queries | Predictions | Failures | Driver wall |
|---|---:|---:|---:|---:|
| ICEBERG |178/200|40,743|0|319.05s|
| GLACIER protonated |175/200|34,877|0|180.97s|
| GLACIER N1A_D proxy |13 eligible|4,381|0|36.92s|

80,001 successful forward prediction jobs total; count excludes interrupted
work repeated during recovery. N1 uses47 spectra and10 merged-CE variants.
Simulator RDKit2025.03.6, PyTorch2.14.1+cu130; scorer RDKit2026.03.3.

The full200-query parent hit the26GiB guard after3169.56s, at sampled
28,183,703,552 bytes and sampled GPU peak15,313MiB; no OOM. Cached retrieval/main/PubChem/ICE stages were
preserved. Recovery reconstructed a lightweight parent without the large
reference index and repeated interrupted GLACIER/N1, retaining pinned inference
code and inputs. Recovery completed in1593.34s (26m33s), sampled RAM peak
10.52GiB, GPU2391MiB. Its original legacy `CLAW_GL_HEALTH` string can remain
`GL NOT RUN`; successful driver metadata,175 scored queries, and the subsequent
assertions are the authoritative execution evidence.

G3 five-fold LightGBM plus neural comparison completed in3.84s inside the
trainer,8.10s including process startup/profiling. Neural peak tensor allocation
76,154,368 bytes; sampled whole-GPU peak837MiB. The expensive computation is
retrieval, forward evidence and RDKit auditing, not this small fusion fit.
Successful recovery and training profiles both return0, with zero OOM events.

Kaggle visible smoke completed12 queries without main errors; both forward
stages CUDA/OK. Notebook wall3200.93s (53m21s). Its400-row visible CSV contains
388 deliberate placeholder rows; the official code rerun processes hidden data.
This is not a full400-query T4 runtime benchmark.

The finalizer initially hit API429 when enumerating output in20-file pages;
recovered using the allowed500-page size and the downloaded audited files.
Earlier HTTP400 submit attempts while the notebook ran were rejected, creating
no submission. Do not repeat the accepted mutation57552927.

## Artifacts and validation

Root: `artifacts/cluster/g3-dev200-2545/`.

- `experiment-manifest.json`: versions, lineage, output and checkpoint SHA256.
- `data-lineage.json`: generated data bytes/hashes and preserved split hashes.
- `independent-verification.json`: final F0 parity and independent OOF metrics.
- `control/`: `candidate_evidence.parquet`, `raw_candidate_evidence.parquet`,
  `candidate_spectrum_pairs.parquet`, `paired_queries.parquet`, `g1_results.json`.
- `fusion/results.json`, `oof_query_rr.csv`, `oof_candidate_scores.parquet`,
  five LightGBM checkpoints, five neural checkpoints, fold preprocessing files.
- `recovery-state.json`, `forward-recovery-manifest.json`, resource profiles
  and all failed-attempt logs. Original `run-manifest.json` retains the failed
  monolithic attempt; **recovery-state.json=complete** is the successor result.
- F0: `artifacts/kaggle/f0-gu-v1/finalizer-state.json`,
  `official-submission-status.json`, execution receipt and output inventories.

Ten focused tests passed after the finalizer pagination repair; `git diff
--check` passed. No further model fitting, full research run or submission is
needed to reproduce the reported completed comparison. The next promotion gate
is an audited excluded evaluation, not more tuning on this public panel.
