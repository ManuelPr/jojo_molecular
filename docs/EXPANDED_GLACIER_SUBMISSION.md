# Expanded train + COCONUT + GLACIER submission

2026-10-14: user explicitly requested preparation and official submission:
"va bene! fallo", in response to the proposed expanded train+COCONUT + GLACIER
submission after full400 offline runtime/format checks. This authorizes one
new official submission once the concrete inference artifact passes its audit.
No paid VM. Master plan0.8 approval requirement satisfied by this instruction.

Configuration frozen from PG1: full same8.5ppm/fallback30ppm candidate window,
no prune80, no PubChem, original two fingerprint models and eight31-feature
rankers. GLACIER MassSpecGym top40 unique candidates, weight2.0 selected in all
five development folds, library protection0.9, original top25 raw then scorer
identity deduplication. Unsupported GLACIER cases preserve the native ranking.
Empty mass windows retain the baseline's explicitly counted singleCCO fallback.

Validation measured0.773666 OOF on188 queries; unknown pretrained overlap.
This does not predict public score>0.42. Library-holdout A remains unmeasured;
user chose a diagnostic official submission as the next informative test.

Self-contained hidden rerun: reads actual competition test.parquet and sample
at runtime; train/library universe is unmasked for inference. No development
IDs, ground-truth labels, precomputed test prediction cache, or parent kernels.
No dependency on placeholder counts or post-filter library counts. FPNet
explicitly remains CPU to match the validated feature protocol; GLACIER runs
in its hash-verified isolated native CUDA environment. CPU references are
released before model inference. Assets use the same pinned versions and hashes.

Builder: `scripts/build_expanded_glacier_submission.py`.
Runtime: `kaggle/expanded_glacier_submission.py`.
Local audit: `scripts/audit_expanded_glacier_submission.py`.
Kernel: `mperni/casmi26-expanded-glacier-submission`; initial build SHA256
`03ec3a5623a847b65719ecaf030c73b1fd250a714098205d9586c91f428e06bc`.
Status: v1 pushed2026-10-14 at12:45UTC (14:45Europe/Rome), T4, offline,
28800s runtime cap. Production writer exactly reproduces all188 validated
expanded+GLACIER rankings;9 targeted unit tests PASS. Quota before launch28.19
GPU hours remaining. No official submission sent yet; full400 run pending.
Submission ID and score will be recorded after the full run/audit/official send.

Fresh authenticated API preflight2026-10-14: registered entrant, submissions
enabled,0 submitted today,5 available. Official code requirements allow CPU/GPU
up to9h, internetoff, freely available external data/pretrained models, filename
submission.csv. Deadline2026-12-14 at23:59UTC. Metric pins RDKit2026.03.3 and
allows fewer than25 guesses. Full published page contents and allowance saved
in `artifacts/expanded_glacier/competition_preflight.json`.
Full v1 COMPLETE:400 rows,3940.85s,0 empty-window fallbacks. All400 visible
queries have library confidence>=0.9, so production correctly preserves native
ranking and skips GLACIER.366 have supported spectra,959 supported acquisitions,
but the hidden rerun may differ. Do not claim GPU forward was exercised here.

Local audit PASS:400/400 ID/order/writer replay,9229 unique output SMILES
independently normalized with scorer RDKit,1–25 distinct identities per row.
Submission SHA256 `f9651baa046c08b45d80581145308d6bad2c7191df7b3fcff887a146a7467cd0`.
Artifacts `artifacts/expanded_glacier/kaggle_v1/`.

Integration check launched: `mperni/casmi26-expanded-glacier-branch-probe` v1,
same mounted datasets and exact production `if items` AST block, two prior
compatibility-only caffeine/aspirin inputs. It produces no competition CSV and
does not alter production v1. Probe SHA256
`220c8dcd78e8768ba7c9440f55f8403dc7a4298e03d39f395469b11af8f1f0f7`.
Probe COMPLETE and verified: exact production branch succeeds with the same
dataset mounts, native CUDA,2 predictions, no errors. Scope compatibility only.
Artifacts `artifacts/expanded_glacier/branch_probe_v1/`.

## Official submission sent — 2026-10-14

Authorized official submission **57184698**, production kernel **v1**, saved
scriptVersionId358339073, submitted14:01:44UTC /16:01:44Europe/Rome.
Kaggle receipt PENDING, score absent, error_description empty.4 submissions
remaining today. Do not submit duplicates; monitor this exact reference through
the full API including hidden error_description. Request, version, source/output
hashes and receipt preserved in `artifacts/expanded_glacier/`.

Official result checked 2026-10-14 15:50:28 UTC: submission **57184698** is
`COMPLETE`, public MRR@25 **0.338**, private score absent, error_description
empty. Compared with public-control **57143111** at 0.298, the measured public
gain is **+0.040** (about 13.4% relative). This is below the 0.42 target and
below the informal 0.35–0.38 expectation stated before scoring. The public
metric alone does not reveal class proportions, candidate recall, GLACIER
activation, or per-molecule errors on the hidden rerun. The visible 400-row
placeholder remains a technical rehearsal, not an accuracy estimate. Exact API
response: `artifacts/expanded_glacier/official_submission_status.json`.

Unlabelled visible comparison to the frozen public-control v2: first identity
preserved400/400; lower-ranked identity lists change367/400. This is evidence
of first-choice preservation on library-confident visible inputs, not an
accuracy estimate or a different-acquisition library-holdout A. Comparison
artifact `kaggle_v1/comparison_to_public_baseline.json`.
