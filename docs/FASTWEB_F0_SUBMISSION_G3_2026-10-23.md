# F0 submission and G3 research — 23 October 2026

The user explicitly authorized a submission a priori and concurrent research.
The previous prohibition on submitting is superseded for this one F0 control.
Keep the existing allocation2545, venv and frozen split files. No G2 or G4.

## Kaggle control

Private notebook: https://www.kaggle.com/code/mperni/casmi26-f0-gu-v492-research-control

Version **1**, built by `scripts/build_fastweb_f0_kaggle.py` from the fixed Gu
V492 V1 source. Original source SHA256:
`3b05fe5620f0bfe3acb319c782761acb61c61d283d8835b415a4d671cd841aa4`.
Upload notebook SHA256:
`caa9fedadcfd95acbb41031b69bb75a0d5178bfc7549f794d4ad1e283556a200`.
All prediction cells remain unchanged. Saved outputs are stripped. The copied
upstream numeric notebook ID is removed so the upload creates our own notebook.

Pinned research mounts: FPNetV5, panelV10, attributed assetsV6, popularityV10,
knowledgeV9. These do not certify the historical mounts behind public0.464.
Docker image and T4 selection match the upstream metadata; Internet is off.
No G3 models or rules are included in this control.

The original notebook runs a12-query visible smoke and processes the entire
hidden input on official rerun. Its visible CSV includes placeholder answers
for unprocessed IDs; these are **not** claimed as full-placeholder inference.
An early official-submit request was rejected by Kaggle with HTTP400,
`Notebook is still running. Did not find provided Notebook Output File.`
A diagnostic retry produced the same definitive rejection. The submissions
listing confirmed no new submission was created. Best official score remains
0.440, submissions57243687 and57229265.

`scripts/finalize_fastweb_f0_submission.py` now waits for the notebook to finish,
downloads only the CSV and small audit files, checks receipt/hash/row count,
then submits version1 **once** under the current user authorization. No retry
of the submission mutation. Reconcile by description before any restart.

Inspect these files before issuing another submission command:

- `artifacts/kaggle/f0-gu-v1/finalizer-state.json`
- `artifacts/kaggle/f0-gu-v1/finalizer.log`
- `artifacts/kaggle/f0-gu-v1/finalizer.pid`
- `kaggle/fastweb_f0_bundle/build-manifest.json`

There is no new official score until the submission service reports it.

## G3 experiment contract

Hypothesis: learning conditional simulator weights and handling unavailable
evidence can avoid the regressions of unconditional proxy fusion.

200 queries/957 spectra, deterministically stratified from the public panel,
excluding all16 pilot identities. The234 panel identities with available
`enveda-np-examples` acquisitions agree with the official scorer crosswalk.
Sixteen of250 panel entries lack these acquisitions; two also lack the training
identity crosswalk. These exclusions are explicit, not label corrections.
47,792 reference spectra removed, 2,491,816 retained; candidate structures stay
available. External reference exclusion is applied by the existing adapter.

The public pretrained overlaps remain unverified. Results will be **diagnostic**,
not strict unseen-structure validation or a basis for leaderboard claims.
No frozen project split is replaced. No sealed evaluation is used for tuning.

Fixed comparisons on identical final candidate pools:

1. Original protonated GLACIER plus ICE fallback, N1A complement, joint proxy.
2. LightGBM LambdaRank:120 trees,15 leaves, learning rate0.03, minimum40 rows
   per leaf, lambda1.0, two CPU threads.
3. CUDA neural listwise scorer: two64-unit SiLU hidden layers,60 epochs,
   AdamW learning rate0.002, weight decay0.01, gradient clipping1.0.

Five folds grouped by official identity, seed20261023. Median imputation and
scaling fit on training rows only. Query-local simulator normalization uses
only observable candidate evidence. Truth and identity never enter features.
Queries without a true candidate contribute zero in evaluation and are omitted
from ranker fitting. No hyperparameter search or automatic promotion.
Challengers replace final ordering on the same pool, including the effect of
replacing the inherited rank2 insertion. Compare protected library strata too;
the reference-excluded panel may supply few such cases.

The16-query CUDA smoke completed with finite loss, saved checkpoints and OOF
predictions;8 focused tests passed. Smoke MRR was0.921875 for LightGBM and
0.915179 for the neural scorer, versus0.871528 for protonated/ICE and0.804762
for joint proxy. This tiny previously inspected cohort verifies execution and
motivates the larger fixed experiment; it is **not** promotion evidence.

## Execution and limits

Detached orchestrator `scripts/cluster/run_g3_research.py` stays in job2545.
F0 wall cap3h, each simulator budget1800s, RAM guard26GiB; then a fusion stage
capped at10min. GPU experiments run sequentially. No new allocation, package
installation, FPNet G2 training or generator G4 expansion.

Artifacts under `artifacts/cluster/g3-dev200-2545/`:

- `panel-crosswalk-audit.json`, `competition/eligibility.json`, `competition/contract.json`
- `run-manifest.json`, `orchestration.log`, `orchestrator.pid`
- `control-profile/`: resources and bounded pipeline log
- `control/`: candidate/evidence exports and G1 comparisons, when complete
- `fusion/`: OOF predictions, per-query RR, checkpoints and results, when complete

Startup errors are preserved. Attempt1 resolved the venv Python symlink to
system Python and failed before inference; corrected by retaining the absolute
venv executable path. Attempt2 stopped at the RAM guard because stale file
cache accumulated. No OOM. POSIX_FADV_DONTNEED on172 research files released
cache without changing file bytes, reducing cgroup current22,978,764,800 to
1,801,043,968 bytes. Same26GiB guard on restart; audit in
`page-cache-advice.json`. Pipeline and trainer hashes are recorded in the
current run manifest; do not edit them during execution.

Status is deliberately read from the live artifacts above. A running experiment
does not imply successful completion, a measured gain, or a submitted notebook.


### Sequencing instruction — 23 October 2026

User: "resta in attesa e lancia submissions e training in sequenza".
F0 finalizer remains active. G3 orchestration parent is stopped with SIGSTOP;
its evidence-collection child continues normally. **After F0 state becomes
`submitted`, resume the PID in `g3-dev200-2545/orchestrator.pid` with SIGCONT**
(after checking its command line), allowing G3 training when evidence is ready.
Gate record: `artifacts/cluster/g3-dev200-2545/submission-sequence-gate.json`.
Do not launch a second F0 submission or a duplicate research pipeline.


### Official F0 submitted; G3 recovery — 23 October 2026

F0 submission **57552927**, notebook version1, accepted by Kaggle at
**09:09:58 Europe/Rome**; API status **PENDING**, no public score yet.
The visible notebook completed12 queries,400 CSV rows with388 placeholder
answers,0 main errors; ICEBERG and GLACIER CUDA stages both OK. Visible notebook
wall3200.93s (53m21s), including setup/analysis; not a full400 inference benchmark.
The finalizer hit429 while listing outputs in20-file pages; recovered with the
API maximum500-page size and reused audited local downloads before submitting.
Exactly one accepted F0 submission. Receipt/state under `artifacts/kaggle/f0-gu-v1/`.

The200-query run reached ICEBERG:178 covered queries,14,932 scored candidates,
40,743 predictions,zero prediction failures,319.05s. Its26GiB guard interrupted
GLACIER at3169.56s with peak cgroup28,183,703,552 bytes; no OOM. Retrieval/main/
PubChem/ICE are preserved. A lightweight recovery parent now loads only cached
candidate lists and ICE results, repeats interrupted GLACIER/N1, then exports
and trains G3. This removes the large reference index from simulator parent RAM.
Old stopped orchestration parent resumed after submission and exited on the
recorded guard failure; sequencing gate is released. Do not restart that old
full pipeline. Active successor: `scripts/cluster/run_g3_recovery.py`.
Live state: `artifacts/cluster/g3-dev200-2545/recovery-state.json`;
logs/resources in `recovery-profile/`, then `fusion-profile/`; source and cached
input hashes in `forward-recovery-manifest.json`. Same existingjob2545 andvenv;
no G2/G4. The official F0 recipe remains independent of this research.
