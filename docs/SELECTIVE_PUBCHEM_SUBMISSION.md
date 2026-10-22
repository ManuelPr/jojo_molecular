# Selective PubChem diagnostic submission — 2026-10-14

User authorized both the experiment and one official Kaggle submission:
"facciamolo, facciamo anche una submission". No paid VM is involved.

The control is the measured expanded train+COCONUT + GLACIER kernel v1,
submission 57184698, public MRR@25 0.338. The new kernel preserves that
model's base scoring, top-40 GLACIER policy and strong-library protection. It
opens a PubChem branch only when direct-library confidence is below 0.9 and
the maximum base ranker probability is below 0.3. It screens the full PubChem
mass window at 10 ppm with coarse Morgan bits, full-scores up to 2,000 and
retains 50 metric-distinct external candidates. Existing ranker probabilities
order those external candidates among themselves. At most five enter output
slots 4, 8, 12, 16 and 20. The base top-1 cannot change. The PubChem branch
uses no hidden labels, precomputed test predictions or internet during inference.

The gate and slots are a conservative diagnostic policy, not a calibrated
optimum. The key offline replay used the pinned 188-query feature and GLACIER
caches, with a separate 188-query catalog-withheld proxy:

| Cohort | Control MRR@25 | Selective MRR@25 | Changed lists | Changed top-1 |
|---|---:|---:|---:|---:|
| Known catalog | 0.773666 | 0.771306 | 58 | 0 |
| Catalog withheld proxy | 0 | 0.043579 | 87 | 0 |

Known-catalog paired delta -0.002360 (bootstrap CI95
[-0.003652, -0.001145]); proxy delta +0.043579 (CI95
[0.030680, 0.056356]). The proxy tests rescue when the correct structure is
removed from the base catalog; it is not a true hidden Class-2 sample. The
normal cohort is not an unbiased score forecast because the upstream model
training overlap is unknown. Both results come from
`artifacts/selective_pubchem/offline_replay.json`, which pins source cache
hashes. The development replay was read-only and did not execute notebook code.

Implementation: `src/casmi26/selective_pubchem.py`,
`kaggle/selective_pubchem_submission.py`,
`scripts/build_selective_pubchem_submission.py`,
`scripts/audit_selective_pubchem_submission.py`. The generated bundle has
SHA256 `99901a6ba679b0020b899a3505411dc4cd7d974cb11b80b70a5fac5b53f84e05`.
Eleven targeted tests passed; source compiles. Kaggle private kernel
`mperni/casmi26-selective-pubchem-submission` v1 was pushed on 2026-10-14,
T4, internet disabled, 28,800-second cap. It must complete a 400-row visible
rehearsal and independent output audit before the authorized official submit.
The visible 400 are placeholders and do not measure hidden accuracy.

The v1 visible run completed in 4092.94 seconds with 400/400 output rows.
Independent audit passed: 400/400 writer replay, 9,229 distinct output SMILES
normalized with RDKit 2026.03.3, valid distinct metric identities and the
expected source/output hashes. The visible placeholder has 400 protected
library queries, zero PubChem-eligible queries and zero GLACIER inputs. Its
`submission.csv` SHA256 is
`f9651baa046c08b45d80581145308d6bad2c7191df7b3fcff887a146a7467cd0`,
identical to the earlier expanded control on that placeholder. This is a
technical no-op only on the visible data; hidden branch activation is unknown.
Audit: `artifacts/selective_pubchem/kaggle_v1/independent_audit.json`.

Official submission **57196384** sent from kernel v1 on 2026-10-14 at
22:07:59 UTC (2026-10-15 00:07:59 Europe/Rome). Initial full API status:
`PENDING`, public score absent, `error_description` empty. Receipt/status:
`artifacts/selective_pubchem/official_submission_status.json`.
Final SDK check on 2026-10-15 at 08:41:00 UTC (10:41 Europe/Rome):
**COMPLETE**, public MRR@25 **0.339**, private score absent and error empty.
The difference from control 57184698 (0.338) is **+0.001 at published precision**.
This is the best measured public artifact so far, but the small aggregate
improvement does not establish private-set robustness or identify rescued
Class-2 molecules. Hidden per-query rankings and gate activation are not exposed.
Keep both frozen artifacts. Diagnose candidate recall and conditional ranking
offline before testing calibrated fusion that can promote external candidates
to rank 1; the fixed slots were a diagnostic restriction, not the final design.
Monitoring is complete; no duplicate or additional official submission was sent.
