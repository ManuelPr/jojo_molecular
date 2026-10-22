# Decision log

## 2026-10-22 — Handoff su GitHub per allocazione Fastweb

Pubblicare codice/configurazioni/test/documentazione e sorgenti upstream con
attribuzione nel repository indicato dall'utente, preservando la licenza e il
commit iniziale remoto. Escludere dati, pesi, segreti e bundle generati.
Fornire un preflight che verifichi i kernel CUDA tramite forward/backward;
non basta la visibilita della GPU. Usare direttamente l'allocazione VS Code
esistente, senza avviare automaticamente altri job. Esplicitare che il nuovo
ranker finale e il generatore sono ancora proposte, non modelli pronti.

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

## PubChem selettivo: conservare e approfondire offline — 2026-10-15

Risultato ufficiale verificato **0,339** (57196384), **+0,001** rispetto al
controllo expanded+GLACIER **0,338**. Conservare come miglior artifact pubblico
misurato, senza considerarlo miglioramento robusto sulla distribuzione hidden.
Gli inserimenti fissi erano un test diagnostico; la direzione architetturale
resta una fusione calibrata dove i candidati esterni possano arrivare primi,
come previsto dal master plan. Prima misurare i colli di bottiglia di recall e
ranking su holdout e distinguere recuperi da regressioni. Non riabilitare il
join grezzo, già peggiorativo offline. Nessuna ulteriore submission autorizzata
implicitamente dal risultato.

## PubChem selettivo come test diagnostico — 2026-10-14

Nuova autorizzazione utente per un invio ufficiale. Proteggere library>=0,9
e la prima scelta del modello expanded+GLACIER. Aprire PubChem solo se la
massima probabilità del ranker base è <0,3; inserire fino a cinque identità
esterne agli slot 4/8/12/16/20. Replay appaiato: catalogo noto -0,002360
MRR, proxy struttura tolta dal catalogo +0,043579; nessuna top-1 cambiata.
Il tradeoff è dichiarato, non è una previsione del hidden. Notebook privato v1
COMPLETE; audit400 PASS. Invio ufficiale singolo **57196384** PENDING. Dettagli in
`SELECTIVE_PUBCHEM_SUBMISSION.md`.

## PG2 public result: next experiment needs class-2 coverage — 2026-10-14

Submission expanded train+COCONUT + GLACIER **57184698** raggiunge public
MRR@25 **0,338**, +0,040 sul controllo 0,298, senza errore, ma sotto 0,42.
Non attribuire il delta a GLACIER: sul placeholder400 era tutto protetto e
l'API public non mostra il percorso hidden. Non convertire l'OOF0,773666 in
una previsione hidden. Prossimo confronto offline: library-holdout con
acquisizioni diverse, poi recupero PubChem selettivo e ranking calibrato con
metriche separate per candidate recall e MRR; un proxy davvero fuori catalogo
serve prima di promuovere generazione de novo. Nessuna nuova submission o VM
a pagamento da questo checkpoint.

## PG1 full188: pruning e ranking esterno — 2026-10-14

Audit indipendente PASS, baseline RR188/188 riprodotti. Prune80 elimina la
truth per42/188; usare tutta la finestra di massa porta MRR0,542091 a0,690067,
delta paired CI95[0,102533;0,195222]. Finestra massima401 candidati sul campione.
È un candidato concreto per il prossimo confronto, non una previsione hidden.
PubChem aggiunto senza calibrazione peggiora il rango raw della truth per123/188
e MRR scende a0,386795. Non promuovere il join grezzo. Il proxy con catalogo
nascosto recupera118/188 tra i50 candidati PubChem selezionati. Separare questa
coverage dalla qualità del ranking e dalla vera generazione de novo.
Forward188 v2 COMPLETE: expanded OOF0,773666, guadagno forward CI95 positivo.
PubChem+forward0,533008; ranker ricalibrato OOF0,651308, sotto expanded+forward.
Preferire expanded+GLACIER per verifica library-holdout A e rehearsal400.
PubChem resta ricerca di coverage; non promuovere il join grezzo.
Non convertire queste metriche in una previsione del leaderboard.

## Cache forward non deve alterare le ablation — 2026-10-14

Il modello può calcolare una unione di candidati per efficienza, ma ciascuna
variante deve usare solo gli score che avrebbe richiesto da sola. Corretto il
budgetleak nello smoke, replay verificato. Rettifica comunicata all'utente.
Applicare maschera al full188; preservare entrambi i report per tracciabilità.

## PG1: separare recall e calibrazione — 2026-10-14

GLACIER originale funziona CPU/GPU, parità verificata. PubChem ha segnale di
coverage (12/16 strutture nel proxy catalogo nascosto) ma il join non calibrato
peggiora ranking standard sullo smoke. Misurare su188 e forward, senza presumere
che più candidati migliorino MRR. Cache CPU e forward GPU separati per evitare
quota GPU spesa nella preparazione. Nessun nuovo invio prima di gate misurato.

## Baseline hidden positiva — 2026-10-13

Public four-channel v2 **0,298**, submission 57143111 COMPLETE senza errori.
Promuovere v2 a riferimento diagnostico riproducibile per esperimenti offline.
I molteplici cambiamenti rispetto a E6 impediscono attribuzione causale unica:
confrontare pool e canali separatamente, misurare perdita al pruning top80.
Seconda E6 resta un crash, non uno zero; guard 127 dipendente dal placeholder
da correggere nella futura recovery. Nessun altro invio o job avviato.

## Rettifica diagnostica API — 2026-10-13

La seconda submission non prova un secondo zero: score vuoto e errore non
gestito nel rerun hidden. Verificare sempre `error_description` oltre a COMPLETE.
Non inferire dall'esito `57135939` che correggere C0 sia stato insufficiente:
l'effetto hidden di C1 non è stato misurato. Differenze E6/public restano valide.

## Invio controllo approvato — 2026-10-13

Autorizzazione esplicita ricevuta dall'utente. Submission **57143111** inviata
sulla v2 verificata; monitorare risultato hidden prima di scegliere esperimenti.
Non usare lo score della validazione come previsione del leaderboard.


## Gate diagnostico superato — 2026-10-13

Proporre l'invio esatto della public-control v2: run COMPLETE, gate locale PASS,
development MRR@25 0,5421, zero fallback e runtime 109,48 minuti. Non modificare
la ricetta tra controllo e submission. Nessun invio finché non arriva
l'approvazione esplicita prevista dal master plan §0.8 e dal piano concordato.
L'eventuale score positivo dimostrerebbe che questa pipeline funziona sul hidden,
senza isolare quale differenza abbia causato i due zero. Uno zero o errore
richiederebbe ispezione del rerun hidden prima di nuovi esperimenti.


## Controllo pubblico storico — 2026-10-13

Riprodurre il fork pubblico storico a quattro canali come riferimento,
con versioni/hashes degli asset attuali fissati, prima di una nuova submission.
Non promettere 0,339: il sorgente diretto ha restituito 403 e gli asset ranker
non coincidono necessariamente con quelli dello score storico. Il notebook
prvsiyan attuale include una composizione successiva e non è questo controllo.
Conservare ranking e cap 80; modificare soltanto packaging, fail-fast e writer
scorer-aware. Validation/pretrained overlap esplicitamente non certificato.
Rehearsal e validation offline su Kaggle CPU autorizzati dalla richiesta corrente;
nessun uso di VM a pagamento. Presentare evidenza terminale prima dell'invio.

## Audit 2026-10-13 — Causa hidden aperta; confronto a C1 fisso

E6 non è una riproduzione della pipeline pubblica a quattro canali. Non
attribuire confidenza alta alla coverage hidden senza dati osservabili.
Il secondo zero smentisce la sufficienza della correzione C0. Prima di C2,
confrontare retrieval diretto e ranking a C1 fisso, isolando reference,
formula anchor e pareggi di massa. Conservare E6 come controllo congelato;
non modificare l'inferenza promossa sulla base delle fixture sintetiche.
Report: `PUBLIC_PIPELINE_DIFFERENTIAL_AUDIT.md`. Nessuna nuova submission.

## ADR-028 - Recovery coverage-first con C1 e reference scaling

**Data:** 2026-10-12
**Stato:** accettata

L'audit domain-matched development misura C0 catalog recall 57,45% contro 100%
per C1. C1 porta Recall@1000 a 1,0 ma aumenta i competitor same-formula medi da
1,55 a 14,18 e riduce la mass-only MRR@25 da 0,4069 a 0,3801. La conversione
degli addotti non mostra un errore sistematico (mediana 1,65 ppm, p90 3,12 ppm).

La recovery procede in ordine: runner fail-fast; C1 con E6 congelato; ladder
reference 127→512→2.000→2.748; C2 COCONUT; C3 ChEBI/LIPID MAPS. Import e
benchmark lunghi vanno sulla VM, Kaggle resta per smoke e inferenza. Nessuna
seconda submission senza rehearsal offline e nuova approvazione.

Goal 5 v4 è terminato prima dell'interruzione, dopo 8 h 21 min 46,64 s di log.
Gli artifact sono archiviati, ma E8–E12 non sono promossi: i delta MRR C1 vs C0
non sono stabili e Hit@1 peggiora. Non avviare un sostituto Kaggle.

## ADR-001 - Tre protocolli, non un singolo holdout

**Data:** 2026-10-09  
**Stato:** accettata

Usare library holdout, molecule-disjoint e novelty holdout come protocolli separati. Un solo split same-identity sovrastima la generalizzazione e non distingue ranking da copertura del catalogo.

## ADR-002 - Leakage audit bloccante prima del fit

**Data:** 2026-10-09  
**Stato:** accettata

Il fit non parte se identita, contenuto spettrale, candidate roster, osservazioni del ranker o provenance delle feature violano il protocollo. I manifest canonici sono artifact di prima classe.

## ADR-003 - Nearest mass come controllo forte

**Data:** 2026-10-09  
**Stato:** accettata

Mantenere nearest mass in ogni studio. Nel run v4 supera retrieval union e ranker nel molecule-disjoint, quindi un modello complesso deve dimostrare un delta appaiato rispetto a questo controllo, non soltanto rispetto al caso casuale.

## ADR-004 - Non promuovere il ranker corrente

**Data:** 2026-10-09  
**Stato:** accettata

Il ranker migliora il library holdout, ma non il molecule-disjoint. Questo e coerente con overfitting al regime same-identity. Rimane una baseline e un test d'integrazione.

## ADR-005 - Fingerprint isomer-aware prima di modelli pesanti

**Data:** 2026-10-09  
**Stato:** accettata

Il prossimo esperimento e un spectrum-to-fingerprint baseline con hard negatives same-formula. Candidate Recall@25 e gia 1 nel catalogo bounded, mentre 13/32 errori del ranker hanno un competitor same-formula. DreaMS e ICEBERG/GLACIER restano milestone successive e richiedono evidenza incrementale.

## ADR-006 - Novelty come ramo esplicito

**Data:** 2026-10-09  
**Stato:** accettata

Il closed-world ranker ottiene necessariamente zero quando il target e assente dal catalogo. La novelty generation deve avere interfacce, metriche e budget propri e confluire nell'ensemble soltanto dopo filtri chimici e mass consistency.

## ADR-007 - Locale leggero, Kaggle per smoke, VM per scala

**Data:** 2026-10-09  
**Stato:** accettata

Lo sviluppo locale e limitato a codice e test CPU. Kaggle esegue smoke e validazioni bounded offline; il training completo si sposta su una VM grande solo dopo un risultato go/no-go positivo. Nessuna submission automatica.

## ADR-008 - Controlled e realistic sono benchmark diversi

**Data:** 2026-10-09  
**Stato:** accettata

Il catalogo controlled puo consultare e garantire il target e serve esclusivamente a misurare ranking condizionato. Il realistic deve derivare soltanto da informazioni disponibili in inferenza, conservare una trace di costruzione target-blind e fallire se rileva injection. I risultati dei due protocolli non possono essere aggregati o presentati come equivalenti.

Motivo: con 4.096 candidati controlled il Recall@25 e 1,0000 e la mediana same-formula e 0; con 49.620 candidati realistic il Recall@25 e 0,8750 e la mediana same-formula e 10,5.

## ADR-009 - Non promuovere il fingerprint encoder Goal 3

**Data:** 2026-10-09  
**Stato:** accettata

Il compact peak encoder e implementativamente valido ma non generalizza: mean sample Jaccard 0,0893 contro 0,2120 del KNN, early stopping all'epoca 1 in tutti i fold e peso fingerprint selezionato pari a zero in E2/E3. Nel realistic E4 ed E5 peggiorano E0 e gli intervalli non sostengono un vantaggio.

Non aumentare dimensione, profondita o attenzione. Prima servono learning curve su piu identita, rappresentazioni candidate migliori, gestione della sparsita dei bit e un obiettivo piu vicino al ranking same-formula.

## ADR-010 - Ritardare ICEBERG/GLACIER

**Data:** 2026-10-09  
**Stato:** accettata

ICEBERG/GLACIER non vengono integrati nella fase successiva immediata. Un forward scorer aggiungerebbe costo e confondenti mentre il segnale fingerprint di base e negativo e quattro target su 32 non raggiungono ancora la top-25 realistic. L'integrazione forward diventa ammissibile dopo un delta fingerprint positivo e ripetibile oppure dopo una chiara evidenza che la rappresentazione candidata, non lo spettro encoder, e il collo di bottiglia.

## ADR-011 - Canonicalizzazione bloccante del catalogo Goal 4

**Data:** 2026-10-10  
**Stato:** accettata

Applicare RDKit 2026.03.3 con canonicalizzazione tautomerica e richiedere che
l'InChIKey14 ricalcolato coincida con la chiave fornita prima di indicizzare una
struttura. Il rehearsal ha trovato 425 mismatch su 49.620 record unici. Usare lo
stesso catalogo filtrato in validation e inference; registrare i reject, senza
correggerli usando identità validation o test.

## ADR-012 - Promuovere analog propagation soltanto come reranker del pool fisso

**Data:** 2026-10-10  
**Stato:** accettata

Il segnale analogico deve operare sul top-100 nearest-mass senza aggiungere
candidati. Le reference sono identity-OOF in training e non contengono identità
o hash validation. La formula del target, i descrittori query-only e gli score
del leaderboard non sono feature. La promozione definitiva usa delta appaiato
rispetto a E0 e final holdout, non il controlled benchmark.

Il run canonico v4 soddisfa il gate: E6 ottiene delta MRR@25 +0,016369 sul
development (IC95% [+0,001938; +0,033939]), +0,026794 su all-validation
(IC95% [+0,003121; +0,061990]) e +0,037218 sul final, dove l'intervallo ampio
attraversa zero. E6 sostituisce E0 come baseline competitiva, mantenendo E0
come controllo obbligatorio.

## ADR-013 - Neutral loss e fragment compatibility isolati non sono baseline

**Data:** 2026-10-10  
**Stato:** accettata

E1 ed E2 vengono conservati come ablation, non come sistemi promossi. La
compatibilità formula/neutral loss è quasi costante fra isomeri; il fragment
matching diventa candidato-specifico soltanto tramite una reference o una
predizione forward. Un peso nullo scelto sul development è un risultato valido,
non un motivo per forzare la feature nel ranker.

## ADR-014 - Non scegliere LightGBM dal solo final piccolo

**Data:** 2026-10-10  
**Stato:** accettata

La selezione dei modelli avviene sulle 16 identità development. Un E5 forte per
caso sulle 16 identità final ma negativo/instabile sul development non viene
promosso. Il final rimane audit indipendente e non può essere usato per cambiare
feature o iperparametri nello stesso goal.

## ADR-015 - Espansione catalogo per tier, non PubChem full

**Data:** 2026-10-10  
**Stato:** accettata

Misurare nell'ordine current, LIPID MAPS, ChEBI, COCONUT e union Tier 1.
PubChem entra solo come artifact structure-only prefiltrato con provenance e
review dei termini. Ogni tier deve riportare coverage e ranking separatamente;
un catalogo più grande non è automaticamente migliore.

## ADR-016 - Escludere reference duplicate delle query anche in inferenza

**Data:** 2026-10-10  
**Stato:** accettata

Prima dello scoring nascosto, calcolare hash del contenuto normalizzato delle
query e rimuovere ogni reference coincidente, senza consultare identità test.
La v3 è stata correttamente bloccata dal controllo; la v4 ha escluso una
reference su 128 e ha completato. Disabilitare la guardia avrebbe introdotto
library lookup non dichiarato.

## ADR-017 - Non promuovere E5 dal final holdout

**Data:** 2026-10-10  
**Stato:** accettata

E5 raggiunge 0,494942 sul final di 16 query, ma nel development scende da
0,349104 a 0,263413 con delta -0,085691 e IC95% interamente negativo. La
selezione final-driven sarebbe leakage da model selection; E5 resta una
baseline diagnostica.

## ADR-018 - Goal 5 focalizzato sul retrieval analogico

**Data:** 2026-10-10  
**Stato:** accettata

Seguire Scenario C: scalare la library analogica, indicizzarla e provare DreaMS
congelato. Misurare Tier 1 coverage in parallelo. ICEBERG/GLACIER entra solo
dopo un probe economico sul residuo same-formula; nessun grande training viene
autorizzato dalla conclusione di Goal 4.

## ADR-019 - E6 congelato come controllo di regressione Goal 5

**Data:** 2026-10-10
**Stato:** accettata

Il commit `04a6a89ae7fc6c32d4a65f6f63450864f5a00abc`, gli hash dei dati,
il manifest, le metriche E0/E6 e il CSV v4 sono un contratto immutabile. Le
estensioni Goal 5 vivono in nuovi moduli e confrontano ogni challenger con E6 a
parità di stage. Nessun risultato Goal 4 viene ricalcolato retroattivamente.

## ADR-020 - Validation domain-matched in tre condizioni e holdout sigillato

**Data:** 2026-10-10
**Stato:** accettata

Usare `enveda-np-examples`/timsTOF come proxy di dominio, non come stima
imparziale del test. Separare A library-visible, B structure-known/spectra-hidden
e C structure-absent. Escludere fisicamente i 16 final Goal 4, gli hash delle
query e le identità sealed dalle reference development. Il sealed viene aperto
una sola volta dopo aver fissato E7-E12.

## ADR-021 - Indici esatti prima di ANN

**Data:** 2026-10-10
**Stato:** accettata

Per massa e formula usare array ordinati, posting list, `searchsorted`, mmap e
checksum. Per gli analoghi usare un prefilter esatto sulla massa neutra prima
dello scorer Goal 4 invariato. FAISS/HNSW non è giustificato per una query
monodimensionale e non può sostituire il fallback nearest-mass; sarà rivalutato
solo per un canale vettoriale che risulti un collo di bottiglia misurato.

## ADR-022 - DreaMS è environment-blocked, non model-rejected

**Data:** 2026-10-10
**Stato:** accettata

Non installare DreaMS direttamente nell'ambiente di scoring Python 3.13/RDKit
2026.03.3. L'upstream pinna Python 3.11 operativo, Torch 2.2.1, NumPy 1.25,
PyArrow 15 e RDKit 2023.9.6 e richiede un checkpoint da 1,24 GB. Il probe dovrà
girare in un wheelhouse Python 3.11 isolato ed esportare embedding verificati.
L'assenza del run non è evidenza negativa sulla qualità del modello.

## ADR-023 - Nessun prior di database senza evidenza inference-safe

**Data:** 2026-10-10
**Stato:** accettata

E11 resta non eseguito. La frequenza di una struttura nel train o la presenza
in una sorgente non diventa automaticamente un prior chimico generalizzabile;
può riflettere sampling della library e peggiorare novelty. Un prior entrerà
solo con provenance, definizione disponibile in inferenza e delta stabile su
development e sealed.

## ADR-024 - Kaggle per smoke e inferenza, VM per elaborazioni lunghe

**Data:** 2026-10-12
**Stato:** accettata

Lo sviluppo locale resta limitato a codice, compile check e unit test. Kaggle
viene usato per smoke test ridotti e inferenza offline compatibile con la
competizione, non per canonicalizzazione completa o benchmark di molte ore. I
rebuild del catalogo, la preparazione delle reference e gli esperimenti E7–E12
completi vanno spostati su una VM esterna con artifact persistenti. Nessuna VM a
pagamento viene avviata senza approvazione esplicita.

Motivo: Goal 5 v2 ha consumato circa 11 h 58 min quasi interamente nella
canonicalizzazione prima del limite Kaggle; v3 ha impiegato 2 h 50 min 55 s per
raggiungere la prima valutazione development. Il costo non è adatto al ciclo di
debug Kaggle.

## ADR-025 - Goal 5 congelato a checkpoint incompleto

**Data:** 2026-10-12
**Stato:** accettata

Non iniziare Goal 6 e non promuovere E7–E12 finché non esiste un artifact
terminale con metriche development e sealed. Il kernel v4 già attivo può
terminare, ma non va sostituito da un nuovo run Kaggle. Se supera 4 ore senza
artifact terminale, proporre la cancellazione; 8 ore è il limite operativo per
questo benchmark. L'eventuale cancellazione deve preservare log, versione e
artifact recuperabili.

## ADR-026 - Prima submission dalla versione Goal 4 E6 già completata

**Data:** 2026-10-12

**Stato:** accettata

Usare `mperni/casmi26-goal4-spectral-ranking`, versione 4, come prima
submission ufficiale. Non creare una nuova versione e non incorporare Goal 5:
la v4 è `COMPLETE`, offline, associata alla competizione e ha output/hash/runtime
già verificati. Il modello resta E6 con `analog_score`, peso 0,5 e reranking
same-formula dell'anchor mass.

La submission rimane bloccata fino ad approvazione esplicita. Dopo l'invio si
registra un solo punto di calibrazione; il public leaderboard non viene usato
per modificare E6 o scegliere iperparametri.

## ADR-027 - Public 0,000: coverage prima del ranking

**Data:** 2026-10-12

**Stato:** accettata

La submission E6 v4 autorizzata è `COMPLETE` con public MRR@25 visualizzato
0,000 e rank 3139/3140 allo snapshot. Il runner e il formato sono stati
accettati, ma E6 può solo riordinare strutture nel catalogo costruito dal train.
Il punto pubblico invalida quindi l'uso del benchmark locale closed-world come
proxy della pipeline hidden end-to-end.

La priorità tecnica successiva, quando il workflow Goal 5 verrà riaperto, è
dimostrare candidate coverage/novelty su un protocollo realmente open-world
prima di investire in ulteriore reranking. Non si conclude che il reranker E6
sia la causa dello zero: le truth hidden non sono disponibili. E6 resta
congelato, il singolo score non viene usato per tuning e nessuna seconda
submission viene autorizzata implicitamente.

## ADR-029 - C1 necessario ma insufficiente; nessuna terza submission

**Data:** 2026-10-13

**Stato:** accettata

La seconda submission `57135939` è stata eseguita su autorizzazione esplicita
con C1 e ranking E6 congelato. Il public MRR@25 resta 0,000. Il troncamento C0
è quindi un bug locale dimostrato, ma non la spiegazione sufficiente del
fallimento pubblico. Non usare il secondo zero per modificare E6 né effettuare
un terzo invio. Spostare il prossimo test informativo su VM: C2 COCONUT,
reference scaling e misure offline; Goal 6 resta escluso.
