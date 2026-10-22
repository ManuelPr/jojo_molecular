# Public 0.451 notebook audit — 2026-10-16

Read-only research requested after our v89 and PubChem consensus both scored
0.440. No notebook executed and no submission made during this audit.

## Verified score/version evidence

Kaggle browser pages displayed public and best score **0.451** for:

- [Eason V22 v1, script358828911](https://www.kaggle.com/code/easonyanyan/casmi26-v22-rel150-e2r2-clean?scriptVersionId=358828911).
- [Forensics Lab v4, script358862997](https://www.kaggle.com/code/saddamaditya/forensics-lab-the-apex-dossier-lb-0-442-sota?scriptVersionId=358862997).

Latest CLI pulls match those current version pages. Local sources and metadata
are under `artifacts/public_notebook_audit_2026-10-16/n0` and `n1`.
Notebook SHA256 respectively:
`d2e73414203593d7e731b9e33ae3f1507628a6c773c5863444a796b81e972854`,
`76c780de22d1ce8372542bf89b41afc9fd5180c014814e1cb4bb0f74defcd03a`.
The Forensics prose still says 0.447; the page score/version is authoritative.

## Changes relative to our reproduced Flexon v89

1. V22's inherited executable core through cell 31 retains the same engines,
   fingerprint models, simulator code and fusion. The promotion condition in
   cell 24 changes `rel > 250.0` to `rel > 150.0`. The library gate remains
   `lib_max < 0.9`; the alternative `(S > 6 and popularity >= 5)` remains.
   `rel` is the best non-pool raw fingerprint-fit margin against the best pool
   fit, not a probability. Promotion happens before engine fusion and can
   affect survival in its 40-candidate shortlist, not just final ordering.
2. Final E2R2 inserts Engine 2's top candidate at rank 2 when it is distinct
   from rank 1 under official metric identity. It preserves rank 1, removes
   equivalent copies, shifts other candidates and truncates to 25. It can
   therefore harm ranks 2–25 despite preserving top 1.
3. Input metadata replaces `prvsiyan/chebi-lipidmaps-casmi26` with
   `sergiomalv/casmi-chebi-lmsd-structures`. Engine 2 source is unchanged;
   visible V22 logs report 98,433 added ChEBI/LIPID MAPS structures and a
   788,589-structure Engine 2 pool. This does not mean all additions are new
   versus our old resource; exact set overlap and historical dataset versions
   remain to be audited. Author's +0.001–0.003 attribution is not our ablation.
4. Adds MetFrag-lite scoring (one/two bond cleavage fragment evidence) and
   weight-0.5 same-formula reranking where neither simulator provides evidence.
   This ranks existing candidates; it does not invent missing structures.
5. V22 omits v89's last dual-polarity PubChem overlay and does not attach the
   optional DreaMS tail or separate simulator-wheel resource. Thus the whole
   notebook comparison changes more than just the four headline additions.

## Two 0.451 recipes are related, but not identical

After removing standalone prose expressions, 15/18 aligned executable cells
have identical ASTs between V22 and Forensics v4, including the engines,
promotion rule and final E2R2. Differences: runtime preflight, fragment score
collection, and final fallback. Forensics additionally finds same-formula
groups without finite simulator scores even in otherwise covered molecules,
then invokes a second fragment rerank. It also attaches DreaMS and an extra
RDKit wheel dataset. Equal rounded public scores do not establish a benefit
from this additional group-level fallback or identical predictions.

## Interpretation and proposed next decision

The verified gap is +0.011 MRR@25, not +1.1 percentage points of accuracy.
Public score alone cannot identify class-2 versus class-3 gains or causal
component effects. Visible V22 is only a 12-molecule smoke: E2R2 changed zero
rows and PubChem promotions were zero; it cannot explain hidden-set gains.

Our last consensus overlay required forward-model agreement and did not change
visible rows. These public recipes instead broaden pre-fusion promotion and
protect a competing engine's answer near the top. That is a materially
different hypothesis, although a hard margin tuned on public scores may not
generalize.

Recommended next baseline is exact V22 v1 (simpler than Forensics v4), with
historical input versions and hashes resolved before reproduction. Preserve
same-run controls for E2R2/fragment changes, and validate threshold and catalog
changes using structure/library-held-out data. New official submission still
requires explicit authorization. Do not add our unhelpful consensus overlay
to this reproduction. Preserve upstream attribution and licences.
