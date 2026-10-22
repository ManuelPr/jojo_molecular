# Public notebook audit — 22 October 2026

## Evidence and scope

Kaggle CLI `kernels list --competition enveda-CASMI26-molecule-id-mass-spectra
--sort-by scoreDescending --page-size 30 --csv` supplied the discovery list.
Eight notebook sources were downloaded with the official CLI and inspected;
their Kaggle pages supplied the version/score badges below. This is a targeted
audit of leading public families, not an exhaustive leaderboard census.
`notebook_inventory.csv` records source hashes. Downloads and dataset metadata
are locally retained under `artifacts/public_notebook_audit_2026-10-22/`.

**Our measured baseline remains 0.440. The strongest public score verified in
this audit is 0.464.** Neither a title saying “top 1” nor CLI sort order proves
an overall leaderboard position. These public recipes have not been reproduced
by us. Scores are aggregate MRR@25, not accuracy or class-specific results.

| Notebook | Source inspected | Page evidence | Interpretation |
|---|---|---|---|
| [Dmitrii: Data Behind Spectra to Structures](https://www.kaggle.com/code/dmitriigluzdov/casmi-26-the-data-behind-spectra-to-structures) | V24 | Best **0.464 V20**, [script 361008383](https://www.kaggle.com/code/dmitriigluzdov/casmi-26-the-data-behind-spectra-to-structures?scriptVersionId=361008383); no current score displayed | Latest source is not the scored V20 artifact. Richest data/training documentation. |
| [Amr: upstream data v16](https://www.kaggle.com/code/amrkhalid124/casmi26-upstream-data-v16?scriptVersionId=360887011) | V1 | Current/best **0.464** | Same upstream family, not independent evidence for every component. |
| [Hongbin Gu: v492 dg v19](https://www.kaggle.com/code/guhongbin/casmi26-v492-dg-v19?scriptVersionId=361010883) | V1 | Current/best **0.464** | Preferred fixed public control to port; source and scored version match. Historical input versions still require binding. |
| [Lavin: lb top 1](https://www.kaggle.com/code/lavinwins/casmi-26-lb-top-1) | V3 | Best **0.464 V1**, [script 360745429](https://www.kaggle.com/code/lavinwins/casmi-26-lb-top-1?scriptVersionId=360745429); no current score displayed | Latest source advertises adduct reconciliation, deeper analog search and seed ensembles; these are not verified causes of the V1 score. |
| [Ahmed: v25 unq](https://www.kaggle.com/code/ahmedberatozer/casmi26-v25-unq?scriptVersionId=361057118) | V1 | Current/best **0.463** | N1 challenger plus cross-query rank-1 uniqueness. Do not adopt uniqueness without verifying the official identity-level premise. |
| [Flexon: Closing the Evidence Gap](https://www.kaggle.com/code/flexonafft/casmi26-closing-the-evidence-gap) | V49 | Current **0.457**; best **0.462 V47**, [script 360486019](https://www.kaggle.com/code/flexonafft/casmi26-closing-the-evidence-gap?scriptVersionId=360486019) | Multi-energy treatment regresses relative to its retained challenger control; do not call V49 an improvement. |
| [Prvsiyan: Analog Propagation](https://www.kaggle.com/code/prvsiyan/analog-propagation-casmi-2026-baseline?scriptVersionId=360497306) | V43 | Current/best **0.456** | Now a reproduction of Hongbin V465, rather than an independent new architecture. |
| [Dual-Gate Evidence Margin](https://www.kaggle.com/code/saddamaditya/dual-gate-evidence-margin-pubchemlite-cc0?scriptVersionId=360314907) | V2 | Current/best **0.456** | PubChemLite, N1A proxies, popularity 0.15 and alternative promotion gate. |

All eight notebook pages declare Apache-2.0 for notebook code. Attached data,
checkpoint and copied-component terms remain separate, including non-commercial
competition-derived assets. Attribution is retained.

## Changes that matter relative to our v89

1. **More candidate coverage in Engine 2.** PubChemLite CC0 fingerprints supplement
   training/COCONUT/ChEBI/LIPID MAPS. Newer PubChem priors include additional
   candidate stores and LOTUS/NPAtlas/depositor/synonym annotations. Membership
   and popularity are weak ranking features, not proof of molecular identity.
2. **GLACIER coverage where a real [M+H]+ spectrum is absent.** N1A makes proxy
   queries from [M+NH4]+ and [M-H2O+H]+ spectra. These are approximate views, not
   measured protonated spectra. The N1 challenger retains proxy GLACIER even
   when ICEBERG already has scores, and combines both for same-formula ranking.
   Source inspection confirms `N1_COMPLEMENT=False` and conditional joint fusion
   in the newer Dmitrii family. Our v89's protonated-only GLACIER cannot do this.
3. **Fingerprint models with explicit training exclusions.** The fold-safe asset
   supplies five FPNet checkpoints, each excluding one identity fold and all
   panel natural products. The newer PubChem channel uses
   `z_AB + 0.5 * mean(z_fold0..z_fold4)`. This ensemble is NOT out-of-fold for an
   ordinary training query: only its corresponding excluded-fold model is safe.
4. **Reference enrichment.** External MassBank/MoNA/GNPS reference records are
   added for structures already in training. This can aid library matching but
   must be removed by identity on the type-2 proxy, including external records.
5. **Ranking heuristics remain important.** Relative PubChem promotion threshold
   150, reduced popularity weight 0.15, E2R2 insertion and fragment fallback are
   still present. The Dual-Gate branch adds `rel > 130 and pop >= 2.5` alongside
   `rel > 150` (and retains the existing other gate). These are candidates for
   ablation, not established universal thresholds.

The upstream version history attributes 0.456 -> 0.464 to joint ICEBERG/proxy
GLACIER routing. It also reports increasing analog parents 6 -> 20 reduced
0.464 -> 0.456, recovered after reverting to six. Those historical component
claims are author-reported, not our controlled reruns. The current Flexon
0.457 and best V47 0.462 badges were independently checked on Kaggle.

The 250-natural-product panel is useful for replay and diagnosis, but it is
already used for public method selection. It is not our sealed evaluation set.
The source explicitly acknowledges that full1 saw the panel and FPNet A+B
training rosters are not fully documented. “Fold-safe FPNet” does not make the
whole pipeline leakage-free. Exact-answer formula and guaranteed-in-pool
comparisons must be labelled conditional diagnostics, not end-to-end MRR.
Absence from a limited PubChem tier does not establish true class 3.

## GPU opportunity supported by actual assets

[Fold-safe FPNet V5](https://www.kaggle.com/datasets/dmitriigluzdov/casmi26-fold-safe-fpnet/versions/5)
contains training code, five ~199 MB checkpoints, 10,226 output-bit indices,
input contracts, split audits and per-fold validation. We downloaded and read
the small README, model contract, trainer and validation JSON, without executing
upstream code or downloading the large weights locally.

The supplied training reports for folds 1–4 record **82,855 updates**, RTX 3080,
peak allocated GPU memory **10,753,815,552 bytes (~10.0 GiB)** and elapsed times
~9.35–15.67 hours. These are upstream measurements, not H100 measurements.
They support feasibility of a bounded FPNet experiment on H100, not a speedup
prediction. The trainer defaults to 16 workers and a 64-batch queue. Its
`--hours` argument is not an enforced loop stop in the inspected version;
`--segment_minutes` and `--smoke_steps` control termination. Adapt and audit
these before launch; preprocessing/caches are also required by `traindata`.

Decision: stage official data and these assets, reproduce fixed-control evidence
tables, prioritize simulator coverage and an identity-excluded fingerprint
experiment, then learn the final ranking. See [the Fastweb experiment plan](FASTWEB_GPU_EXPERIMENT_PLAN.md).
