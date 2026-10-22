# PubChem + GLACIER paired experiment

Started 2026-10-13; checkpoint updated 2026-10-14. User authorized implementation
and model testing with "VAI". No paid VM or new official submission.

## Assets and implementation

Frozen public-control source/FPNet/ranker assets from the measured public 0.298
pipeline are reused. PubChem v1 (`ahmedberatozer/casmi26-pubchem-tier`) has
105,875,489 mass-sorted structures encoded as mmap mass/offset/byte arrays,
150–1250 Da organic CHNOPS + halogens according to its card. Local full
extraction filled C: and was stopped; the experiment mounts PubChem on Kaggle.
Automatic review rejected recursive and individual deletion of the incomplete
local download; the user freed disk space manually. No other files removed.

Forward reference: `prvsiyan/casmi26-forward-reference-stack/2`, unmodified
ms-pred commit `708148c2a8eb0c32120644436fefd2fe90cd2214`, upstream open
MassSpecGym GLACIER checkpoint SHA256
`5a47cecca707d3abd5a49c7dbac99d100aa2a586d5d4f848f1e8e35140d7db11`.
No NIST weights. Source MIT; checkpoint provenance refers to the upstream
open-source MassSpecGym release. Package source/checkpoint/wheels verified
against producer provenance; parent RDKit remains official 2026.03.3.
Child: Linux Python 3.12.3, torch 2.6.0, RDKit 2025.03.6.
Native upstream DGL/LinSATNet are used, rather than the alternate pure-torch
shim package downloaded for comparison. Inference is isolated in a subprocess.

Probe v1 found system Python 3.12 had no pip. Probe v2 found missing aiohttp.
Dependency metadata was checked and the HTTP/numba closure added. Offline
wheel extraction is hash-checked, validates archive paths, and affects only
the isolated child environment. Private auxiliary wheel dataset
`mperni/casmi26-forward-aux-wheels/2`: 44 wheels, 161,506,807 bytes.

## Environment measurements

- CPU probe v3 COMPLETE: two real spectra, valid finite outputs, original model.
  Total 54.53s, model/runner 24.8s including 24.6s load.
- T4 GPU probe v4 COMPLETE: same two spectra. Fragment m/z arrays identical;
  max intensity difference 8.35e-7 / 7.15e-7. Total 174.75s including isolated
  CUDA environment extraction. Tiny-example throughput is not a batch benchmark.
- 19 unit cases passed (5 retrieval/fusion + 14 successful-control cases).
- Available GPU quota checked: 28.75 hours before probes. No paid VM.

## Protocol

Fixed unsealed development: 188 identities / 876 spectra. Joint reference mask
191 raw aliases, leaving 2,498,313 spectra. No sealed membership opened.
Pretrained identity overlap remains unknown. Five candidate variants:

1. `baseline80`: successful control's mass/library prune to 80.
2. `expanded`: all candidates in the same retrieval window, no prune80.
3. `pubchem`: expanded base + up to 50 external candidates, ranked together.
4. `catalog_withheld_baseline`: jointly remove development identities from
   the base candidate pool as well as their references.
5. `catalog_withheld_pubchem`: same withheld pool, independently retrieved
   PubChem candidates may rescue the known structures.

The catalog-withheld proxy is not true de-novo/Class-3 evaluation: structures
may be present in PubChem. Labels are used for the explicit pool mask and
metrics, never to inject or score a true PubChem candidate.

PubChem: 10ppm, screen the entire window with Morgan-2 logits, retain up to
2,000 for full 6,930-bit fingerprint scoring, return 50 canonical unique
external candidates. Screening and retained candidate counts are reported.
GLACIER computes the union of each variant's first 40 unique candidates once.
During evaluation each variant uses only its independently selected first40;
shared caching must not expand an ablation's forward budget.
Only positive [M+H]+ / finite CE are supported by the original runner. Other
queries preserve their base rankings. No silent setup/timeout fallback.
Weights 0/.25/.5/1/2 selected on four identity folds and evaluated on the fifth.
Pairwise bootstrap for per-molecule deltas; 0.9 direct-library confidence gate.
The official top25-then-deduplicate writer is preserved for fair comparison.

Retrieval/features are cached on CPU; GPU forward consumes a checksum-pinned
immutable cache without recomputing retrieval. This avoids spending GPU quota
on RDKit and reference preparation. No inference kernel/submission is produced
by these validation jobs.

## Preliminary 16-query cache (CPU v1 COMPLETE)

| Variant | MRR@25 | Candidate recall |
|---|---:|---:|
| baseline80 | 0.687500 | 81.25% |
| expanded | 0.817708 | 100% |
| pubchem | 0.458807 | 100% |
| catalog_withheld_baseline | 0 | 0% |
| catalog_withheld_pubchem | 0.403251 | 75% |

Every baseline reciprocal rank matches the earlier public-control development
report exactly (16/16). Removing prune80 recovers three missed true structures,
but its paired MRR delta CI95 [-0.0104, 0.3177] includes zero on this tiny sample.
Blind PubChem addition hurts the current 31-feature ranker; PubChem independently
rescues 12/16 when their base-pool identities are removed. These are preliminary
development measurements, not projected leaderboard gains.

Cache total 1,686.56s (28.11min), 345.95s actual per-query feature work;
15 supported queries and 991 eligible candidate structures for forward scoring.
Artifact: `artifacts/pubchem_glacier/features_v1/`.
CPU kernel hash `cff7be59466c4affbe963335dbd51aef227e4c0d731883b77da910628e639b39`.

## Kaggle validation jobs — 2026-10-14

- `mperni/casmi26-pubchem-glacier-forward` v1 COMPLETE: T4, rerank the pinned 16-query
  cache. Kernel SHA256 `fe83f9b4d75243b6f8ed8054e502b43ea75667813c206a1ee3acc54599ec27b3`.
- `mperni/casmi26-pubchem-glacier-features-full` v1: CPU, all 188 identities,
  same parameters, additionally exports ranker features for later diagnosis.
  Kernel SHA256 `56e6ff0c5648dd137e1f6feecd9938761bd237b2bbca730443071f2a2756bf86`.

Full CPU features are COMPLETE. Download reports with a file-pattern filter
to avoid copying runtime environments onto the user's nearly full C: drive.
Full paired results and forward contribution are recorded below. No job remains active.

## Corrected forward pilot — 2026-10-14

GPU16 consumed 15 supported queries, 2,474 predictions; model+runner129.8s,
total233.06s, steady predictions22.12/s. Setup/runtime errors absent.
Initial fusion incorrectly used scores selected by other variants from the
shared GPU cache. This gave standard PubChem OOF0.741667 and the withheld proxy
0.480903. Those numbers are superseded. Variant-local top40 masks were added,
regression-tested, and the immutable GPU predictions replayed without rerunning
the model. Corrected independent audit PASS, including cross-fit choices,
query identities, withheld-catalog separation, and baseline16/16 parity.

| Variant | Base MRR | Corrected forward OOF MRR |
|---|---:|---:|
| baseline80 | 0.687500 | 0.687500 |
| expanded | 0.817708 | 0.837240 |
| pubchem | 0.458807 | 0.609139 |
| catalog_withheld_baseline | 0 | 0 |
| catalog_withheld_pubchem | 0.403251 | 0.475694 |

PubChem forward delta+0.150332, CI95[0.021469,0.316675]. Expanded and withheld
forward-delta intervals include zero. The 16-query hash assignment has four
nonempty folds out of five slots; do not interpret pilot CV as definitive.
Artifact: `artifacts/pubchem_glacier/forward_v1_masked/` (original v1 retained).
Full188 forward uses the corrected mask from its first evaluation.
20 unit cases pass including the shared-cache budget regression.

## Full 188-query retrieval result — 2026-10-14

Feature CPU v1 COMPLETE in 3,806.35s. Independent audit PASS: all 188 baseline
reciprocal ranks match the frozen control exactly; cache checksums and catalog
withholding validated.

| Variant | MRR@25 | Hit@1 | Recall@25 | Candidate recall |
|---|---:|---:|---:|---:|
| baseline80 | 0.542091 | 44.15% | 75.00% | 77.66% |
| expanded | 0.690067 | 56.38% | 96.28% | 100% |
| pubchem | 0.386795 | 26.06% | 75.53% | 100% |
| catalog_withheld_baseline | 0 | 0 | 0 | 0 |
| catalog_withheld_pubchem | 0.352583 | 25.53% | 59.57% | 62.77% |

Removing prune80 improves MRR by 0.147976, paired CI95 [0.102533, 0.195222],
48 improved and 9 worsened queries. Blind PubChem addition has a negative
paired delta against baseline80: -0.155295, CI95 [-0.223056, -0.086185].
The withheld proxy measures independently retrieved top50 candidates, not
exhaustive PubChem coverage or genuinely novel molecules outside databases.
These are development results with unknown upstream training overlap.

Artifacts: `artifacts/pubchem_glacier/features_full_v1/`.
Manifest SHA256 `3f385fba4d9f6eefa38991be6f719e773fb9bb021fe6c1aafbd0a3dde26b13c0`.
GPU forward v2 launched on the pinned full cache: 159 supported queries,
11,772 unique query-candidate graphs. Kernel SHA256
`e47cb1825e422cf5a8253480d7e5490b552c3374acd1c407a189012487d419b7`.
No new official submission.

## Full forward and calibration results — 2026-10-14

GPU forward v2 COMPLETE, independent audit PASS,188 queries and baseline
parity188/188. Native GLACIER covered159 queries,28,653 predictions, no errors.
Runner1091.7s including17.2s load, steady26.67pred/s; whole kernel1586.10s.
Each variant uses its own top40; unsupported queries preserve native ranks.
Weights selected on the other four identity folds; expanded selects2.0 in all5.

| Variant | Native MRR | Forward OOF MRR |
|---|---:|---:|
| baseline80 | 0.542091 | 0.585428 |
| expanded | 0.690067 | **0.773666** |
| pubchem | 0.386795 | 0.533008 |
| catalog_withheld_baseline | 0 | 0 |
| catalog_withheld_pubchem | 0.352583 | 0.439629 |

Expanded forward delta+0.083600, paired CI95[0.042792,0.123562],45 improved,
13 worsened. Expanded+forward vs baseline80 total+0.231576,
CI95[0.172887,0.291719],73 improved,13 worsened. Forward Hit@1=67.02%,
Recall@25=96.28%. Original report `hit_at_1` and `recall_at_25` describe native
ranking; explicit forward metrics are in `experiment_summary.json`.
Artifacts: `artifacts/pubchem_glacier/forward_full_v2/`.

Fixed supervised calibration: HistGradientBoosting,depth4,150 iterations,
lr0.05,min leaf20,L2=1,5 canonical identity folds. Training excludes held query
identities and their identities as negative candidate rows. Same masks and
parameters compare36 features without GLACIER against39 with entropy/missing/z.
No hyperparameter sweep. All188 queries evaluated, including retrieval misses;
native ranks retained behind library gate0.9. Runtime versions and hashes saved.

| Protocol | Calibrated without GLACIER | Calibrated with GLACIER |
|---|---:|---:|
| PubChem join | 0.599697 | 0.651308 |
| Catalog-withheld PubChem | 0.380366 | 0.420117 |

GLACIER adds+0.051612 CI95[0.019219,0.084304] to calibrated standard join;
withheld proxy+0.039751 CI95[0.013727,0.066781]. Calibration improves standard
join over weighted forward0.533008, but remains below expanded+forward0.773666.
Withheld calibrated proxy is below weighted-forward0.439629, difference CI95
includes zero. Do not promote this ranker or the uncalibrated PubChem join.
Artifacts: `artifacts/pubchem_glacier/learned_ranker_full/`; lineage,fold,cohort
and metric audit PASS. Fitter assertions and tested helper enforce identity
exclusion; the audit did not independently refit model predictions.

Decision: preferred next candidate is expanded train+COCONUT plus GLACIER,
original FPNet/31-feature ranker and library protection. No new official
submission or production inference400 has been run. Before promotion:
library-holdout A with different reference acquisitions, full400 offline
runtime/format rehearsal, then explicit submission approval per master plan0.8.
Unknown pretrained identity overlap remains. Scores are development measurements,
not a guarantee of public score>0.42 or true de novo performance.
