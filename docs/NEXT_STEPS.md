# Next steps — Goal 5 checkpoint

## Priorita aggiornate Fastweb — 2026-10-22

Seguire `docs/FASTWEB_GPU_EXPERIMENT_PLAN.md`: ambiente H100 gia verificato
secondo il report remoto; prima dati ufficiali e asset versionati, quindi F0
porting/profiling della pipeline competitiva e G1 copertura proxy GLACIER + ICE.
G2 e il primo training selezionato: FPNet con esclusione delle identita e poi
una sola modifica controllata. G3 apprende la fusione sulle evidenze in cache.
Goal 3 legacy non e la priorita scientifica, ne una replica del nostro 0.440.
Nuovo riferimento pubblico verificato 0.464; vedere audit 22 ottobre.
Non modificare split congelati; non lanciare nuova allocazione o submission.

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

## Aggiornamento dopo risultato PubChem — 2026-10-15

**57196384 COMPLETE: public 0,339**, contro **0,338** del controllo;
verifica SDK 08:41 UTC, errore vuoto. Monitoraggio concluso.
Congelare entrambe le ricette. Prima di un altro invio, misurare offline sullo
stesso holdout: truth nella finestra di massa, dopo screening/top50, nei 25
finali e MRR condizionata alla presenza. Separare recuperi e regressioni.
Confrontare poi inserimento fisso e fusione calibrata con possibilità di rank 1
per PubChem, mantenendo protezione dei library match affidabili. Non promuovere
il join grezzo già peggiorativo; usare split separati per calibrazione e misura.
Il +0,001 pubblico è un segnale limitato, non prova di generalizzazione.

2026-10-14: nuova autorizzazione per una submission PubChem selettiva.
Kernel `mperni/casmi26-selective-pubchem-submission` v1 COMPLETE;
rehearsal400 e audit indipendente PASS. Invio ufficiale **57196384** PENDING.
Monitorare score ed errore del rerun hidden senza invii duplicati. Evidenza in
`SELECTIVE_PUBCHEM_SUBMISSION.md`.

Audit comparativo pubblico registrato in `PUBLIC_NOTEBOOK_GAP_2026-10-14.md`:
prima misurare offline il ramo PubChem selettivo con catalogo held-out; poi
ICEBERG dove GLACIER manca e completamento scorer-aware dei 25 slot, una
modifica alla volta. Non copiare l'intero ensemble dei notebook migliori senza
un confronto appaiato e validazione domain-matched.

2026-10-14 15:50:28 UTC: submission **57184698 COMPLETE**, public **0,338**,
error_description vuoto. Guadagno +0,040 sul controllo 0,298, ma sotto 0,42.
Il punteggio non identifica quali casi hidden sono classe 1/2/3 né dimostra
che il ramo GLACIER sia stato attivato. Prossima priorità sperimentale:
validazione identity/library-holdout con acquisizioni differenti; misurare
separatamente recall di recupero, Recall@25 e MRR per catalogo base e recupero
PubChem selettivo, proteggendo i match library affidabili. Per un proxy tipo 3,
escludere l'identità da tutti i cataloghi e valutare un generatore di analoghi
vincolato a massa/formula prima di promuoverlo. Nessun ulteriore invio ufficiale
autorizzato da questo risultato.

2026-10-14: una nuova submission expanded train+COCONUT + GLACIER è autorizzata
da "va bene! fallo". Completare il kernel autonomo, run400 offline, audit,
quindi inviare esattamente la versione verificata e monitorare score/error API.
Nessuna ulteriore approvazione da richiedere per questo invio già autorizzato.
Checkpoint dedicato `EXPANDED_GLACIER_SUBMISSION.md`.

Invio eseguito: **57184698**,kernel v1,2026-10-14 16:01:44Europe/Rome.
400-row audit PASS e ramo GLACIER CUDA testato indipendentemente (visibili tutti
protetti da library match). Stato PENDING,nessuno score ancora. Monitorare ID
esatto ed error_description completo; nessuna nuova submission autorizzata.

PG1 completato 2026-10-14: feature CPU188 COMPLETE e audit PASS, baseline0,542091,
expanded0,690067 (delta CI95 interamente positiva), PubChem0,386795.
Forward GPU188 v2 COMPLETE e audit PASS. Expanded+GLACIER OOF0,773666,
delta forward CI95[0,042792;0,123562]. PubChem+GLACIER0,533008, ricalibrato
39 feature0,651308: entrambi sotto expanded+GLACIER. Proxy catalogo nascosto
weighted-forward0,439629 contro ricalibrato0,420117. Nessun job PG1 ancora attivo.
Prossimo candidato: expanded train+COCONUT + GLACIER, verificare library-holdout A
con acquisizioni reference differenti e poi rehearsal offline400/runtime/formato.
Non inviare ufficialmente senza approvazione esplicita master plan0.8.

Richiesta obiettivo >0,42: ipotesi retrieval PubChem + ranker esteso + forward
GLACIER/ICEBERG, confronto incrementale pool/recall/ranking prima di invio.
Evidenze e limiti accesso in `NEXT_MODEL_EXPERIMENT.md`; risultati PG1 completati
in `PUBCHEM_GLACIER_EXPERIMENT.md`, senza nuove submission ufficiali.

## Priorità dopo score diagnostico 0,298 — 2026-10-13

Submission 57143111 public-control v2 COMPLETE, score 0,298, errore vuoto.
Controllo positivo ottenuto. Conservare ricetta/asset congelati; prossimi
esperimenti offline: pool C1 vs train+COCONUT a evidenza fissa, ablation dei
quattro canali, truth recall prima/dopo pruning top80. Valutare sulla stessa
development cohort mantenendo esplicito overlap pretrained non verificato.
Correggere guard post-filtro 127 nella futura recovery. Nessun nuovo invio.

Rettifica API 2026-10-13: `57135939` è un errore nel rerun hidden con score
assente. Le note storiche sul secondo zero sono superate. Controllare sempre
`error_description`; effetto di C1 sul leaderboard ancora non misurato.

Futura recovery: eliminare guard post-filtro 127 dipendente dal placeholder;
verificare reference pre-filtro 128 e after=before-excluded. Difetto riprodotto
con AST guard, ma traceback hidden non disponibile. Non modificare la v2
public-control attualmente sottoposta a valutazione.

## Controllo pubblico completato — 2026-10-13

Kernel `mperni/casmi26-public-baseline-control` v2 COMPLETE (CPU offline).
Development MRR@25 0,5421; Hit@1 44,15%; Recall@25 75%; mass-window truth 100%.
Zero fallback, runtime 109,48 minuti. Output scaricati, audit CSV PASS:
ID/ordine, identità valide/uniche, hash e metriche verificati. Utente ha
autorizzato: v2 inviata, submission **57143111**, COMPLETE con public 0,298
ed errore assente. Risultato registrato; nessun invio duplicato.
Il payload contiene solo development 188/876. Nessuna submission ufficiale
effettuata in questa fase. La v1 ha fallito prima dell'inferenza per wheel cp312.

## Priorità dopo audit differenziale 2026-10-13

Prima di C2, confrontare offline a C1 fisso mass-only/E6/direct library estesa
e baseline pubblica versionata. Misurare formula anchor, pareggi di massa,
recall prima/dopo ranking e scaling reference. La causa hidden non è provata;
non assumere coverage come spiegazione sufficiente dei due zero.
Dettagli in `PUBLIC_PIPELINE_DIFFERENTIAL_AUDIT.md`. Nessuna terza submission
o VM a pagamento autorizzata da questo audit; mantenere il workflow già deciso.

## Sequenza recovery aggiornata

1. Conservare Goal 5 v4 `COMPLETE`, log e artifact già recuperati; non
   promuovere E8–E12 e non rilanciare il notebook.
2. Rendere fail-fast la futura pipeline candidata eliminando
   fallback di esperimento/feature/peso e aggiungendo fingerprint runtime.
3. Sulla VM, riusare C1 e misurare E6 congelato con la ladder reference
   127/512/2.000/2.748. Non aprire il sealed fino al congelamento.
4. Costruire C2 COCONUT e C3 ChEBI/LIPID MAPS solo dopo il risultato C1;
   misurare separatamente catalog recall, Candidate Recall e ranking.
5. Fare un unico rehearsal Kaggle di sola inferenza con artifact precomputati.
6. Fermarsi prima della seconda submission e chiedere nuova approvazione.

Dettagli in [RECOVERY_EXPERIMENT_PLAN.md](RECOVERY_EXPERIMENT_PLAN.md). Goal 6
resta vietato.

Ultimo aggiornamento: 2026-10-12

## Stato

Goal 5 è incompleto ma salvato in un checkpoint riproducibile. Goal 6 non deve
iniziare. Non avviare nuovi esperimenti o kernel Kaggle finché il workflow non è
stato riorganizzato.

## Prossima operazione breve consentita

Il kernel Goal 5 v4 è terminale e gli artifact sono già archiviati. Non
rilanciarlo e non effettuare submission. La prossima modifica breve è rendere
fail-fast il runner futuro; gli esperimenti lunghi riprendono soltanto dopo la
predisposizione della VM.

## Lavoro Goal 5 ancora necessario

1. Rendere fail-fast il runner futuro e aggiungere fingerprint di input/output.
2. Isolare l'effetto reference con ladder 127/512/2.000/2.748 su VM.
3. Migliorare il reranking C1 mirando a Hit@1 senza modificare E6 tramite LB.
4. Eseguire il probe DreaMS frozen soltanto in un ambiente Python 3.11 isolato,
   dopo aver preparato wheelhouse e checkpoint con hash.
5. Valutare C2 (COCONUT) e poi C3 (ChEBI/LIPID MAPS); nessun
   database esterno è stato ancora importato.
6. Preparare un rehearsal Kaggle di sola inferenza e, solo dopo risultati
   completi, formulare la decisione sul Goal successivo.

## Workflow da predisporre prima di riprendere

### Locale

Codice, unit test, compile check e validazione degli artifact su subset piccoli.
Nessun preprocessing completo.

### Kaggle

Solo smoke bounded e inferenza offline. Target operativo: smoke entro 15–30
minuti; l'inferenza Goal 4 osservata richiede circa 25 minuti, circa 36,5 minuti
incluso il benchmark di selezione. Evitare rebuild e benchmark multi-ora.

### VM esterna

Per un run Goal 5 completo usare inizialmente CPU, non GPU: 16–32 vCPU, 32–64
GB RAM e almeno 20 GB di disco di lavoro, con cache/artifact persistenti. Stima
di budget: 4–8 ore se C1 e feature riutilizzabili sono già presenti; 8–12 ore
se è necessario ricostruire la canonicalizzazione completa. Sono budget di
planning, da verificare con uno smoke e checkpoint intermedi, non promesse.

Nessuna VM a pagamento può essere avviata senza approvazione esplicita.

## Criterio di ripresa

Riprendere gli esperimenti solo dopo aver definito:

- immagine/lockfile della VM;
- upload e checksum di C1 e dei manifest di split;
- checkpoint per stage e resume;
- logging periodico di runtime/RSS;
- stop-rule e costo massimo;
- trasferimento finale degli artifact alla pipeline Kaggle di inferenza.

## Calibrazione E6 completata

La versione Kaggle Goal 4 v4 è stata inviata una sola volta dopo approvazione:
submission `57109254`, stato `COMPLETE`, public MRR@25 visualizzato 0,000 e
rank 3139/3140 allo snapshot del 2026-10-12. E6 resta congelato e non va
modificato in risposta al singolo public score.

Prima di proporre una seconda submission occorre produrre evidenza offline che
il candidate generator recuperi strutture non presenti nel catalogo train-only.
Non usare il leaderboard per distinguere ipotesi di coverage, ranking o
novelty. L'eventuale nuovo invio richiede una nuova approvazione esplicita.

## Aggiornamento dopo la seconda submission

La recovery C1 + E6 `57135939` è `COMPLETE` con public 0,000. Non ripetere C1
e non fare una terza submission. Prossime attività, in ordine:

1. predisporre la VM esterna con checkpoint, checksum e budget;
2. costruire C2 = C1 + COCONUT e misurare coverage/ranking offline;
3. eseguire la ladder reference 127/512/2.000/2.748 con E6 congelato;
4. riesaminare il percorso hidden-only solo tramite log e test consentiti;
5. aprire un nuovo gate prima di qualsiasi ulteriore submission.

Goal 6 resta non iniziato. Kaggle rimane limitato a smoke e inferenza.
