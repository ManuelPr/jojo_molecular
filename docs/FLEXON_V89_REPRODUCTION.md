# Faithful Flexon v89 reproduction — 2026-10-15

User requested reproducing the public solution before further improvements.
Previous measured control: 0.338; selective PubChem: 0.339. These recipes are
not reproductions of the two-engine E006/v89 pipeline.

Exact source: [Flexon v89, script 357683876](https://www.kaggle.com/code/flexonafft/casmi26-public-baseline-adaptation-experiments?scriptVersionId=357683876).
Original file is retained at `third_party/flexon_v89/upstream.ipynb`, SHA256
`c43e870c92bd67b2f0c0245c1b4064cfb1c49a1cbc81ffac349bee4708ad55a1`.
The page's recorded 0.440 is external evidence, not our score; the notebook
header identifies 0.440 as inherited E006 and claims no measured overlay gain.

All 16 datasetVersion IDs from the original notebook metadata were matched to
their owner/slug/version using the official API download redirect path, without
downloading dataset archives or retaining signed URLs. Pins and declared licence
labels: `configs/flexon_v89_assets.json`. Upstream attribution is preserved.

Builder: `scripts/build_flexon_v89_reproduction.py`. It preserves 34/35 source
cells exactly. Cell 11 changes only `IS_RERUN` to `True`, so the visible rehearsal
processes all 400 rows rather than the original 12. The normal full hidden path
uses the same algorithm. Prior execution outputs are removed; a read-only final
observer checks output identities, complete workload and both simulator stages.
No model, coefficient, retrieval gate or fusion policy was changed.

Private kernel: `mperni/casmi26-flexon-v89-faithful-reproduction`, GPU T4, Internet off.
Requested Docker digest: `37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`,
from the public kernel metadata pull. Original notebook image ID is 31430;
the historical ID-to-digest mapping has not been independently verified. Runtime
preflight requires Python 3.12 and main RDKit 2026.03.3; simulator RDKit is 2025.03.6.

Generated notebook SHA256:
`d62f05d4759fc8278cfda7185b96f11ff36d2cfa4a3fe273760729220747ab8b`.
The build manifest records each original and generated cell hash and dataset pin.

After completion, download the small CSV/JSON outputs and run
`scripts/audit_flexon_v89_reproduction.py`. Verify simulator coverage and errors,
all 400 processed IDs, hashes, independent chemical canonicalization, output
cardinality and runtime. The visible placeholder does not measure accuracy.
Record the same-run E004 and E006 controls and dual-polarity audit for later
diagnosis; do not optimize coefficients against the public score.

No official competition submission has been sent for this reproduction.

## Run v1 checkpoint

Kernel v1 successfully created and RUNNING on 2026-10-15. Read-back of the
server notebook confirms all 36 cell sources equal the generated bundle.
Independent AST comparison confirms the only change within original cells is
the `IS_RERUN` assignment; syntax checks and `git diff --check` passed.
At 08:54 UTC (10:54 Europe/Rome), preflight confirmed Python 3.12.13,
RDKit 2026.03.3, two Tesla T4 devices and all 64 V4 manifest files matching.
Full workload selected, ICE budget 5400 seconds. Engine2 subprocess is running;
its output is buffered by the original notebook, so no per-molecule progress
is currently exposed. Completion and independent output audit remain pending.

Monitor:
```powershell
kaggle kernels status mperni/casmi26-flexon-v89-faithful-reproduction
```

Progress snapshot: `artifacts/flexon_v89/progress_v1.log`.
Source returned by Kaggle: `artifacts/flexon_v89/server_v1/`.

## Replica Flexon v89 completata e verificata — 2026-10-15

Kernel `mperni/casmi26-flexon-v89-faithful-reproduction` v1 COMPLETE.
Runtime inferenza/osservatore 9432,59 s (2 h 37 min 13 s). Audit indipendente
PASS: 400/400 molecole elaborate, 25 identita valide e distinte per riga,
9863 SMILES verificati chimicamente, checksum corrispondenti. ICEBERG CUDA
371/371 molecole supportate, GLACIER CUDA 366/366; nessun errore di predizione
o feature. Output SHA256:
`fa8399db3f1f27054a3e874fbeedc2e83e2fd5ef6e804d14efb0687dd40f1dcc`.
Sul placeholder il fallback ICE modifica 5 liste e 1 top-1 rispetto a E004;
overlay dual-polarity v89 non attivo (0 eleggibili), output identico a E006.
Questo non misura accuratezza hidden. Replica tecnicamente pronta, score
ufficiale ancora non misurato e nessuna submission inviata per questa ricetta.
Artifact e audit: `artifacts/flexon_v89/output_v1/independent_audit.json`.


## Replica v89: submission ufficiale inviata — 2026-10-15

Utente autorizza con "andiamo" dopo audit completo. Inviata una sola submission,
**57229265**, da `mperni/casmi26-flexon-v89-faithful-reproduction` **v1**,
output `submission.csv`, alle **11:55:39 UTC / 13:55:39 Europe/Rome**.
Ricevuta Kaggle: 4 invii residui oggi. Stato iniziale **PENDING**, score pubblico
assente. Stato completo in `artifacts/flexon_v89/official_submission_status.json`.
La ricetta verificata e gli asset restano invariati. Attendere il rerun hidden;
non confondere esecuzione visibile riuscita e risultato ufficiale. Nessun invio
duplicato. Confrontare il futuro score con il nostro 0,339 e il riferimento
pubblico storico 0,440, senza assumere che quest'ultimo sia riprodotto.


## Risultato ufficiale replica v89: 0,440 — 2026-10-15

SDK verificato alle17:49:50 UTC (19:49:50 Europe/Rome): submission **57229265**
COMPLETE, public MRR@25 **0,440**, private assente, error_description vuoto.
Guadagno **+0,101** rispetto al miglior risultato precedente0,339, **+0,102**
rispetto a expanded+GLACIER0,338. Riprodotto lo score pubblico storico della
v89 alla precisione pubblicata; superato0,42. Non implica parita per molecola,
risultato private, o soluzione completa delle classi2/3. Congelare v1 e i16 asset
come nuova baseline competitiva. Fonte: `artifacts/flexon_v89/official_submission_status.json`.
La variante PubChem Forward Consensus resta separata e predefinita prima di
questo risultato: RUNNING, ICEBERG completo senza errori, GLACIER avviato;
finalizer PID16988 attivo. Non cambiare la variante in risposta allo score.
