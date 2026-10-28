# Stato progetto CASMI 2026

## Fastweb verificato; aggiornamento pubblico e selezione esperimenti — 2026-10-22

Dal report remoto fornito dall'utente: job esistente 2541, H100 80 GB, 8 CPU
logiche, 32 GiB RAM; CUDA forward/backward e pip check passati; 252 test passati,
2 saltati, 1 real-data escluso. Train e pesi non trovati: nessun training eseguito.
Report recepito, non rieseguito da questa macchina. Preservare ambiente e split.

Audit odierno: 30 notebook scoperti via CLI, 8 sorgenti scaricati e pagine score
controllate. Migliore score pubblico verificato 0.464 (Gu V492 V1, Amr V1,
Dmitrii best V20); nostro best ancora 0.440. Flexon V49 = 0.457 contro V47 =
0.462: ensemble multi-CE non promosso. Nuovi asset: FPNet fold-safe, PubChemLite,
panel diagnostico e librerie/priors aggiornati. I fold pubblici non sostituiscono
i nostri split congelati; full1/A+B/simulatori richiedono audit overlap separato.

Selezionati F0 porting/tabelle competitive, G1 proxy GLACIER + ICEBERG, G2 FPNet
identity-excluded, G3 ranker finale; G4 generazione solo se manca copertura.
Documenti: `docs/PUBLIC_NOTEBOOK_GAP_2026-10-22.md`, `docs/notebook_inventory.csv`,
`docs/FASTWEB_GPU_EXPERIMENT_PLAN.md`. Manifest snapshot dati con versioni e
dimensioni API e planner di download senza esecuzione aggiunti. Nessun nuovo
modello addestrato, job o submission avviato. Fonte/score verificati non implicano
pin storici dei dataset: la riproduzione 0.464 deve ancora risolverli.
Verifiche locali dell'aggiornamento: planner starter/full coerente fra JSON e
shell, quoting di percorsi con spazi e percorsi POSIX corretto, 8 hash sorgente
registrati, `git diff --check` passato. Nessun download massivo locale.

## Verifica pod Fastweb — 2026-10-22

Job esistente 2541: 1 H100 80GB, 8 CPU logiche, RAM job 32 GiB.
Setup persistente `.venv` completato (Python 3.12.3, torch 2.14.1/CUDA13.0,
RDKit 2026.3.3). Preflight CUDA forward/backward PASS e pip check PASS.
Suite: 252 passed, 2 skipped (artifact storico Goal 4 assente), 1 real-data
deselected, 64,86 s; inclusa integrazione Goal 3 sintetica.
Dati e pesi CASMI non trovati nella home e nello spazio di gruppo verificato;
Goal 3 a 2 epoche NON ESEGUITO per assenza train.parquet. Nessuna nuova
allocazione, submission o modifica degli split congelati. Evidenze persistenti:
`artifacts/cluster/fastweb-2541-20261022/`. Dettagli e requisiti della validazione
del ranker finale in [FASTWEB_VERIFICATION_2026-10-22.md](FASTWEB_VERIFICATION_2026-10-22.md).

## Handoff GitHub / Fastweb — 2026-10-22

Richiesta utente: pubblicare il lavoro su `ManuelPr/jojo_molecular` per clonarlo
nel job GPU / VS Code gia allocato. Aggiunti README, guida
`docs/FASTWEB_HANDOFF.md`, setup venv Linux, launcher Goal 3 / validation,
template Slurm senza account/partition inventati e preflight CUDA con vero
forward/backward. Dati, credenziali, pesi e output esclusi da Git; attribuzioni
upstream conservate. Replica v89 ricostruita con hash notebook invariato
`d62f05d4759fc8278cfda7185b96f11ff36d2cfa4a3fe273760729220747ab8b`.
Verifiche locali: 247 test passati, 7 saltati per PyTorch assente, 1 test
real-data escluso; sintassi Bash verificata. Il calcolo CUDA reale resta da
eseguire nell'allocazione Fastweb: nessuna GPU locale NVIDIA disponibile.
Il nuovo ranker finale e il generatore discussi in chat non sono addestrati;
Goal 3 e un esperimento esistente, distinto dal notebook Kaggle da0,440.
Nessun job cluster o submission Kaggle avviato da questo handoff.

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

2026-10-15: richiesta utente di caricare la copia code-only per condivisione
con Gustar8. Creato notebook privato `mperni/casmi26-code-only` v1; verifica
read-back PASS (18 celle identiche alla copia locale). Nessun invito inviato
e nessuna submission ufficiale per questa copia.

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

## Nuova submission tipo 2 autorizzata e in preparazione — 2026-10-15

Utente richiede un ultimo invio oggi, diverso dalla v89. Kernel privato
`mperni/casmi26-pubchem-forward-consensus` v1 RUNNING: v89 invariata piu
promozione del primo candidato PubChem solo su confidenza originale e stretto
accordo del simulatore. Proxy componente188: catalogo noto invariato0,771306;
catalogo escluso0,043579 -> 0,079483 (9 recuperi,0 regressioni). Non e una
validazione end-to-end v89: gate e modelli del proxy differiscono.
8 test policy PASS, finalizer verificato senza rete. Processo locale nascosto
attende COMPLETE, verifica sorgente/audit400, quindi invia v1 UNA volta entro
mezzanotte Europe/Rome; si ferma su errori. Non duplicare manualmente l'invio.
Stato in `artifacts/pubchem_consensus/finalizer_state.json`; dettagli in
`PUBCHEM_FORWARD_CONSENSUS.md`. V89 57229265 ancora PENDING alle15:31UTC.

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

## Riproduzione fedele Flexon v89 — 2026-10-15

Utente: "riproduciamolo e poi capiamo come migliorare". Priorita alla replica
della ricetta completa, dopo PubChem selettivo 0,339. Sorgente v89 fissato,
16 versioni dataset storiche risolte via API. 34/35 celle identiche; unica
modifica operativa: prova visibile completa400 invece di smoke12. Osservatore
finale aggiunto senza cambiare ranking. Kernel privato
`mperni/casmi26-flexon-v89-faithful-reproduction` v1 avviato, T4, offline.
Attendere esito e audit indipendente; nessuna submission ufficiale inviata.
Dettagli, hash e limiti in `FLEXON_V89_REPRODUCTION.md`.

## Esito PubChem selettivo — 2026-10-15

Verifica SDK alle 08:41 UTC (10:41 Europe/Rome): submission **57196384**
`COMPLETE`, public MRR@25 **0,339**, errore vuoto. Controllo **57184698**:
**0,338**; delta sui punteggi pubblicati **+0,001**. Conservare questa versione
come miglior risultato pubblico misurato, insieme al controllo congelato.
Il piccolo delta non dimostra robustezza sul private né identifica le classi
recuperate. Gli slot fissi preservano top-1 ma limitano il contributo esterno.
Prossimo confronto offline: recall PubChem e ranking condizionato alla presenza
della truth, poi fusione calibrata che consenta rank 1, proteggendo i library
match affidabili. Nessun nuovo invio da questo aggiornamento.

2026-10-14: l'utente ha autorizzato un esperimento PubChem selettivo e una
submission ufficiale. Replay offline appaiato: catalogo noto 0,773666 ->
0,771306 MRR; proxy catalogo escluso 0 -> 0,043579, top-1 preservata in
entrambi. Kernel privato `mperni/casmi26-selective-pubchem-submission` v1
COMPLETE in4092,94s; audit400 PASS. Invio ufficiale **57196384** alle22:07:59
UTC, stato iniziale PENDING, score non ancora disponibile. Dettagli in
`SELECTIVE_PUBCHEM_SUBMISSION.md`.

Audit notebook pubblici 2026-10-14: confrontati sorgenti Kaggle sopra 0,338.
Il gap verificabile riguarda soprattutto PubChem selettivo, seconda pipeline
BIO/AFIX, ICEBERG di fallback e fusione su identità scorer. La versione esatta
Flexon v89 da 0,440 è stata recuperata via browser: rispetto a v90 da 0,415,
le prime34 celle sono identiche e cambia solo l'esperimento finale (dual vs
joint PubChem). Il delta pubblico non prova la causa per singola molecola.
Vedere `PUBLIC_NOTEBOOK_GAP_2026-10-14.md`.

## Risultato expanded + GLACIER — 2026-10-14

Submission ufficiale **57184698**: `COMPLETE`, public MRR@25 **0,338**,
errore API vuoto (controllo SDK 15:50:28 UTC). Guadagno misurato **+0,040**
rispetto al controllo pubblico 57143111 a 0,298; obiettivo 0,42 non raggiunto.
Il 0,773666 OOF sui 188 development non era predittivo del leaderboard hidden.
Le 400 righe visibili sono un placeholder dal training; l'API non rivela classi,
recall candidati né attivazione GLACIER sul test nascosto. Nessun nuovo invio
automatico. Dettagli e risposta API in `EXPANDED_GLACIER_SUBMISSION.md`.

## Submission expanded + GLACIER autorizzata — 2026-10-14

Utente: "va bene! fallo", dopo proposta di inferenza400/audit/invio ufficiale.
Autorizzata una nuova submission della configurazione migliore PG1, senza
PubChem. Notebook autonomo hidden-safe in preparazione, niente cache test
come parent e niente ID development incorporati. Writer mantiene il cutoff
raw25 e dedup scorer. Nove test passati; parità188/188 verificata.
Kernel `mperni/casmi26-expanded-glacier-submission` v1 avviato14:45Europe/Rome,
GPU T4, offline. Hash03ec3a5623a847b65719ecaf030c73b1fd250a714098205d9586c91f428e06bc.
Dettagli e checkpoint in `EXPANDED_GLACIER_SUBMISSION.md`. Prima invio:
rehearsal400 completo e audit di file/ranking/runtime/hash.
Rehearsal v1 ora COMPLETE in3940,85s,400/400,zero fallback. Audit PASS:
9229 SMILES normalizzati indipendentemente,writer replay400/400. Tutte400
query visibili protette da matchlibrary>=.9; ramoGL non attivato. Probe di
integrazione dello stesso ramo e degli stessi mount v1 in corso, per coprire
il percorso potenzialmente attivo sul hidden. Probe ora COMPLETE e PASS,
2 predizioni CUDA reali sul ramo identico. Invio ufficiale già eseguito:
**57184698**,kernel v1,16:01:44Europe/Rome,stato PENDING; score ancora assente.
4 invii disponibili oggi. Monitorare questo ID, non inviare duplicati.

## PubChem + GLACIER: esperimento completato — 2026-10-14

Utente ha autorizzato i test. Probe CPU v3 e GPU v4 COMPLETE, parità spettri
verificata (m/z identici, intensità max delta 8,35e-7). Cache CPU 16 query
COMPLETE: baseline MRR 0,6875, no prune80 0,8177, PubChem aggiunto 0,4588;
proxy catalogo nascosto + PubChem 0,4033, recall 12/16. Piccolo campione,
nessuna stima di score pubblico. Controllo baseline riproduce 16/16 RR precedenti.
Forward16 GPU COMPLETE; replay corretto per budget locale per variante:
expanded OOF0,8372, PubChem OOF0,6091, proxy catalogo nascosto OOF0,4757.
Prima fusione con budget condiviso sovrastimava PubChem0,7417; rettificata,
test regressione e audit indipendente PASS. Feature CPU188 COMPLETE v1:
baseline0,542091 (parità188/188), expanded0,690067, PubChem0,386795,
proxy catalogo nascosto0,352583. Expanded delta+0,147976 CI95[0,102533;0,195222].
Audit indipendente PASS. Forward GPU188 v2 COMPLETE e audit PASS:
expanded OOF0,773666 (delta forward+0,083600 CI95[0,042792;0,123562]),
PubChem OOF0,533008, proxy catalogo nascosto OOF0,439629.159 query supportate,
28.653 predizioni, runtime totale1586,10s; budget locale corretto.
Ranker ricalibrato39 feature OOF: PubChem0,651308, proxy0,420117; inferiori
ai migliori candidati dei rispettivi protocolli. Preferire expanded
train+COCONUT + GLACIER. Prima di promozione: library-holdout A e rehearsal400.
Dettagli, hash e asset in `PUBCHEM_GLACIER_EXPERIMENT.md`. Nessun nuovo invio.

## Submission diagnostica riuscita — 2026-10-13

**57143111**, public four-channel kernel v2: COMPLETE, **public MRR@25 0,298**,
errore API vuoto. Osservato alle 16:30:44 Europe/Rome (14:30:44 UTC).
Prima 57109254: score 0.000; seconda 57135939: crash hidden, score assente.
Nuova baseline valida sul hidden; differenze multiple non isolano la causa del
primo zero. Conservare v2 e asset/hash come controllo, avviare prossimi confronti
offline con ablation e recall prima/dopo pruning. Nessun altro invio/job.

## Rettifica stato submission precedente — 2026-10-13

Lettura completa API: `57109254` public `0.000`, errore assente; `57135939`
public score assente, errore non gestito durante il rerun hidden. COMPLETE
non significa necessariamente successo. Le sezioni storiche che indicano un
secondo zero sono superate: la recovery C1 non ha prodotto una misura hidden.
Dettagli conservati in `artifacts/public_baseline/kaggle_v2/official_submissions_detail.json`.

Possibile causa crash riprodotta: recovery richiede esattamente 127 reference
dopo filtro duplicati dipendente dal test. Rehearsal 128-1=127; assenza del
duplicato hidden porterebbe a 128 e RuntimeError. AST guard verificato a 127/128.
Non è conferma del traceback hidden. Vedere `ZERO_SCORE_ROOT_CAUSE.md`.

## Public baseline control in corso — 2026-10-13

Su richiesta dell'utente è stato preparato il controllo pubblico storico a
quattro canali. Sorgente upstream e loop di ranking preservati, asset con hash
e versioni fissati, development 188/876, CPU offline. Kernel privato
`mperni/casmi26-public-baseline-control` v2 COMPLETE. v1 falliva subito
per wheel RDKit cp312 incompatibile con Python 3.13; corretto usando il wheel
cp313 già verificato. Quattordici test passati; nessuna submission ufficiale.
Inferenza 400/400; development MRR@25 0,5421, Hit@1 83/188, Recall@25 141/188,
truth in mass window 188/188. Runtime completo 6568,87 secondi, zero fallback.
Audit locale CSV PASS (ID, ordine, identità valide/uniche, hash e metriche);
quattro righe deduplicate. Metriche non sono uno score hidden né un holdout
garantito dei checkpoint pubblici. Nessuna submission ufficiale inviata.
Report: `PUBLIC_BASELINE_CONTROL.md`. Output e sorgente scaricati e sorgente
normalizzata verificata. Gate superato e utente ha autorizzato esplicitamente:
submission ufficiale v2 **57143111**, 2026-10-13 12:08:58 UTC, terminata
con public 0,298 senza errore. Nessun invio duplicato.

L'access token OAuth è scaduto durante il monitoraggio. Il client Kaggle 2.2.4
controlla la scadenza con un ritardo di 30 minuti; `refresh_access_token()`
dell'SDK ufficiale ha rinnovato la sessione esistente senza nuova autenticazione
interattiva e senza esporre credenziali. Monitoraggio ripristinato.

## Audit differenziale aggiornato — 2026-10-13

Dopo due score visualizzati 0,000, causa hidden non identificata. La coverage
C0 non è una spiegazione sufficiente. E6 non riproduce la baseline pubblica:
127 reference, top-5 analoghi, nessun canale direct-library/FPNet/fragmentation
nel punteggio e fusione vincolata alla formula nearest-mass. Diagnostica locale:
`scripts/audit_submission_ranking_limits.py`; report
[PUBLIC_PIPELINE_DIFFERENTIAL_AUDIT.md](PUBLIC_PIPELINE_DIFFERENTIAL_AUDIT.md).
Priorità: confronto offline a C1 fisso prima di attribuire lo zero soltanto
alla coverage o ampliare il database. Nessun job o invio in questo audit.
Le sezioni sotto sono checkpoint storici, superati da questo audit quando
attribuiscono confidenza alta alla causa hidden.

## Recovery checkpoint — 2026-10-12

Audit locale completato senza training, job Kaggle o apertura del sealed
holdout. Sul proxy domain-matched development (188 identità, 876 spettri), C0
copre 108 truth (57,45%) e C1 188 (100%). C1 raggiunge Candidate
Recall@25/100/1000 89,89/99,47/100%, ma la mass-only MRR@25 è 0,3801 contro
0,4069 di C0 perché i competitor same-formula medi crescono da 1,55 a 14,18.

Tutti gli addotti osservati sono supportati; errore massa neutra mediano 1,65
ppm e p90 3,12 ppm. La causa primaria più probabile del public 0,000 è candidate
coverage/selection bias closed-world, con domain shift e sole 127 reference
spettrali come co-cause. C2/C3 non sono stati costruiti.

Goal 5 v4 è terminato `COMPLETE`. Artifact e log sono stati scaricati una sola
volta; durata effettiva dal log 8 h 21 min 46,64 s, oltre il budget di 8 ore.
E8/C1 migliora coverage e Hit@5/10 ma non Hit@1; i delta MRR vs E7 non sono
stabili fra A/B e sealed. Non viene promosso. Goal 6 resta non iniziato e
nessuna seconda submission è autorizzata.

Report: [ZERO_SCORE_ROOT_CAUSE.md](ZERO_SCORE_ROOT_CAUSE.md),
[EXTERNAL_COVERAGE_ANALYSIS.md](EXTERNAL_COVERAGE_ANALYSIS.md) e
[RECOVERY_EXPERIMENT_PLAN.md](RECOVERY_EXPERIMENT_PLAN.md).

Ultimo aggiornamento: 2026-10-12, calibrazione leaderboard 16:42 Europe/Rome

## Stato sintetico

I Goal 1–4 sono completati. **Goal 5 dispone ora di un artifact terminale ma
nessun E8–E12 è promosso; Goal 6 non è iniziato.** Il riferimento end-to-end promosso resta il
realistic benchmark Goal 4 E6, target-blind, con catalogo canonico di 49.195
strutture. Le metriche E7–E12 sono disponibili e mostrano più coverage, ma non
un delta MRR/Hit@1 stabile.

Il run autorevole è il kernel Kaggle privato
`mperni/casmi26-goal4-spectral-ranking`, versione 4, offline. E6 è promosso
come nuova baseline: analog propagation sul top-100 nearest-mass, confinata al
gruppo di formula dell'anchor E0. La prima submission ufficiale è stata
completata: public MRR@25 visualizzato 0,000, rank 3139/3140 allo snapshot.

## Checkpoint Goal 5

Completati:

- baseline E6 congelata e verificata tramite hash e signature;
- C1 full-train costruito: 271.439 strutture canoniche, 50.662 formule, indice
  checksummed/mmap da 34.821.876 byte;
- retrieval mass/formula esatto, pool dinamici, analog prefilter scalabile,
  staged reranking e union/RRF E12;
- protocollo domain-matched A/B/C con 234 identità, 188 development, 46 sealed,
  1.097 spettri query e 2.932 reference capped;
- adapter DreaMS frozen e decisione `NOT RUN / environment-blocked`;
- bundle Kaggle privato offline senza chiamate di submission;
- metriche E7–E12 development/sealed, paired bootstrap, candidate recall e
  diagnostiche domain-shift recuperate dal job v4 terminale;
- suite locale: 204 passed, 7 skipped; `compileall` e `git diff --check`
  verificati prima del checkpoint.

Non completati:

- DreaMS scientific probe nell'ambiente Python 3.11 isolato;
- cataloghi esterni C2/C3, non scaricati né importati;
- ladder controllata per isolare l'effetto del numero di reference;
- nuova pipeline candidata con ranking capace di recuperare Hit@1.

### Job Kaggle

`mperni/casmi26-goal5-scalable-retrieval` v4 è terminato `COMPLETE`. Il log
effettivo copre 30.106,64 s (8 h 21 min 46,64 s). Artifact e log sono stati
scaricati una sola volta sotto `artifacts/goal5_kaggle_v4/`; nessun nuovo job o
submission è stato avviato.

La v2 ha raggiunto il limite dopo circa 43.084 s conservando indice e piani di
dominio. La v3 è terminata in errore dopo 10.254,6 s (2 h 50 min 54,6 s) per
un anchor E12 esterno alla union pool; il bug è corretto e coperto da test. La
v4 ha completato E7–E12 ma ha superato il limite operativo di 8 ore: non va
rilanciata su Kaggle.

### Workflow deciso

- Locale: scrittura codice e unit test brevi.
- Kaggle: smoke test e inferenza offline.
- VM esterna: canonicalizzazione, preprocessing e benchmark lunghi.

Nessuna VM esterna o GPU a pagamento è stata avviata. L'unica submission
autorizzata è E6 v4; nessuna submission Goal 5 è stata effettuata.
La prossima azione è archiviare v4 e spostare la ladder reference/C2-C3 sulla
VM; non avviare un run Kaggle sostitutivo.

## Evidenza Goal 4

| Split realistic | E0 MRR@25 | E6 MRR@25 | Delta paired | IC95% | Hit@1 E0 → E6 |
|---|---:|---:|---:|---:|---:|
| Development, 16 | 0,349104 | 0,365473 | +0,016369 | [+0,001938; +0,033939] | 0,2500 → 0,2500 |
| Final, 16 | 0,401331 | 0,438549 | +0,037218 | [-0,001770; +0,103166] | 0,3125 → 0,3750 |
| All-validation, 32 | 0,375217 | 0,402011 | +0,026794 | [+0,003121; +0,061990] | 0,2813 → 0,3125 |

Candidate Recall@25/100/1000 resta 0,875/1,000/1,000 perché E0–E7 usano lo
stesso pool top-100. Su tutte le query E6 ne migliora 9, ne peggiora 2 e ne
lascia 21 invariate. E1 ed E2 selezionano peso zero. E5 LambdaRank è negativo
sul development e non viene selezionato, anche se il final piccolo mostra un
valore elevato e instabile.

## Benchmark e leakage

- Catalogo sorgente: 49.620 strutture; catalogo canonico: 49.195; reject: 425.
- Validation: 32 identità, 96 spettri, tutte `enveda-180`/`timsTOF`.
- Zero target consultation, prioritization o injection.
- Recall@100=1 è spiegata da truth rank massimo 78; quattro target sono oltre
  rank 25 (29, 46, 37, 78).
- 26/32 query hanno competitor same-formula; 18 errori E0 sono proxy di
  isomeria costituzionale.
- Reference train identity-OOF e validation identity/content-disjoint.
- Nel rehearsal sul test placeholder una reference duplicata per contenuto
  spettrale è stata esclusa automaticamente: 128 reference iniziali, 127
  utilizzate. Il report del rerun hidden non è esposto.

## Componenti Goal 4

- `spectral_evidence.py`: peak matching, cosine/modified/shifted, entropy,
  neutral losses monoisotopiche e aggregazione multi-spettro.
- `analog_propagation.py`: retrieval analogico, mass shift, relazione
  strutturale, compatibilità frammenti/addotto e guardie anti-leakage.
- `goal4_audit.py`: distribuzioni ppm, rank, breakdown e tassonomia errori.
- `candidate_catalogs.py`: canonicalizzazione, deduplica, mass/formula index,
  mmap e fingerprint bit-packed.
- `goal4_ranking.py` e `goal4_pipeline.py`: E0–E7, selection development-only,
  bootstrap appaiato e resource accounting.
- `goal4_inference.py`: catalogo target-blind e inferenza E6 offline.

## Inferenza e calibrazione pubblica

Il CSV di rehearsal Kaggle v4 contiene 400 molecule ID ed esattamente 25 SMILES
validi e unici per riga. SHA-256:
`52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f`.
Benchmark e selezione richiedono 672,53 s; l'inferenza test 1.500,43 s. Peak
RSS è 1,69 GB e la pipeline non alloca VRAM.

Dopo approvazione esplicita, la stessa versione 4 è stata inviata come
submission `57109254` alle `2026-10-12T13:54:59.493Z`. Stato `COMPLETE`, public
MRR@25 visualizzato 0,000, rank 3139/3140 alle `14:42:23Z`. Il runtime hidden
non è esposto; il turnaround osservato è 2.769,79–2.816,43 s. Nessun nuovo
commit Kaggle, tuning o secondo invio.

## Qualità

- Unit test: 153 passati, 7 skip PyTorch opzionali.
- Coverage: 66% su 5.197 statement; moduli Goal 4 centrali 87–93%, ranking 91%.
- `compileall` e `git diff --check`: passati.
- E2E Kaggle offline: passato su train/test ufficiali.
- Nessuna VM a pagamento o grande training; una sola submission E6 autorizzata.

## Decisione successiva

Goal 5 segue principalmente lo Scenario C: ampliare e indicizzare la libreria
spettrale leakage-safe, migliorare retrieval analogico/confidence e provare
DreaMS soltanto come embedding congelato. L'espansione Tier 1 del catalogo va
misurata in parallelo. ICEBERG/GLACIER diventano prioritari solo se il residuo
same-formula dimostra la necessità di forward spectral reranking.

Dettagli: [GOAL4_SPECTRAL_RANKING_REPORT.md](GOAL4_SPECTRAL_RANKING_REPORT.md),
[CANDIDATE_COVERAGE_REPORT.md](CANDIDATE_COVERAGE_REPORT.md) e
[LEADERBOARD_CALIBRATION.md](LEADERBOARD_CALIBRATION.md).

## Esito prima submission ufficiale

La baseline Goal 4 E6 è stata inviata una volta dalla versione Kaggle 4 già
`COMPLETE`, senza modifiche e senza includere Goal 5. Lo score pubblico
visualizzato 0,000 mostra che la validation locale closed-world non è
rappresentativa della pipeline hidden end-to-end.

L'ipotesi primaria è candidate coverage/novelty: il catalogo E6 è train-only e
il reranker non può recuperare strutture assenti. È un'inferenza, non una prova
diretta sulle truth hidden. La priorità successiva, quando Goal 5 riprenderà, è
validare offline un candidate generator open-world prima di un'altra
submission. Dettagli in `FIRST_SUBMISSION_PRECHECK.md` e
`LEADERBOARD_CALIBRATION.md`.

## Recovery C1 e seconda submission — 2026-10-13

Il percorso candidato è ora fail-fast e replica lo scorer ufficiale rimuovendo
la stereochimica prima della canonicalizzazione tautomerica. Il bug di
canonicalizzazione non cambiava però nessuno dei 10.000 slot della prima
submission. Il bug di catalogo C0 è stato corretto sostituendo 49.195
strutture con l'indice C1 verificato da 271.439, mantenendo E6 congelato.

Kaggle recovery v2 è `COMPLETE`: 400 query, 1.213 spettri, 25 candidati/riga,
127 reference, runtime 1.119,35 s e 210 test passati (7 skip opzionali). La
seconda submission autorizzata `57135939` è `COMPLETE`, public 0,000, rank
3189/3193. C1 non è quindi sufficiente. Goal 6 resta non iniziato; nessuna
terza submission. La priorità è C2 COCONUT e scaling reference su VM con
evidenza offline, poi un nuovo gate esplicito.


## Starter/F0/G1 — aggiornamento sessione 22 ottobre 2026

2541 cancellato secondo Slurm; uso del 2545 esistente autorizzato in chat.
Piano starter e manifest preparati; download bloccati da accesso Kaggle assente,
quota personale non verificata. Preflight con dati e F0/G1 non eseguiti.
Venv e split conservati; nessuna nuova allocazione o submission.
Dettagli: [FASTWEB_STARTER_STATUS_2026-10-22.md](FASTWEB_STARTER_STATUS_2026-10-22.md).


### Ripresa con accesso Kaggle — 22 ottobre 2026

Starter completo (4.342.989.049 byte); FPNet V5: 55/55 checksum pubblicati
corrispondenti. Preflight vero train.parquet PASS, 2.539.608 righe e CUDA PASS.
Sorgente Gu V492 V1 hash esatto recuperato ed estrazione sicura engine/N1A
preparata. Sottoinsieme simulatori V6 verificato, caricamento CUDA GLACIER e
ICEBERG PASS in sito isolato (zero predizioni, non G1).
F0 end-to-end e tabelle evidenze ancora da implementare su asset completi;
G1/MRR/copertura/throughput non misurati. Quota NFS RPC irraggiungibile.
Report e manifest: [FASTWEB_STARTER_STATUS_2026-10-22.md](FASTWEB_STARTER_STATUS_2026-10-22.md).


## F0/G1 completati sul pilot — 23 ottobre 2026

421 asset aggiuntivi (24.853.073.596 byte) fissati e hashati; venv/split
preservati. F0 su job2545, 16 query/58 spettri; 3.490 reference training
e 2 esterne escluse, candidati mantenuti. Inferenze CUDA senza fallimenti;
recupero analisi CPU byte-identico. MRR diagnostico: baseline 0,871528,
N1 complement 0,811111, joint 0,804762. Copertura16/16; forward8/16→12/16.
Nessuna promozione: esposizione pretrained non esclusa e proxy in regressione.
Stima conservativa H100200 query≈2,69h; nessuna run completa/G2/G4/submission.
Report: [FASTWEB_F0_G1_RESULTS_2026-10-23.md](FASTWEB_F0_G1_RESULTS_2026-10-23.md).


## F0 submission authorized and G3 research started — 2026-10-23

User explicitly requested the F0 submission a priori and useful computation in
parallel. Notebook `mperni/casmi26-f0-gu-v492-research-control` **version 1** was
pushed privately with unchanged prediction cells and research mounts
FPNet5/panel10/assets6/prior10/knowledge9. This does not certify the historical
0.464 input mounts. Official best score checked via API remains 0.440.
Kaggle rejected early submission with HTTP400: notebook still running/output
unavailable; no submission was created by those requests. A single-submission
finalizer is running; inspect its state before any further submission command:
`artifacts/kaggle/f0-gu-v1/finalizer-state.json`.

Research: 200 new panel queries/957 spectra, disjoint from pilot16; excluded
47,792 reference spectra, retaining 2,491,816. The panel has 234 available NP
queries; 16 panel entries lack NP acquisitions, including two without the
training crosswalk. No official-scorer mismatch in the 234 available identities.
Eligibility and crosswalk exclusions are explicit artifacts. Existing frozen
split files are unchanged. Full1/A+B/forward pretrained exposure is still not
certified, so this is diagnostic, not strict unseen-structure evaluation.

New G3 adapter compares fixed heuristics, five identity-grouped OOF LambdaRank
models and a small CUDA listwise neural challenger on identical candidate pools.
No hyperparameter search or automatic model promotion; no G2/G4. Eight focused
tests and a real CUDA smoke passed. Pilot16 OOF results are software diagnostics,
not grounds for changing the Kaggle control. Research orchestration is detached
inside existing job2545, 3h F0 cap, 26GiB guard, then <=10min fusion segment.
Status: `artifacts/cluster/g3-dev200-2545/run-manifest.json`.

Two startup failures are preserved: resolving the venv symlink selected system
Python (fixed before inference); then the RAM guard stopped accumulated file
cache (no OOM). POSIX_FADV_DONTNEED on our own research files released stale
cache, reducing current cgroup usage from22.98GB to1.80GB without changing any
file bytes; the same26GiB guard is retained on restart. No new allocation or
venv changes. Details: `FASTWEB_F0_SUBMISSION_G3_2026-10-23.md`.


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


## Completed F0 submission and G3 — 23 October 2026, 09:46 Europe/Rome

Official F0 submission **57552927**, notebook `mperni/casmi26-f0-gu-v492-research-control`
version1, is **PENDING**, no public score. Do not submit it again. Best measured
official score remains0.440. Research successor `recovery-state.json` is now
**complete**, returncodes0 for recovery and training; the older monolithic
`run-manifest.json` correctly records its RAM-guard failure.

200-query/957-spectrum diagnostics completed, fixed7,729 candidates and36,810
pairs, truth coverage200/200. Actual F0 joint MRR0.910871; five-fold OOF
LightGBM0.981667 (delta+0.070795, diagnostic paired95%[+0.042879,+0.101137],
24 improvements/1 regression); neural0.978333. All200 final-F0 RR values match
the joint arm; learned metrics independently checked from OOF scores. Neural
has no demonstrated advantage over LightGBM. No G3 model promoted/submitted:
public-panel/upstream pretrained exposure remains unverified, no sealed test.

80,001 successful forward predictions, zero failures. Lightweight forward
recovery1593.34s, peak sampled RAM10.52GiB; G3 fit3.84s (profile8.10s), CUDA
challenger and all checkpoints saved. Ten focused tests pass, frozen split
hashes unchanged, no venv/new allocation/G2/G4. No active research training
remains. F0 official hidden evaluation is still pending on Kaggle.

Results: `FASTWEB_G3_RESULTS_2026-10-23.md`. Manifest:
`artifacts/cluster/g3-dev200-2545/experiment-manifest.json`.
Next useful work: audit pretrained exclusions and test the fixed learned fusion
on an independent excluded cohort before promotion; avoid further tuning on
this diagnostic panel. Follow the existing official submission, without a new
submission mutation.


## G3 submission requested and prepared — 23 October 2026

User explicitly prefers to test G3 on Kaggle now instead of further local
research. This supersedes the earlier local promotion gate for this
experimental submission. Prepared a separate private notebook
`mperni/casmi26-f0-g3-lightgbm-experiment`, retaining F0 control57552927.
Deployment averages the five saved LightGBM fold scores; no refit, no neural
model. Captures observable numeric main-channel evidence and protonated GL
scores, then replaces final ordering on the same40-candidate pool.

Technical checks only: exact feature parity on7,729 cached rows, fold0 prediction
parity with max error0.0; syntax and diff checks pass. Private upload package:
13 files,655,621 bytes, five model text files, five numeric preprocessing files,
inference code and manifests. Contains no spectra/validation labels/credentials.
Bundle and finalizer are ready. Transfer inventory:
`artifacts/kaggle/g3-lightgbm-v1/transfer-review.json`.

**Upload has NOT occurred and G3 has NOT been submitted.** Automatic approval
review rejected the dataset upload twice, including after payload inspection,
because it requires trusted explicit user consent to export these nonpublic
models to Kaggle. Do not bypass via embedding, another tool or indirect upload.
Ask consent specifically for this private13-file transfer and subsequent G3
submission. After consent, create the private dataset, push the prepared bundle,
record the actual returned notebook version and start
`scripts/finalize_fastweb_g3_submission.py --version VERSION` once. F0 state and
experiment results remain unchanged; current F0 API still PENDING.


## G3 private upload explicitly approved and running — 23 October 2026

User replied **SI** to the specific request to privately upload the13 G3 files
(655,621 bytes: five LightGBM models, five preprocessing files, inference code
and manifests) to Kaggle accountmperni and submit the new experiment. The same
payload hashes were checked before transfer. Prior auto-review export block is
resolved by this explicit consent; do not ask again for this authorized task.

Private dataset `mperni/casmi26-g3-fusion-research-models` **version1** is READY;
remote personal-dataset API confirms `is_private=True`, all12 data files present
(metadata is dataset configuration). CLI returned a JSON decode error after
creation; reconciled by read-only status/file listing, no duplicate upload.
Notebook `mperni/casmi26-f0-g3-lightgbm-experiment` **version1** successfully
pushed and RUNNING. It retains the F0 recipe/mounts, captures numeric evidence,
then applies the mean of five saved LightGBM fold scores to the same40-candidate
pool. This deployment ensemble has no measured official score yet.

Detached single-submit finalizer is active:
`scripts/finalize_fastweb_g3_submission.py --version 1`.
Live state/log/PID: `artifacts/kaggle/g3-lightgbm-v1/`.
It waits for completion, validates G3 receipt/model hash/CSV, submits once and
records the returned official ID. **Do not launch a duplicate finalizer or
manual submission.** It has not submitted while status is waiting_for_notebook.
No new local model experiment, refit, venv or allocation. User preference:
for these experiments prefer a Kaggle submission with essential technical
checks over lengthy further local validation. Keep scientific local/official
results distinct and F0 control57552927 intact.


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


## Conservative G3 tail experiment launched — 23 October 2026

User authorized “bho, falla”. New Kaggle notebook
`mperni/casmi26-f0-g3-conservative-tail` version1 pushed; detached finalizer
waits and will submit once after checks. Exact F0 top1 and top25 candidate set
are preserved; G3 only reorders positions2–25. No training or new model upload.
No official score yet. Do not duplicate submission/finalizer.
Details: [FASTWEB_G3_CONSERVATIVE_2026-10-23.md](FASTWEB_G3_CONSERVATIVE_2026-10-23.md).
Live state: `artifacts/kaggle/g3-conservative-v1/submission-state.json`.


## Conservative G3 official result — 23 October 2026

Authenticated Kaggle API confirms submission57563808 COMPLETE, public MRR@25
0.451. F0 control57552927 remains0.464; unrestricted G3 scored0.388.
Conservative tail ordering improves0.063 over unrestricted G3 but regresses
0.013 against F0. Preserve F0 as baseline; do not promote either G3 recipe.
The scored conservative recipe preserves F0 top1 and candidate set, so tail
ordering provides a net negative contribution on the public score. The
comparison with unrestricted G3 also changes pool membership (exact F0 top25
versus unrestricted fusion pool), so it does not isolate top1 protection alone.
No new training or submission launched during this check.
Snapshot: `artifacts/kaggle/g3-conservative-v1/official-results.json`.


## Stato competizione e piano H — 28 ottobre 2026

Leaderboard scaricato 14:15 UTC: noi **0.464, rank 959/4243**; primo 0.513; 17 team
≥0.48, 378 ≥0.47. Miglior notebook pubblico **0.477** (busyaprime m1): stessa
pipeline v4g + re-ranking neurale leader-safe (w_top 0.25, w_mid 0.75) + fragment
check sul solo leader. Il modello neurale (`sanpier/casmi-spectrum-model-v1`) è un
transformer da 12 MB con holdout casuale; la sua versione long perde 0.019 sul LB.
Public LB ≈125 molecole: 1 molecola rank 2→1 ≈ +0.004.
Esperimenti programmati: F0 fatto (0.464), G1 solo pilot, G3 respinto
(0.388 / 0.451), **G2 e G4 non eseguiti**. Nessun esperimento dal 23/10.
Fonti esterne confermate dall'host: ICEBERG PubChem atlas (pesi NIST'23,
predizioni precalcolate consentite in dataset privato), MIST, MS2DeepScore 2.0,
FIORA-OS, DreaMS SSL, release recenti delle librerie del train, relazioni
cross-test; NIST e SIRIUS vietati. Correzione massa elettrone solo sul test nascosto.
GPU: job 2545 (1 H100, condivisa con training `name-that-llm`), job 2658 (2 H100)
PENDING; tutte le 64 H100 del cluster allocate. Nessuna submission, upload,
allocazione o training avviati in questa sessione.
Piano: [EXPERIMENT_PLAN_2026-10-28.md](EXPERIMENT_PLAN_2026-10-28.md); coordinamento
Claude ⇄ Codex: [COLLAB_BOARD.md](COLLAB_BOARD.md). Evidenze locali:
`artifacts/public_notebook_audit_2026-10-28/`.


## 2026-10-28 16:11 — Codex J5/J5b atlas

Consegnati a Claude 16.995 spettri simulati / 5.665 identità esterne al train, 15 formule, zero overlap con la tabella canonica completa (274.195 identità). Downloader streaming e parser con manifest/esclusioni verificati; 36 test passati. Audit reale ha individuato e rimosso 3 identità non idempotenti. Report: [J5 atlas](J5_atlas_data_2026-10-28.md). Nessuna misura MRR o training Codex in questa fase.


## 2026-10-28 22:23 — Codex J5c completato

Scorer atlas diretto, replay sanpier/JM e audit coverage implementati. Sul diagnostic esposto al training, JM+atlas coda vs JM delta+0.00321 IC95[-0.00090,+0.00827] sulle55 truth presenti: non promuovere. Catalogo ranking completo15 formule pronto: 9.740 identità/29.220 spettri, recall74/142 vs55/142 del campione. Report: [J5c](J5c_atlas_ranking_2026-10-28.md). Nessun risultato H1 o LB misurato da questo esperimento.
