# Public baseline diagnostic control

Date: 2026-10-13. State: offline rehearsal/development COMPLETE, local gate PASS;
authorized official submission 57143111 (exact v2) COMPLETE, public **0.298**,
error_description empty. Result observed 2026-10-13 16:30:44 Europe/Rome.

## Objective and fixed recipe

Reproduce the historical public four-channel fork as a control after submissions
57109254 scored public MRR@25 0.000 and 57135939 failed with an unhandled
hidden-rerun error (no score, verified via API error_description). Do not tune
on leaderboard scores. Source, license and adaptations:
`third_party/public_four_channel/README.md`.

Source SHA-256: `65aeab2a4cb3e2ceee3f993915495c2910439913de62e1b26700dcc79f2c351f`.
The recipe has train + COCONUT candidates, full train spectral references,
top-100 analogs, MetFrag-lite, single/merged FPNet and eight 31-feature GBMs.
The original 80-candidate prune and all ranking parameters remain unchanged.
The output writer removes duplicate scorer identities without padding.

Assets: COCONUT version 2, FP-models-v2 version 1, ranker-features version 6.
All file bytes are pinned in `configs/public_baseline_manifest.json`; runtime
checks reject any drift. Hashes, not dataset descriptions, certify the bytes.
Ranker rows SHA-256: `41ccec87fba5f8ab255aaf5a723567f25bd766064265c5cc2b83ba2cf15f57f8`.
Published score 0.339 is historical and self-reported; the current asset mix is
not guaranteed to reproduce it. The external producer's log itself describes
material variation across ranker versions.

## Rules and environment verified

The [official rules](https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra/rules)
were read in the browser on 2026-10-13. They allow reasonably accessible external
data/models, set five submissions/day and two final selections, and require
non-commercial handling of competition data. The published datasets are freely
accessible to participants; their cards specify CC-BY-NC-SA-4.0. No competition
spectra are redistributed in this control. All notebooks remain private.

The [official overview](https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra/overview)
was also read directly in the browser: fewer than 25 guesses is explicitly
allowed, scoring uses tautomer-canonical InChIKey14 under RDKit 2026.03.3,
CPU and GPU notebooks have a nine-hour maximum, internet must be off and
freely available pretrained models are allowed. The final deadline remains
2026-12-14 23:59 UTC. Thus removing duplicate padding is format-correct.

CPU only, internet off, timeout 10,800 seconds. No paid VM and no GPU quota.
Kaggle v1 failed during the first 11 seconds: attached RDKit cp312 wheel was
incompatible with Kaggle Python 3.13. It produced no predictions and consumed
no official submission. v2 uses the same RDKit release via our cp313 wheel.

Kernel: [mperni/casmi26-public-baseline-control](https://www.kaggle.com/code/mperni/casmi26-public-baseline-control).
v2 source SHA-256: `950e3fb9ca4284e5e4e2cd2a82139b83ae244b4ae559a83a1aa280e6015fab99`.
The source reads test/sample dynamically and writes the full rehearsal before
development validation. Validation masks are restored and never affect test
predictions. No submission call is embedded in the kernel.

## Validation and comparison

Use the existing development cohort: 188 canonical identities, 876 spectra.
No sealed membership is embedded. Hide all development reference raw-key aliases
identified from query records and canonical candidates in their 30ppm windows.
Report MRR@25, Hit@1, Recall@25, truth presence in mass window, reference counts
and per-query ranks. Canonical alias detection outside those windows and overlap
in pretrained checkpoints/ranker training remain limitations.

Existing Goal 5 development B controls on this cohort: C1 mass-only MRR@25
0.3801; E8 C1 with expanded references MRR@25 0.4082. They use different reference
universes. E8 is not the submitted C1 + 127-reference pipeline; do not label the
comparison as a pure ranker ablation or as a measured improvement over that
submission's local MRR.

## Gate before official submission

Require completed offline run, verified asset/channel counts, finite development
metrics, candidate diagnostics, current test/sample ID agreement, 1–25 valid
unique scorer identities/row, bounded fallback count and runtime margin.
Interpret public-result differences only after fixing the exact kernel version.
If the control fails this gate, investigate the failure instead of spending a
submission. Present the completed evidence and candidate version to the user
before the official diagnostic submission, as agreed in the conversation.

Verification so far: fourteen unit cases pass (unchanged prediction-loop AST,
stereo deduplication/order, invalid-candidate rejection, development-only payload,
ten official adduct types). Public Na/K constants are slightly more precise
than the rounded local constants: Na differs by 2.701 microdalton, about
0.006ppm at 450.5Da. All ten conversions agree within 0.01ppm at that mass,
far smaller than the 8.5ppm retrieval window. This control retains public
constants; frozen E6 is not modified.
## Completed v2 measurements — 2026-10-13

Kaggle status COMPLETE. All seven outputs and log downloaded to
`artifacts/public_baseline/kaggle_v2/`. Pulled remote source equals the frozen
bundle after newline normalization (Kaggle pull writes CRLF on Windows).

Development: MRR@25 **0.5420906074**, Hit@1 **83/188 (44.15%)**,
Recall@25 **141/188 (75%)**, truth in retrieval mass window **188/188 (100%)**.
Joint mask removes 191 raw identity aliases; 2,498,313 reference spectra remain.
The 47 misses occur after mass-window retrieval, but this experiment does not
separate top-80 pruning from the final ranker. Pretrained overlap limitations
above still apply. Higher MRR than C1 mass-only 0.3801 and expanded-reference E8
0.4082 is an end-to-end diagnostic, not proof of hidden-test improvement.

Rehearsal: 400 queries / 1,213 spectra; 712,199 pool structures;
2,539,608 references / 275,632 analog representatives; two FPNet and eight GBMs.
Zero empty-window/CCO fallback rows; 1–25 candidates per row. Inference plus
writer 3,708.34 seconds; complete control including validation 6,568.87 seconds
(109.48 minutes), below the 10,800-second execution budget.
CSV SHA-256 `800e0359a4d80e6459cdda40e7cd42d99a2f22e35af2595432ad2f77ba365a4b`.

Independent local audit PASSED under RDKit 2026.03.3: exact sample ID order,
all candidates parse and have unique official scorer identities, first-occurrence
upstream ordering preserved, output hashes and measured metrics recomputed.
Four rows required deduplication. Gate saved as `public_submission_gate.json`.
RDKit emitted intermediate tautomer/kekulization warnings; all final candidates
passed parsing and identity checks. No official submission has been performed.
The user explicitly authorized submission on 2026-10-13. Exact kernel v2
submitted successfully at 12:08:58 UTC, submission ID **57143111**. Initial
status PENDING. Result observed 14:30:44 UTC (16:30:44 Europe/Rome):
**COMPLETE, public MRR@25 0.298, error_description empty**. No source/assets
changed. This establishes successful hidden execution and nonzero prediction
quality for this recipe. It does not isolate a cause of E6's first zero.

## Outcome and next experiments

| Submission | Pipeline | Official outcome |
|---|---|---|
| 57109254 | C0 + E6 | Public 0.000, error empty |
| 57135939 | C1 + E6 | Unhandled hidden-rerun error, no score |
| 57143111 | Public four-channel v2 | Public 0.298, error empty |

The development 0.5421 and hidden public 0.298 use different cohorts and the
former may overlap pretrained training. Do not treat their difference as a
quantified generalization gap. Keep exact v2 as reproducible reference.
Next evaluate offline controlled changes: C1 versus train+COCONUT under fixed
evidence, library/analog/FPNet/fragmentation ablations, and recall before/after
top80 pruning. Diagnose and fix the recovery's placeholder-dependent reference
count guard before any future recovery rerun. No further official submission
or training job authorized/started by this result.
