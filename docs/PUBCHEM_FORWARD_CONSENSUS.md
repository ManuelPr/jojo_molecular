# PubChem forward consensus — 2026-10-15

User explicitly requested one additional submission for today, aimed at known
structures without reference spectra (type 2), different from the ongoing v89
submission 57229265. This authorizes one official submission after audit.

Hypothesis: an external PubChem identity lacks a vote from the second engine
and may be demoted during fusion even when its own retrieval evidence is strong.
Preserve the complete v89 recipe, then restore the independent PubChem lead
only with strict forward agreement. This is a limited ranking correction, not
a solution to all type-2 identification, and adds no new candidate coverage.

All 36 reproduction cells are preserved. One read-only snapshot before simulator
reranking records the initial PubChem ordering and the existing source gate:
library <0.9 and ((S>6 and popularity>=5) or fingerprint margin>250).
After the complete v89 output, promote that initial external lead only if it
strictly beats every scored rival in the base/external union, with at least two
scored base and two scored external metric identities. GLACIER is selected when
the inherited gl_of has evidence, otherwise ICEBERG. No switching simulator by
which one prefers the candidate. Missing evidence, ties, strong libraries and
unconfident source predictions preserve the baseline. No extra simulator run.

## Evidence and limits

Frozen PG1 component proxy (188 paired identities):

| Cohort | Selective control MRR | Consensus MRR | Promotions |
|---|---:|---:|---:|
| Known catalog | 0.771306 | 0.771306 | 0 |
| Catalog-withheld proxy | 0.043579 | 0.079483 | 13 |

Withheld paired delta +0.035904, bootstrap CI95 [0.015957, 0.059840], nine
improvements and zero regressions. This proxy uses the old probability<0.3 gate
and old fingerprint/ranker/GLACIER recipe. It does NOT validate the full v89
treatment or its source-confidence gate; upstream pretraining overlap is unknown.
It supports the component hypothesis only. No leaderboard-based threshold tuning.
Artifacts: `artifacts/pubchem_consensus/component_replay.json`.

Six new unit tests pass, plus two existing selective-policy tests. No-network
finalizer checks pass: audit failure prevents submission, success allows exactly
one request, repeat execution is blocked by a durable intent file.

## Execution

Private kernel `mperni/casmi26-pubchem-forward-consensus` v1 is RUNNING, full400,
T4, Internet off, same sixteen pinned datasets as v89. Notebook SHA256:
`90073608b8ac26e3d34cbe738e3959ca0f6d64e41d564837ffa3bca399b161dc`.

Builder: `scripts/build_pubchem_consensus_submission.py`.
Auditor: `scripts/audit_pubchem_consensus_submission.py`.
Finalizer: `scripts/finalize_pubchem_consensus.py`, launched as a hidden local
Python process. It polls at 60 seconds, refreshes existing OAuth, verifies server
source equality, downloads only relevant outputs, audits the same-run v89 control
and treatment, then submits exactly kernel version 1 once. It stops on errors,
audit failure, an existing submission intent, or after 2026-10-15 24:00 Europe/Rome.
Submission network mutation is never automatically retried if ambiguous.

The local computer must remain running for the finalizer; the Kaggle kernel
itself runs remotely. State, PID and logs are in `artifacts/pubchem_consensus/`.
Do not manually submit while the finalizer is active. Inspect
`finalizer_state.json`, `submission_receipt.json` and `submit_intent.json` before
any recovery. No official submission has been sent at this launch checkpoint.

The visible placeholder may produce an inactive treatment because of strong
library matches; that does not establish hidden inactivity or accuracy.

## Riparazione PubChem Consensus v2 — 2026-10-15

La v1 e terminata ERROR nell'ultima cella: json.dumps(evidence) non accetta
chiavi tuple. Il helper upstream metric_identity restituisce (InChIKey14,
heavy_atom_composition), mentre overlay e auditor richiedevano identita stringa.
Base e simulatori completati, ma nessuna submission ufficiale inviata: finalizer
fermato senza submit_intent. Corretto l'adattatore per usare l'upstream
canonicalize_smiles_to_ik14 (componente canonica ufficiale) senza cambiare
coefficienti, modelli o regola di promozione. Aggiunti due test d'integrazione
CSV/JSON con identita upstream tuple, ramo protetto e ramo promozione attivo.
8 test policy/integration PASS; finalizer single-submit verificato senza rete.

Kernel `mperni/casmi26-pubchem-forward-consensus` **v2 RUNNING** dalle circa
20:08 Europe/Rome. SHA256 notebook:
`aa23745fbb0ca5955f5bf9eed8e0aaac3cf88af9fd84e42a0daeddb35f068586`.
Finalizer riavviato PID5728, fissato a v2 e nuovo hash, stessa autorizzazione
per UN invio entro mezzanotte locale, solo dopo audit. Log v1 conservato;
nuovi log finalizer_v2_stdout/stderr.log. Nessun invio duplicato manuale.


## PubChem Consensus v2 COMPLETE e submission inviata — 2026-10-15

Kernel `mperni/casmi26-pubchem-forward-consensus` v2 COMPLETE. Audit indipendente
PASS: controllo v89 e trattamento,400/400 righe e replay,25 candidati validi e
distinti per riga,9863 SMILES verificati sul controllo. ICEBERG371 e GLACIER366
molecole supportate, senza errori. Overlay sul placeholder inattivo:0 eleggibili,
0 liste modificate. Questo non misura l'attivazione sul hidden.
Il finalizer ha inviato UNA submission **57243687** alle20:42:13UTC
(**22:42:13 Europe/Rome**), dopo audit superato. SDK alle20:55:49UTC:
**PENDING**, public score assente, error_description vuoto.
Receipt: `artifacts/pubchem_consensus/submission_receipt.json`; audit e output
in `artifacts/pubchem_consensus/output_v2/`; stato ufficiale completo in
`artifacts/pubchem_consensus/official_submission_status.json`.
Confronto atteso con baseline v89 **0,440**. Non inviare duplicati; finalizer
terminato dopo invio e submit_intent persistente impedisce ripetizioni.


## PubChem Consensus: risultato ufficiale invariato0,440 — 2026-10-16

SDK verificato08:52:22UTC: submission **57243687 COMPLETE**, public **0,440**,
private assente, error_description vuoto. Baseline v89 **57229265 = 0,440**;
delta alla precisione pubblicata **0,000**. Nessun guadagno pubblico dimostrato.
Il punteggio arrotondato aggregato non prova predizioni identiche: gate inattivo,
modifiche senza effetto sui ranghi corretti, compensazioni o delta sotto la
precisione pubblicata restano possibili. Il placeholder aveva0 eleggibili;
questo non stabilisce l'attivazione sul hidden.

Decisione: conservare la v89 come baseline primaria; Consensus resta esperimento
senza beneficio misurato, non promuoverlo come miglioramento. Il replay PG1
(+0,035904 su proxy fuori catalogo) usava gate e modelli diversi dalla v89:
era evidenza del componente, insufficiente per prevedere un guadagno end-to-end.
Prima di altre submission costruire una validazione della pipeline v89 effettiva
con identita escluse dalle reference spettrali, strutture mantenute nei cataloghi
per proxy tipo2 e coorte separata di controllo library. Separare copertura del
pool, perdita nel pruning, rango prima/dopo fusione e promozioni realmente utili.
Non allentare soglie sulla base del solo public; nessun nuovo invio autorizzato.
Fonte: `artifacts/pubchem_consensus/official_submission_status.json`.
