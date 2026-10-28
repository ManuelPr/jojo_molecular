# Experimental G3 Kaggle deployment — 23 October 2026

User requested immediate G3 integration and a leaderboard experiment instead
of further lengthy local validation. Explicit **SI** subsequently authorized
the private transfer of the13-file model package and its submission. Prior
automatic upload-review rejections are resolved; no additional consent is
required for this same task.

Private model dataset: `mperni/casmi26-g3-fusion-research-models`, **version1**,
ready, API `is_private=True`.12 data files plus dataset configuration;655,621
bytes including configuration. No spectra, validation labels or credentials.
Create returned a client JSON decode error after server success; status and
file listing reconciled it without another creation attempt.

Notebook: https://www.kaggle.com/code/mperni/casmi26-f0-g3-lightgbm-experiment

**Version1**, pushed successfully and RUNNING. Five original research dataset
versions remain fixed; the sixth mount is the private G3 datasetV1. Offline,
same requested T4/image as F0. F0 control notebook/submission57552927 stays
separate. No G3 official submission exists while finalizer state is
`waiting_for_notebook`.

## Inference change

Capture the main engine's numeric ranker/fingerprint/prior features, preserving
candidate order for identity deduplication. Copy real protonated GL scores
before the proxy update. After F0 has finished and written its own receipt,
reconstruct the same40-candidate metric-fusion pool and rank it by the
arithmetic mean of the five saved LightGBM fold predictions. Each model uses
its own saved median/mean/std preprocessing. This replaces the final heuristic
ordering and rank2 insertion; candidate retrieval and simulator code remain
unchanged. The visible smoke preserves untouched placeholder rows outside
the processed12 queries.

The deployment ensemble is a new experimental recipe. Local0.981667 was
out-of-fold scoring (one excluded model per query), not a measured leaderboard
score for this five-model deployment ensemble. Upstream pretrained exclusion
remains unverified; user explicitly accepts the experimental submission.

Essential technical checks completed without refitting: exact observable
feature assembly parity on7,729 cached rows; fold0 prediction maximum absolute
error **0.0** against its saved OOF scores; syntax and diff checks passed.

## Artifacts and automation

- `scripts/build_fastweb_g3_kaggle.py`: pinned builder.
- `kaggle/g3_fusion_overlay.py`: feature capture, inference and final receipt.
- `kaggle/assets/g3_fusion_v1/`: authorized private upload package.
- `kaggle/fastweb_g3_bundle/`: generated notebook/metadata/build manifest.
- `artifacts/kaggle/g3-lightgbm-v1/transfer-review.json`: exact payload hashes,
  explicit consent and confirmed private upload.
- `adapter-verification.json`, `kernel-push-receipt.json`: technical evidence.
- `submission-state.json`, `finalizer.log`, `finalizer.pid`: live state.

Detached finalizer already running:
`scripts/finalize_fastweb_g3_submission.py --version 1`.
It waits for COMPLETE, retrieves only CSV/G3 receipt using500-file pages,
checks model-manifest/output hashes and CSV structure, then submits **once**.
Do not start another finalizer or submit manually without reconciliation.
The returned official ID will be stored in `submission-state.json`.

Notebook SHA256:
`15ea28972cbc78cba3cadd83633c6bb26cdaa9418c87be5f8e38815b0b3779ac`.
Model manifest SHA256:
`687de35ac45149b878cf6e0d3515e20780fdab20e2ee639283541315a0da81cd`.

Keep existing job2545, venv and frozen splits. No G2/G4 or new allocation.
Read live state for current status; RUNNING is not an accepted submission or a
measured official result.


## G3 official submission accepted — 23 October 2026, 10:37 Europe/Rome

**G3 submission57554882 accepted**, private notebook
`mperni/casmi26-f0-g3-lightgbm-experiment` version1. User explicitly approved
the private13-file transfer and this experimental submission with SI. Model
datasetV1 is private and ready. Single-submit finalizer completed successfully;
**do not submit again or restart it**.

Visible smoke:400 CSV rows,12 processed queries,zero main errors. G3 reordered
all12 processed lists; overlay feature assembly/inference/audit took16.707s.
Model-manifest hash matches the approved package. The same-run F0 control CSV
hash equals the earlier F0 notebook output hash exactly, confirming the visible
control bytes are unchanged before applying G3. Output SHA256:
`9360cccd476a53bab0ac066dd60ffe348ab5f5464e44f8bdb38d3dd838da59dc`.

Official API currently reports **PENDING for both F0(57552927) and G3(57554882)**,
no public scores yet. No additional local research or retraining was performed.
Package/bundle/receipt/state hashes are in
`artifacts/kaggle/g3-lightgbm-v1/experiment-manifest.json`.
Next action: read official results when available and compare the two recipes;
no further submission is required to complete this authorized experiment.


## Official results — 23 October 2026

Authenticated Kaggle API confirms both submissions COMPLETE:

| Recipe | Submission | Public MRR@25 |
| --- | --- | --- |
| F0 fixed research control | 57552927 | 0.464 |
| F0 + G3 five-fold LightGBM mean | 57554882 | 0.388 |

G3 regresses by 0.076 absolute against F0. F0 matches the published 0.464
numerically and improves our previous 0.440 by 0.024; this does not certify
that historical asset versions or hidden predictions are identical.

The G3 local OOF 0.981667 on the 200-query public diagnostic panel did not
translate to the hidden public leaderboard. The panel is not a reliable
promotion criterion for this fusion. Upstream pretrained exposure remains
unverified; domain/feature shift and replacing F0 ranking protections are
hypotheses, not established causes. Deployment averages five models whereas
OOF uses the one excluded-fold model per query, another unisolated difference.

Decision: retain F0 as the competitive baseline; do not promote this G3 fusion.
Both authorized submissions are finished. No new training or submission was
started for this result check. Next research should diagnose the validation
and deployment mismatch before selecting a conservative fusion variant.

Fresh official API snapshots: `artifacts/kaggle/f0-gu-v1/official-results-2026-10-23.json`
and `artifacts/kaggle/g3-lightgbm-v1/official-results-2026-10-23.json`.
Earlier PENDING entries/manifests are historical snapshots, superseded by these
results; their recorded file hashes have been preserved.
