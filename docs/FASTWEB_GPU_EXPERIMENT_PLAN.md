# Fastweb GPU experiments — decision of 22 October 2026

## Environment status and next action

User-supplied remote report: existing Slurm job **2541**, **1 H100 80 GB**,
**8 logical CPUs, 32 GiB RAM**; CUDA forward/backward preflight passed.
Python 3.12.3, PyTorch 2.14.1/CUDA 13.0, RDKit 2026.03.3; 252 tests passed,
2 historical-artifact skips, 1 real-data test deselected; `pip check` passed.
These are reported remote results, not rerun or independently inspected here.
`train.parquet` and external CASMI weights were absent in the searched paths.
No training metric exists yet. The GPU is ready; scientific data preparation
and the competitive pipeline's cluster adaptation are the blocking work.

Keep the existing allocation and working environment. No new `sbatch`, package
upgrade, Kaggle submission or change to frozen split files is needed now.
The reported persistent locations are the checkout `.venv`,
`artifacts/cluster/fastweb-2541-20261022/`, and
`docs/FASTWEB_VERIFICATION_2026-10-22.md` on the remote checkout. Preserve those
local changes when integrating this update. Shared free NFS capacity (~511 TiB)
is not a personal quota. Verify quota and job lifetime before large transfers.

## 1. Stage reproducible inputs

`configs/fastweb_research_assets_2026-10-22.json` pins the newly inspected asset
versions. It is a **new research snapshot**, not proof of the historical mounts
used to obtain 0.464. Retain the existing v89 16-asset manifest as the historical
0.440 control. Do not silently replace its inputs with newer versions.

Official Kaggle API sizes checked today:

| Input | Size reported by API (decimal GB) | Priority |
|---|---:|---|
| Official train.parquet | 3.033 | First, plus test/sample for technical checks |
| Fold-safe FPNet V5 | 1.072 | First; checkpoints, contracts, trainer, audits |
| Natural-product panel V10 | 0.233 | First; diagnostic replay and split crosswalk |
| Attributed public assets V6 | 20.004 | Competitive pipeline, model code, caches, simulators |
| PubChem popularity prior V10 | 11.574 | Full candidate retrieval and aligned priors |
| Natural-product knowledge V9 | 0.135 | Reference/prior audit |
| PubChemLite CC0 fingerprints V1 | 0.361 | Already represented in the combined assets; separate source for isolated ablation |

The first three total ~4.34 GB; the full listed inputs ~36.4 GB, before expanded
caches, archives and experiment outputs. Reserve **at least 100 GiB of actual
personal quota** as an initial operating allowance, then measure. Do not load
the entire combined dataset into RAM. Stage to NFS; no large local Windows
downloads are needed. `scripts/cluster/plan_research_downloads.py` prints exact
pinned CLI commands and sizes without downloading or using credentials.

From the remote checkout, after preserving local changes and updating Git:

```bash
python scripts/cluster/plan_research_downloads.py --root "$PWD/data/fastweb" --group starter
```

Execute the printed commands using the user's existing Kaggle access on the
remote system. If the CLI is absent, install it in a separate tool environment
so the verified training venv stays stable. Credentials remain outside Git and
logs; do not accept new competition terms automatically. A single-file official
download may be zipped: inspect its result and extract `train.parquet` into the
competition directory before setting `CASMI_TRAIN_PATH`. Hash downloaded files,
record dataset versions and preserve licences. The download planner does not
prepare training caches or certify asset integrity.

Then run the existing data-aware preflight, without another setup:

```bash
export CASMI_TRAIN_PATH="$PWD/data/fastweb/competition/train.parquet"
export CASMI_OUTPUT_DIR="$PWD/artifacts/cluster/data-preflight-20261022"
bash scripts/cluster/run.sh preflight
```

## 2. Freeze the experiment contract before fitting

- Keep `configs/goal3_frozen_identities.txt` and
  `configs/goal5_prior_final_identities.txt` byte-identical. Crosswalk public fold
  identities to our official scorer keys. Additional splits/manifests are new
  versioned artifacts, never replacements for these files.
- Type-1 control: independent acquisitions with legitimate reference matches.
  Type-2 proxy: remove **all reference spectra of evaluation identities**, also
  external libraries, but keep their candidate structures. Type-3 proxy: remove
  the identity from every candidate source, cache and reference library; test
  recovery by generation. These proxies do not reveal hidden-test class labels.
- Validate a training query only with models excluding it. Public fold-k weights
  are safe only for matching fold-k queries and the separately excluded panel;
  averaging all five leaks training exposure for ordinary fold queries. Check
  normalised identities, tautomer equivalents and known pretrained overlaps.
- Full1, A+B and forward-model training overlaps must be labelled separately.
  A reference-excluded experiment with unverified pretrained exposure is a
  diagnostic comparison, not strict unseen-structure validation. Strict model
  evaluation requires audited excluded identities or refitting affected models.
- Separate ranker training, tuning, and a sealed final cohort. The public panel
  is diagnostic only. Do not inspect sealed outcomes repeatedly to tune rules.
- Build candidate/evidence tables with query identity, candidate scorer identity,
  provenance, inclusion/pruning stage, ranker/fingerprint scores, real/proxy
  adduct and CE, ICEBERG/GLACIER score **and missing/failed flags**, library
  confidence, prior, true-candidate label, split and model/data hashes.
  Missing score is not a zero-quality molecule.

## 3. Selected experiments, in order

All times below are **initial run budgets**, not duration predictions or reported
results. Each starts with a small timed pilot, persistent checkpoints/caches and
an explicit stop. Run one GPU experiment at a time on the existing allocation.

| ID | Experiment and isolated comparison | GPU / initial budget | Decision evidence |
|---|---|---|---|
| F0 | Port the fixed [Gu V492 V1 control](https://www.kaggle.com/code/guhongbin/casmi26-v492-dg-v19?scriptVersionId=361010883), preserve our v89 separately, export candidate/evidence tables | 32-query smoke; then 200 development queries; up to 2 h for first pilot | Correct source/assets, matching scorer identities, stage parity, measured RAM/VRAM, retrieval Recall@100/1000 and complete timing. Porting/CPU preparation time is additional. |
| G1 **first GPU experiment** | On a fixed candidate pool compare original protonated-only GLACIER + ICE fallback; N1A complement; joint ICEBERG + proxy GLACIER. Stratify [M+NH4]+ and water-loss queries | H100 inference, adaptive candidate batches; 30-min pilot then 2–4 h cap | Newly covered query/candidate pairs, paired MRR@25 delta and regressions, separate eligible/all-query denominators. Keep real [M+H]+ route unchanged. Multi-CE V49 is a separate low-priority ablation because public score regressed. |
| G2 **first training experiment** | Reproduce one identity-excluded FPNet fold; then one controlled change: multi-spectrum sampling OR same-formula hard negatives. Compare against safe frozen FPNet | Start batch 64, 2 workers, BF16 if supported; 200-step smoke then 4-h segment. Tune batch only after profiling | Query-level Recall@100/1000, MRR@25, same-formula errors and natural-product/adduct strata. Fixed training steps/data for the scientific comparison; resume if the full recipe needs more time. |
| G3 | Learn final fusion from cached evidence; compare existing heuristic fusion, LightGBM ranker, then a small neural pair/listwise scorer | LightGBM CPU baseline; H100 neural challenger only if warranted, 1–2 h cap | Paired validation MRR and protected library cohort; calibration and failed-score handling. If LightGBM matches it, ship LightGBM. GPU use alone is not a benefit. |
| G4 conditional | Bounded analog generation: 6 vs 12 parents, capped unique candidates, forward rescoring. No full SMILES foundation model from scratch | CPU generation plus H100 scoring, 1-h pilot then 2–4 h cap | Novelty-proxy coverage gain before ranking, chemical validity, no library regression. Only advance if missing-candidate errors justify it. Wider public parent expansion has already regressed in reported history. |

PubChemLite expansion is a separate F0/G1 pool ablation: compare fixed pools
first, then add candidates and measure coverage. This avoids attributing a
retrieval gain to a simulator or ranker. Do not hide expensive pool construction
inside a GPU timing number. Formula-constrained oracle diagnostics remain
separate from retrieval using only observable query inputs.

For G2, prefer the public architecture/training kit over a long legacy Goal 3
run: it connects directly to the competitive FPNet channel. Goal 3 is still a
bounded infrastructure regression test, not the new scientific priority.
The public trainer needs its `work/` caches, model source, `check_inputs.json`
and exclusion audit; **downloading train.parquet alone is not a launch command**.
Our new G1–G4 cluster adapters are not yet implemented or trained by this update.

## 4. Memory and runtime gates

- H100 80 GB is sufficient for the proposed pilots; allocation VRAM is not
  available as ordinary Python heap. Keep process-tree/cgroup RAM below a
  provisional **26 GiB**, leaving room under 32 GiB. Record the actual cgroup
  limit and memory events, not only parent-process RSS.
- Stream Parquet, memory-map numeric arrays and keep fingerprints packed.
  Avoid all-spectrum Python lists, full dense fingerprints and duplicate RDKit
  objects in workers. Start 2 workers, at most 4 only after measuring; set
  BLAS/torch thread counts consistently with 8 CPU cores.
- Adapt the public trainer's queue **64 -> 4**, workers **16 -> 2**, and record
  both changes. Its parsed `--hours` is not an enforced stop in the inspected
  code; use an enforced segment timer and smoke-step limit. Test finite loss,
  checkpoint save/resume and cancellation before long training.
- Preserve RDKit 2026.03.3 for scoring. Existing simulator packages have their
  own version/wheel assumptions; isolate them and test forward predictions on
  the H100 rather than reinstalling them into the validated main venv blindly.
- Cache simulation by candidate identity, model hash, adduct/proxy mode,
  instrument and CE/preprocessing contract. Hash data/splits and record seeds.
  Store raw per-energy scores for later cheap aggregation experiments.
- Estimate `T_total = T_setup + T_retrieval + N_pairs / measured_pairs_per_second
  + T_fusion` from pilot data, with multiple energies counted as separate jobs.
  Target <7 h on the actual Kaggle GPU for a conservative 2 h margin under the
  official 9 h limit. This is a target, not a demonstrated bound. Stress-test
  low-library-coverage queries; placeholder smoke runtime is not hidden runtime.
- Our previous visible v89 run took ~2 h 37 min; public pages often report only
  ~25 min smoke runs. Neither predicts H100 training time or worst-case scoring.
  The H100 is for research/training; final inference must still be offline and
  fit Kaggle resources. See [official competition constraints](https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra/overview).

## 5. Promotion and handoff

Select treatments on development data; report paired bootstrap intervals by
molecule, candidate coverage, rank changes, unsupported adducts, memory and
runtime. As an initial prespecified promotion gate, require positive development
delta with a paired 95% interval above zero and no library-control loss worse
than 0.002 MRR; assess power if the eligible cohort is too small, rather than
lowering the gate after seeing results. Freeze the chosen recipe and evaluate
sealed data once. A sealed failure returns it to research; repeated tuning
requires a new evaluation contract, not reuse of the same sealed labels.

Next remote task: integrate these documents without losing the verification
report, stage starter assets, verify train schema and quota, then stage pipeline
assets and implement F0/G1 with profiling. Return manifests, parity results,
coverage and resource estimates before a full G2 run. Do not claim the unchanged
0.440 has improved until measured; no Kaggle submission is launched by this plan.
