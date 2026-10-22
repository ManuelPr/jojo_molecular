# Registro esperimenti

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

## Esito ufficiale PubChem selettivo — 2026-10-15

Submission **57196384**, kernel `mperni/casmi26-selective-pubchem-submission`
v1: SDK 08:41:00 UTC conferma `COMPLETE`, public **0,339**, private assente,
`error_description` vuoto. Controllo **57184698 = 0,338**; differenza fra
score pubblicati **+0,001**. Fonte: `artifacts/selective_pubchem/official_submission_status.json`.
Nessuna misura hidden per molecola o per classe: impossibile ricostruire
quanti recuperi/regressioni abbiano prodotto il saldo. Top-1 congelata per
costruzione; candidati esterni limitati agli slot 4/8/12/16/20. Il risultato
non dimostra che PubChem sia esaurito né giustifica tuning sul leaderboard.
Conservare variante e controllo, approfondire recall e fusione offline.

## Selective PubChem replay e kernel — 2026-10-14

Cache PG1 complete e checksum validati. Replay188 con ranking expanded+GLACIER
controllo 0,773666; gate library<0,9 e maxprob<0,3, inserimento PubChem
slot4/8/12/16/20: MRR 0,771306, 58 liste cambiate, zero top-1. Proxy
catalogo escluso: 0 -> 0,043579, 87 liste cambiate, zero top-1.
11 test mirati PASS. Kernel privato
`mperni/casmi26-selective-pubchem-submission` v1 COMPLETE in4092,94s;
rehearsal400 e audit chimico indipendente PASS. Invio ufficiale **57196384**
PENDING, score assente. Vedere `SELECTIVE_PUBCHEM_SUBMISSION.md`.

## Esito ufficiale expanded+GLACIER — 2026-10-14

SDK ufficiale alle 15:50:28 UTC: **57184698 COMPLETE**, public MRR@25
**0,338**, private vuoto, error_description vuoto. Controllo **57143111 =
0,298**; delta public **+0,040**. Risultato inferiore a obiettivo 0,42 e alla
stima informale 0,35–0,38. L'OOF development 0,773666 sovrastima il public
hidden in valore assoluto; cause specifiche non identificabili dal solo score.
Placeholder400 protetto da library in rehearsal, ma nessuna misura di attivazione
GLACIER hidden. Stato completo in `EXPANDED_GLACIER_SUBMISSION.md`.

## Submission expanded+GLACIER inviata — 2026-10-14

**57184698**,kernel v1,scriptVersionId358339073,16:01:44Europe/Rome.
Rehearsal400 COMPLETE in3940,85s,0 fallback. Audit ID/writer/hash400/400 e
9229 SMILES normalizzati PASS. Visibili tutti protetti da library>=.9;
probe del ramoGPU identico con gli stessi dataset PASS,2 predizioni,no errori.
Fonte/configurazione invariati. APIreceipt PENDING,score assente,errore vuoto;
4 slot oggi residui. Monitorare questo ref, non inviare duplicati.

## Expanded+GLACIER submission v1 avviato — 2026-10-14

Autorizzazione esplicita "va bene! fallo" per inferenza400/audit/invio ufficiale.
Writer parità188/188 PASS,9 unit test PASS. Kernel autonomo hidden-safe v1
`mperni/casmi26-expanded-glacier-submission`, GPU T4, internetoff, nessun parent
di cache e nessun PubChem. Avviato14:45Europe/Rome, hash nel report dedicato.
Attendere COMPLETE, scaricare output filtrati, audit, poi inviare la stessa v1
come già autorizzato. Nessuna submission ufficiale ancora inviata in questo step.

## PG1 full188 completato — 2026-10-14

GPU forward v2 COMPLETE, runtime1586,10s,159 query supportate,28653 predizioni,
zero errori. Audit PASS, parità baseline188/188. Expanded+GLACIER OOF0,773666,
delta vs expanded+0,083600 CI95[0,042792;0,123562]. PubChem+forward0,533008,
proxy catalogo nascosto0,439629. Calibrazione OOF fissa39 feature:0,651308 e
0,420117; ablation senza forward0,599697 e0,380366. Hash/cohort/fold/metric
audit PASS. Migliore candidato standard: expanded train+COCONUT + GLACIER.
Library-holdout A e inferenza400 necessari prima di promozione; nessun nuovo
invio ufficiale e nessuna previsione public>0,42. Report completo PG1.

## PG1 feature188 COMPLETE — 2026-10-14

Kernel features-full v1, runtime3806,35s. Audit PASS, baseline188/188 identica
al controllo congelato. MRR baseline80/expanded/PubChem/proxy catalogo nascosto:
0,542091 /0,690067 /0,386795 /0,352583. Prune80 perde42 truth; delta expanded
+0,147976 CI95[0,102533;0,195222]. Recall candidati proxy118/188.
Cache `features_full_v1`, hash e metriche nel report PG1. Forward GPU v2
avviato sul cache fissato:159 query supportate,11772 grafi,424 condizioni.
Budget40 locale già corretto; nessuna nuova submission ufficiale.

## PG1 forward16 e rettifica budget — 2026-10-14

GPU COMPLETE, 2474 predizioni/15 molecole supportate, runtime233,06s.
Bug nel confronto: cache condiviso forniva score oltre i primi40 indipendenti
della variante. Applicata maschera per variante, replay senza nuovo modello.
Numeri precedenti PubChem0,7417/proxy0,4809 superati: corretti OOF0,60914 e
0,47569. Expanded0,83724; baseline80 invariata0,6875. Audit PASS e regressione
budget testata. Artifact `forward_v1_masked`; full188 featureCPU RUNNING.

## PG1 PubChem + GLACIER — checkpoint 2026-10-14

Probe CPU v3 COMPLETE; GPU v4 COMPLETE e parità raw CPU/GPU verificata su due
strutture. Runtime isolato Python3.12/torch2.6/RDKit2025.03.6, scorer2026.03.3.
Cache16 COMPLETE, runtime1686,56s, baseline16/16 RR uguali al controllo.
Mrr baseline/no-cap/PubChem 0,6875/0,8177/0,4588; PubChem recupera12/16 nel
proxy con catalogo base nascosto (Mrr0,4033). Non usare questi16 per dichiarare
guadagno definitivo. Forward16 GPU e feature188 CPU avviati in job distinti,
parametri invariati; nessun sealed né submission. Report `PUBCHEM_GLACIER_EXPERIMENT.md`.

## Risultato submission diagnostica — 2026-10-13

**57143111 / public-control v2: COMPLETE, public MRR@25 0.298, error vuoto.**
Osservato via SDK ufficiale alle 16:30:44 Europe/Rome / 14:30:44 UTC; inviata
12:08:58 UTC. Circa 142 minuti fra invio e osservazione del completamento,
non una misura isolata del runtime hidden. Dettagli API salvati in
`artifacts/public_baseline/kaggle_v2/official_submissions_detail.json`.
Direction check positivo: pipeline multicanale esegue e predice sul hidden.
Non attribuire il successo a un singolo canale/catalogo; non confondere la
validation 0,5421 con una stima garantita del public. Nessun nuovo invio/job.

## Guard recovery dipendente dal placeholder — 2026-10-13

Report rehearsal recovery: reference_count_before_query_filter 128, un hash
duplicato test escluso, reference_spectra 127. Il kernel richiede sempre 127
dopo il filtro. AST del guard eseguito con report simulati: 127 PASS; 128
RuntimeError "Frozen E6 reference library drifted: expected=127, actual=128".
Bug hidden-sensitive concreto; attribuzione al crash 57135939 ancora ipotesi
per assenza traceback. Nessuna modifica a kernel inviati o nuovo invio.
Diagnostica: `artifacts/public_baseline/kaggle_v2/recovery_guard_diagnostic.json`.

## Rettifica lettura API — 2026-10-13

La lettura delle colonne score/status del CLI omette `error_description`.
SDK ufficiale: `57135939` COMPLETE con score vuoto e messaggio di errore non
gestito nel rerun hidden, quindi non un secondo MRR 0,000. `57109254` invece
ha score 0.000 ed errore vuoto. Precedenti annotazioni sul secondo zero sono
superate. Il messaggio generico non fornisce traceback né causa specifica.

## Submission diagnostica autorizzata — 2026-10-13

Utente: "autorizzo". Inviata esattamente la public-control v2 via code submission
con output `submission.csv`, ID **57143111**, timestamp 12:08:58 UTC.
Accettata, stato iniziale PENDING, score ancora assente. Tre submission
residue oggi riportate dal CLI. Nessun nuovo kernel/versione o modifica.


## Public four-channel control — risultato 2026-10-13

Kernel privato v2 COMPLETE, CPU offline, asset fissati e sorgente pull identica
dopo normalizzazione newline. Development 188/876: MRR@25 0,5420906074,
Hit@1 83/188 (44,15%), Recall@25 141/188 (75%), truth mass-window 188/188.
Mask 191 alias raw, reference visibili 2.498.313. Le 47 miss sono successive
al mass retrieval; pruning top80 e ranking non isolati. Overlap pretrained
non verificato: nessuna previsione di score hidden.
Rehearsal 400/1213, pool 712.199, reference 2.539.608, 2 FPNet, 8 GBM,
zero fallback. Runtime completo 6568,87s. Audit locale PASS: ID, ordine,
validità/unicità scorer, hash CSV e ricalcolo metriche. Quattro righe deduplicate.
14 test passati. Artifact: `artifacts/public_baseline/kaggle_v2/`.
Nessuna submission ufficiale; v2 pronta per approvazione finale concordata.


## Public four-channel control — preparazione 2026-10-13

Vendored fork storico shiferaxa commit c75b3fe0, Apache-2.0 con NOTICE;
ranking-loop AST identico. COCONUT v2, FPNet v1, ranker-features v6 verificati
tramite checksum. Builder e wrapper offline aggiunti, writer senza padding.
Development fisso 188 identità/876 spettri; sealed non incluso nel payload.
Kaggle v1 ERROR dopo 10,7 s per wheel cp312; v2 RUNNING con cp313, CPU,
timeout 10.800 s. Test nuovi 4 passed; compileall/diff-check passati.
Nessuna accuracy ancora misurata e nessuna submission ufficiale.

## Audit differenziale delle submission — 2026-10-13

Eseguito `scripts/audit_submission_ranking_limits.py` sui rehearsal salvati:
400 liste e 282 prime scelte SMILES cambiano da C0 a C1; recovery 127 reference,
5 analoghi/query; errore ppm candidato 100 mediano 13,98 e p90 64,87.
Fixture wrong-anchor: rank massa 30/evidenza 1 resta 30; fixture equal-mass:
rank massa 100/evidenza 1 diventa 67 con peso 0,5. Nessuna accuracy hidden
misurata. Output `artifacts/zero_score_recovery/ranking_limits.json`.
Confrontate sorgenti pubbliche shiferaxa e gnshx; score solo autodichiarati.
Test ranking/recovery/metrica: 12 passed in 19,70 s. Nessun job o invio.

## EXP-018 - Zero-score forensics e coverage C0/C1

**Data:** 2026-10-12

**Esecuzione:** locale CPU; nessun training, kernel o submission

**Artifact:** `artifacts/zero_score_recovery/forensics.json`

L'audit usa soltanto le 188 identità development domain-matched; il sealed non
è stato aperto. C0 (49.195 strutture) ottiene catalog recall 0,5745,
Recall@25/100/1000 0,5691/0,5745/0,5745, mass-only MRR@25 0,4069 e conditional
MRR 0,7082. C1 (271.439) ottiene catalog recall 1,0,
Recall@25/100/1000 0,8989/0,9947/1,0 e mass-only MRR/conditional MRR 0,3801.

C1 copre 80 truth aggiuntive ma aumenta i competitor same-formula medi da 1,55
a 14,18. Sui 876 spettri non vi sono addotti unsupported; errore massa neutra
mediano 1,65 ppm e p90 3,12 ppm. Il rehearsal contiene 400 query, 25 candidati
unici ciascuna e 395 ranking distinti: nessun fallback globale osservato.

**Decisione:** coverage C0/selection bias è la causa primaria più probabile;
prima di C2/C3 misurare C1 con E6 congelato e reference scaling.

**Job preesistente:** Goal 5 v4 è poi terminato `COMPLETE`. Log effettivo
30.106,64 s (8 h 21 min 46,64 s). Artifact scaricati una volta sotto
`artifacts/goal5_kaggle_v4/`; nessun relaunch o submission.

E8/C1 vs E7/C0: development A +0,0403 MRR (IC95%
[-0,0350; 0,0979]), development B −0,0025; sealed A +0,0065, sealed B −0,0187.
Hit@1 peggiora in tutte le celle, mentre Recall@25/100 e Hit@5/10 aumentano.
E9/E10/E12 non migliorano la MRR di E8. **Decisione:** non promuovere E8–E12;
isolare reference scaling e migliorare ranking prima di una seconda submission.

Salvo EXP-017, i risultati qui riportati sono locali o prodotti da kernel Kaggle
privati. EXP-017 registra l'unica submission ufficiale e il relativo punto di
calibrazione pubblico.

## EXP-000 — Audit del contratto dati

**Data:** 2026-10-09  
**Obiettivo:** verificare schema, dimensioni e preprocessing sui file ufficiali.

Dataset osservato:

- `train.parquet`: 2.539.608 righe, 21 row group, circa 2,89 GB, 18 colonne.
- `test.parquet`: 1.213 righe, 400 `molecule_id`, circa 4,62 MB, 12 colonne.
- `sample_submission.csv`: 400 righe.

Controllo preprocessing:

| Split | Righe elaborate | Record invalidi | Picchi medi mantenuti |
|---|---:|---:|---:|
| train, campione | 5.000 | 0 | 75,585 |
| test, completo | 1.213 | 0 | 72,6645 |

**Esito:** schema e preprocessing compatibili con i dati reali. Il reader rimane streaming per evitare di materializzare il train completo in RAM.

## EXP-001 — Test della baseline sintetica e sui contratti reali

**Data:** 2026-10-09  
**Comando:** `uv run pytest -q --cov=casmi26 --cov-report=term-missing`

Risultati:

- 28 test passati.
- Coverage totale: 84% su 735 statement.
- Integrazione sintetica completa: preprocessing → retrieval → ranker → writer/validator submission.
- Contract test read-only sui Parquet reali superato.

**Esito:** tutti i contratti della prima baseline sono verificati. La CLI non è ancora coperta direttamente; le funzioni sottostanti lo sono.

## EXP-002 — Rehearsal Kaggle versione 1

**Data:** 2026-10-09  
**Kernel:** `mperni/casmi26-baseline-smoke`, versione 1  
**Esito:** errore di bootstrap prima del training.

Causa:

- il glob degli asset assumeva un nome mount specifico;
- il log ha mostrato che il runtime Kaggle usa Python 3.13, incompatibile con il wheel RDKit `cp311` preparato inizialmente.

Correzione:

- ricerca ricorsiva degli asset sotto `/kaggle/input`;
- selezione del wheel tramite tag dell'interprete corrente;
- wheel RDKit 2026.3.3 `cp313-manylinux_2_28_x86_64`;
- range Python del progetto esteso e verificato a `>=3.11,<3.14`.

## EXP-003 — Mini-training Kaggle end-to-end

**Data:** 2026-10-09  
**Kernel:** `mperni/casmi26-baseline-smoke`, versione 2, COMPLETE  
**Ambiente:** Python 3.13, internet disabilitato, machine shape richiesta Nvidia T4  
**Codice:** wheel `casmi26-baseline==0.1.0` installato offline  
**Chimica:** RDKit 2026.03.3 installato offline e verificato a runtime

Configurazione:

| Parametro | Valore |
|---|---:|
| Seed | 2026 |
| Molecole libreria | 128 |
| Righe train massime scansionabili | 300.000 |
| Validation fraction | 0,25 |
| Candidate cap | 25 |
| Tolleranza massa | 20 ppm |
| Tolleranza picchi | 0,02 Da |
| Picchi massimi | 256 |

Training:

| Metrica | Valore |
|---|---:|
| Query training | 93 |
| Esempi positivi | 93 |
| Esempi negativi | 2.232 |
| Righe ranker | 2.325 |
| Query validazione | 32 |

Validazione interna:

| Modello | MRR@25 | Hit@1 | Hit@5 | Hit@10 | Recall@25 |
|---|---:|---:|---:|---:|---:|
| Retrieval | 0,96875 | 0,96875 | 0,96875 | 0,96875 | 0,96875 |
| Ranker supervisionato | 0,96875 | 0,96875 | 0,96875 | 0,96875 | 0,96875 |

Artifact e runtime:

- pipeline end-to-end: 77,595 s, esclusi bootstrap pip e rendering finale Kaggle;
- `ranker.joblib` prodotto;
- `submission.csv`: 400 righe, 400 molecole, minimo/massimo 25 candidati, validazione `valid=true`;
- validazione locale indipendente contro `data/sample_submission.csv`: superata;
- hash SHA-256 del primo MiB train: `8354c678f84604fae3af122326da8fdd968adb70bb395d1952cab8c12370c8ba`;
- hash SHA-256 del primo MiB test: `c15edff585b814b6b7df0208ec1f3779c2741dfbe388a9c0e1887cb43846edd4`.

Interpretazione critica:

- Il run prova l'operatività tecnica completa, non la capacità di generalizzare a molecole non viste.
- Reference e query sono acquisizioni diverse delle stesse identità: il protocollo favorisce fortemente il retrieval diretto.
- Il ranker non aggiunge valore misurabile rispetto al retrieval in questo esperimento; la parità va trattata come risultato negativo/inconclusivo, non come successo modellistico.
- Il prossimo esperimento decisionale deve usare split molecule-disjoint e structure-disjoint, candidate recall separata dal ranking e intervalli di confidenza per molecola.

**Decisione:** mantenere questa implementazione come baseline riproducibile e harness di integrazione. Non usare il suo MRR per scegliere l'architettura finale.

## EXP-004 - Audit indipendente e protocolli leakage-free

**Data:** 2026-10-09  
**Obiettivo:** sostituire lo smoke same-identity con protocolli auditabili e metriche che separano candidate coverage e ranking.

Implementato:

- library holdout con acquisizioni distinte e deduplica per contenuto;
- molecule-disjoint con target nel catalogo ma identita assente da train/reference;
- novelty holdout con target assente anche dal catalogo;
- manifest JSON deterministici con hash;
- audit fail-fast su identity, spectrum content, candidate contamination, ranker observations e feature provenance;
- Recall@25/100/1000/pool, MRR/Hit, conditional/oracle MRR, breakdown e bootstrap appaiato.

Audit della baseline precedente:

- il vecchio holdout misura soltanto library lookup;
- spectrum ID distinti non escludevano contenuto duplicato;
- il fingerprint del primo MiB non identificava integralmente il dataset;
- l'InChIKey14 dichiarato non era ricontrollato contro lo SMILES;
- nessuna feature corrente deriva direttamente dal target e il fit non includeva observation ID di validation.

**Esito:** contratti e test avversariali integrati; l'esecuzione viene bloccata in caso di leakage.

## EXP-005 - Correzione addotti multimerici

**Data:** 2026-10-09  
**Confronto:** Kaggle validation v2 contro v3, stessa membership degli split e catalogo da 128 strutture.

Problema: mancavano le trasformazioni di massa per `[2M+H]+`, `[2M+Na]+` e `[2M-H]-`. Di conseguenza, la massa neutra era errata per una parte consistente del cohort.

Effetto della correzione:

| Metrica molecule-disjoint | Prima | Dopo |
|---|---:|---:|
| Spettri train con massa neutra coperta | 61/96 | 96/96 |
| Nearest-mass Recall@25 | 0,6563 | 1,0000 |
| Nearest-mass MRR@25 | 0,6563 | 1,0000 |
| Retrieval union MRR@25 | 0,5599 | 0,9089 |
| Ranker MRR@25 | 0,4871 | 0,9844 |

**Interpretazione:** correzione di validita della pipeline, non avanzamento modellistico. I valori assoluti con catalogo da 128 strutture sono troppo ottimistici e sono sostituiti da EXP-006.

## EXP-006 - Validazione Kaggle v4 con catalogo esteso

**Data:** 2026-10-09  
**Kernel:** `mperni/casmi26-leakage-free-validation`, versione 4, COMPLETE  
**Ambiente:** Python 3.13, CPU, internet disabilitato, RDKit 2026.03.3  
**Submission:** nessuna

Configurazione:

| Parametro | Valore |
|---|---:|
| Seed | 2026 |
| Identita / spettri | 128 / 384 |
| Catalogo strutturale | 4.096 |
| Candidate pool | 1.000 |
| Bootstrap | 500 |
| Runtime pipeline | 50,973 s |

Risultati all-validation:

| Protocollo | Query | Nearest mass MRR@25 | Retrieval union MRR@25 | Ranker MRR@25 | Ranker Recall@25 |
|---|---:|---:|---:|---:|---:|
| Library holdout | 128 | 0,7363 | 0,9560 | 0,9961 | 1,0000 |
| Molecule-disjoint | 32 | 0,7467 | 0,6659 | 0,5987 | 1,0000 |
| Novelty holdout | 32 | 0,0000 | 0,0000 | 0,0000 | 0,0000 |

Confronti appaiati principali:

- library, retrieval union - mass: +0,2197, IC95% [+0,1645; +0,2718];
- library, ranker - union: +0,0401, IC95% [+0,0130; +0,0742];
- molecule-disjoint, union - mass: -0,0807, IC95% [-0,1536; -0,0156];
- molecule-disjoint, ranker - union: -0,0672, IC95% [-0,1558; +0,0141].

Il ranker molecule-disjoint produce 13/32 errori proxy same-formula. Source e instrument sono unicamente `enveda-180` e `timsTOF`, quindi i breakdown cross-domain non sono ancora informativi.

Test finali locali: 78 passed, coverage 87% su 1.781 statement.

**Decisione:** non promuovere il ranker corrente. Il prossimo esperimento e spectrum-to-fingerprint con hard negatives same-formula e ranking isomer-aware. Conservare nearest mass come baseline primaria e usare il final molecule-disjoint congelato per il go/no-go.

## Strategia multi-agent

Tre agenti indipendenti hanno lavorato in parallelo su split, leakage audit e diagnostiche retrieval, con ownership di file disgiunti; l'agente principale ha definito i contratti, integrato la pipeline ed eseguito test e Kaggle run. Tempo di goal misurato al checkpoint finale: 2.134 s; consumo complessivo: 428.628 token, di cui circa 340.704 successivi al primo checkpoint disponibile. La qualita e misurata da 78 test passati, coverage 87%, tre audit completi e un run Kaggle riproducibile. Il costo elevato in token e dovuto soprattutto a sviluppo parallelo, integrazione e analisi degli artifact; per le milestone successive conviene delegare solo moduli con interfacce gia stabilizzate.

## EXP-007 - Goal 3 preflight T4

**Data:** 2026-10-09  
**Kernel:** `mperni/casmi26-goal3-fingerprint-ranking`, versione 1, COMPLETE  
**Ambiente:** Tesla T4, Python 3.13, PyTorch 2.11 CUDA 12.8, LightGBM 4.6, RDKit 2026.03.3, offline  
**Submission:** nessuna

La v1 ha eseguito l'intera pipeline E0-E6 e ha prodotto i primi artifact quantitativi. Ha confermato che il modello compatto, LightGBM LambdaRank e il mining same-formula erano operativi. Ha anche evidenziato tre dati mancanti nel contratto: resource accounting uniforme per esperimento, candidate-prior audit e tiny-overfit eseguito nel runtime PyTorch. Questi elementi sono stati aggiunti senza cambiare split, modelli o scoring e verificati in EXP-008.

## EXP-008 - Goal 3 autorevole: fingerprint e ranking isomer-aware

**Data:** 2026-10-09  
**Kernel:** `mperni/casmi26-goal3-fingerprint-ranking`, versione 2, COMPLETE  
**Manifest:** `138055fca36fb37bd29bf27e970a6f8ee853bdd955546a17cb815cf49f1390d0`  
**Artifact:** `artifacts/goal3_kaggle_v2/goal3/goal3_results.json`  
**Submission:** nessuna

Configurazione:

| Parametro | Valore |
|---|---:|
| Righe scansionate | 300.000 |
| Strutture target-blind | 49.620 |
| Identita / spettri congelati | 128 / 384 |
| Candidate pool | 1.000 |
| Fingerprint | Morgan radius 2, 512 bit |
| OOF | 3 fold identity-disjoint |
| Epoch budget / batch | 12 / 16 |
| Hard negative per query | 64 |
| Bootstrap | 500 |

Audit benchmark:

| Protocollo | Catalogo | Target consultati | Injection validation | Recall@25 | Recall@100/1000 | Mediana same-formula pool |
|---|---:|---:|---:|---:|---:|---:|
| Controlled | 4.096 | 128 | 32 | 1,0000 | 1,0000 | 0,0 |
| Realistic | 49.620 | 0 | 0 | 0,8750 | 1,0000 | 10,5 |

Realistic all-validation:

| Esperimento | MRR@25 | Hit@1 | Delta MRR vs E0 | IC95% |
|---|---:|---:|---:|---:|
| E0 nearest-mass | 0,3750 | 0,2813 | - | - |
| E1 ranker originale | 0,2029 | 0,1250 | -0,1721 | [-0,3028; -0,0799] |
| E2 mass + fingerprint | 0,3750 | 0,2813 | 0,0000 | [0,0000; 0,0000] |
| E3 union + fingerprint | 0,3549 | 0,2500 | -0,0201 | [-0,0639; -0,0005] |
| E4 LambdaRank completo | 0,3281 | 0,1563 | -0,0469 | [-0,1136; 0,0118] |
| E5 hard negative same-formula | 0,3299 | 0,1875 | -0,0450 | [-0,1209; 0,0258] |
| E6 fingerprint-only | 0,0000 | 0,0000 | -0,3750 | [-0,5322; -0,2494] |
| E6 mass/context | 0,3568 | 0,2500 | -0,0182 | [-0,0960; 0,0496] |
| E6 spectral-only | 0,3659 | 0,2500 | -0,0091 | [-0,0762; 0,0515] |

Fingerprint quality:

| Modello | Mean sample Jaccard | Micro F1 |
|---|---:|---:|
| KNN validation | 0,2120 | 0,3491 |
| Compact validation | 0,0893 | 0,1639 |
| Compact train OOF | 0,0859 | 0,1582 |

I tre fold selezionano tutti l'epoca 1; la validation loss cresce mentre la training loss cala fino all'early stop. Il tiny-overfit T4 passa: loss 0,675315 -> 0,00001046 in 50 step, con gradienti finiti. Il fallimento e quindi di generalizzazione, non di implementazione.

Diagnosi:

- E1 ha 96/96 identita train con reference same-identity e 0/32 in validation: train/inference mismatch misurato.
- Nel realistic E1 peggiora 20 query, ne migliora 2 e lascia 10 invariate.
- Sei feature mostrano drift; fingerprint log-likelihood ha KS 0,307 e PSI 1,333.
- Nel model-selection i 16 positivi sono tutti `enveda-180`; 462 candidati `drug_plus` hanno zero positivi.
- E5 usa 6.144 negativi, 1.388 same-formula e 5 same-scaffold, ma non migliora E0.
- E0 realistic ha 21/32 errori same-formula e sul final 10/16; l'ambiguita isomerica e reale ma non risolta.

Risorse:

- runtime totale 632,52 s;
- shared candidate generation 55,82 s controlled e 370,32 s realistic;
- peak RSS process-wide circa 2,81 GB;
- peak VRAM PyTorch circa 33,8 MB;
- E1/E4/E5 realistic circa 1,41/1,91/0,52 s.

La v2 riproduce esattamente manifest e metriche v1. Test locali finali: 111 passati e 7 skip PyTorch opzionali nella `.venv`; test neurali eseguiti sul T4.

**Decisione:** no-go per il fingerprint encoder e per il ranker Goal 3. Conservare nearest-mass. Prossima priorita: learning curve su piu identita, target/representation fingerprint meno fragili, obiettivo pairwise/listwise same-formula e recupero target-blind top-100 -> top-25. Non integrare ancora ICEBERG/GLACIER.

Strategia multi-agent Goal 3: due subagent con ownership disgiunta hanno coperto audit ranking/validation e spectrum-to-fingerprint; l'agente principale ha integrato contratti, hard-negative mining, pipeline E0-E6, run Kaggle e documentazione.

## EXP-009 - Goal 4 baseline spettrale Kaggle v1

**Data:** 2026-10-10  
**Kernel:** `mperni/casmi26-goal4-spectral-ranking`, versione 1, COMPLETE  
**Submission:** nessuna

Primo E2E di spectral evidence, analog propagation e E0–E7 sul pool top-100
fisso. E3 porta all-validation MRR@25 da circa 0,375 a 0,402; E6 è leggermente
migliore. Il run dimostra il segnale analogico ma manca ancora di
canonicalizzazione bloccante uniforme e ablation multi-spettro complete.

## EXP-010 - Goal 4 ablation e resource accounting Kaggle v2

**Data:** 2026-10-10  
**Kernel:** stesso kernel, versione 2, COMPLETE  
**Submission:** nessuna

Confrontati max, mean, weighted, confidence-weighted, RRF, potenza spettrale e
rimozione di termini chimici. Il massimo con potenza 3 è migliore; rimuovere
l'addotto peggiora, rimuovere le trasformazioni non cambia il risultato. E1 ed
E2 selezionano peso zero. E5 è instabile fra development e final e non viene
promosso.

## EXP-011 - Catalogo canonico e blocco anti-leakage Kaggle v3

**Data:** 2026-10-10  
**Kernel:** stesso kernel, versione 3, ERROR dopo benchmark completato  
**Artifact validation:** `artifacts/goal4_kaggle_v3/goal4/goal4_results.json`  
**Submission:** nessuna

La canonicalizzazione RDKit filtra 425 mismatch da 49.620 record, lasciandone
49.195. Il benchmark E0–E7 termina, ma l'inferenza viene bloccata da
`AnalogLeakageError`: una reference train ha contenuto spettrale identico a una
query test. Il blocco è corretto e viene trattato come test avversariale reale,
non aggirato.

## EXP-012 - Goal 4 autorevole Kaggle v4

**Data:** 2026-10-10  
**Kernel:** `mperni/casmi26-goal4-spectral-ranking`, versione 4, COMPLETE  
**Artifact:** `artifacts/goal4_kaggle_v4/goal4/goal4_results.json`  
**Submission:** nessuna

Configurazione:

| Parametro | Valore |
|---|---:|
| Manifest | `138055fca36fb37bd29bf27e970a6f8ee853bdd955546a17cb815cf49f1390d0` |
| Catalogo sorgente / canonico | 49.620 / 49.195 |
| Train / validation | 96 / 32 identità |
| Development / final | 16 / 16 identità |
| Candidate pool | 100 |
| Reference OOF | 3 fold identity-disjoint |
| Bootstrap | 500 |

All-validation:

| Esperimento | MRR@25 | Hit@1 | Delta vs E0 | IC95% |
|---|---:|---:|---:|---:|
| E0 nearest-mass | 0,375217 | 0,2813 | — | — |
| E1 neutral loss | 0,375217 | 0,2813 | 0 | [0; 0] |
| E2 fragment compatibility | 0,375217 | 0,2813 | 0 | [0; 0] |
| E3 analog propagation | 0,401817 | 0,3125 | +0,026600 | [+0,002638; +0,061603] |
| E4 rank fusion | 0,375861 | 0,2813 | +0,000643 | [-0,000749; +0,002442] |
| E5 LambdaRank | 0,379178 | 0,2500 | +0,003961 | [-0,110376; +0,119523] |
| E6 same-formula analog | **0,402011** | **0,3125** | **+0,026794** | **[+0,003121; +0,061990]** |
| E7 confidence gate | 0,401817 | 0,3125 | +0,026600 | [+0,002638; +0,061603] |

Sul development E6 migliora da 0,349104 a 0,365473, delta +0,016369 con
IC95% [+0,001938; +0,033939]. Sul final congelato migliora da 0,401331 a
0,438549, delta +0,037218 con IC95% [-0,001770; +0,103166]. La direzione è
coerente, ma il final non è conclusivo da solo. Recall@25/100/1000 resta
0,875/1,000/1,000 per tutti gli esperimenti.

La nuova esclusione content-hash rimuove 1/128 reference e l'inferenza E6
completa 400 molecole con 25 candidati validi/unici. SHA-256 CSV:
`52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f`.
Runtime validation 672,53 s, inferenza test 1.500,43 s, peak RSS 1,69 GB,
VRAM 0. Test finali: 153 passed, 7 skipped, coverage 66%.

**Decisione:** promuovere E6 come baseline Goal 4 e passare a Goal 5 Scenario
C (scaling/indexing del retrieval analogico, DreaMS frozen probe). Conservare
E0 come controllo e non promuovere E5 dal final holdout.

## EXP-013 - Goal 5 v2: build C1 recuperato, runtime non sostenibile

**Data:** 2026-10-10/11

**Kernel:** `mperni/casmi26-goal5-scalable-retrieval`, versione 2,
`CANCEL_ACKNOWLEDGED` al limite del worker

**Submission:** nessuna

Il run ha costruito e salvato il catalogo C1 completo: 271.439 strutture
canoniche, 50.662 formule uniche, 11 sorgenti train, RDKit 2026.03.3. Gli array
checksummed occupano 34.821.876 byte. Ha inoltre prodotto il piano domain
A/B/C: 234 identità eleggibili, 188 development, 46 sealed, 1.097 query e
54.950 reference prima delle mask.

Il log raggiunge 43.084,15 s, circa 11 h 58 min, quasi interamente assorbiti da
canonicalizzazione/tautomer enumeration. Non esistono metriche E7–E12 complete.
Gli artifact utili sono conservati sotto `artifacts/goal5_kaggle_v2/`.

**Decisione:** rendere C1 un artifact persistente e non ricostruirlo in ogni
kernel. Spostare futuri rebuild completi su VM esterna.

## EXP-014 - Goal 5 v3: prebuilt C1 e failure E12

**Data:** 2026-10-12

**Kernel:** stesso kernel, versione 3, `ERROR`

**Runtime effettivo:** 10.254,61 s (2 h 50 min 54,6 s)

**Submission:** nessuna

Il run riusa C1, limita le reference a 2.932 prima delle mask e conserva la
stessa membership/commitment sealed. Fallisce nella prima valutazione
development con:

`ValueError: Ranked candidates for query 'AAWZDTNXLSGCEK' are outside its pool`

La causa è un'invariante E12: l'ordine mass-anchor conservava candidati E10
eliminati dalla union RRF. La correzione filtra l'anchor sull'effettiva union
pool; è stato aggiunto un test di regressione. Nessuna metrica parziale è
promossa.

## EXP-015 - Goal 5 v4: job già attivo al checkpoint

**Data:** 2026-10-12

**Kernel:** stesso kernel, versione 4, `RUNNING` al checkpoint

**Avvio:** 11:22:34 UTC / 13:22:34 Europe/Rome

**Durata verificata:** 2 h 09 min 00,6 s alle 15:31:34 Europe/Rome

**Submission:** nessuna

La v4 esercita la correzione E12 e riusa l'indice C1 persistente. Kaggle non
espone il log mentre il job è attivo, quindi non è possibile attribuire uno
stadio di avanzamento. Non viene ancora classificata come bloccata perché la
durata era inferiore al punto di failure della v3. Nessun nuovo esperimento o
run è stato avviato per questo checkpoint.

**Stop-rule:** proporre la cancellazione se resta `RUNNING` oltre 4 ore senza
artifact terminale; non superare 8 ore. Prima di cancellare, conservare stato,
versione, log e output recuperabili. Al termine, raccogliere una sola volta gli
artifact senza avviare un sostituto Kaggle.

## EXP-016 - Preflight prima submission ufficiale E6

**Data:** 2026-10-12

**Kernel:** `mperni/casmi26-goal4-spectral-ranking`, versione 4, `COMPLETE`

**Submission:** non eseguita; in attesa di approvazione

Il sorgente è stato riscaricato da Kaggle e coincide con il bundle locale dopo
normalizzazione dei line ending, SHA-256
`b41302fee0454252617e852b22cec3e48f218fb097da9cde4e304ba50f2b473d`.
Gli output remoti coincidono con gli artifact congelati; `submission.csv` ha
hash `52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f`.

Il CSV contiene 400 molecule ID unici e 25 candidati validi/unici per riga. Il
runner usa test e sample submission risolti dinamicamente e non contiene ID o
cardinalità del placeholder. Runtime end-to-end 2.190,94 s, peak RSS 1,69 GB,
VRAM 0; limite ufficiale 9 ore. Metadata offline, competition source, T4 e
asset sono verificati. Quota: 0 submission oggi/lifetime, 5 residue.

**Decisione:** versione 4 pronta; fermarsi prima dell'invio. Nessun tuning o
nuovo commit Kaggle.

## EXP-017 - Prima submission ufficiale E6

**Data:** 2026-10-12

**Kernel:** `mperni/casmi26-goal4-spectral-ranking`, versione 4, `COMPLETE`

**Submission ref:** `57109254`

**Configurazione:** E6 congelato, `analog_score`, peso 0,5, reranking limitato
alla formula dell'anchor E0. Commit modello
`04a6a89ae7fc6c32d4a65f6f63450864f5a00abc`; SHA-256 del sorgente Kaggle
normalizzato `b41302fee0454252617e852b22cec3e48f218fb097da9cde4e304ba50f2b473d`.

L'invio autorizzato è stato eseguito alle `2026-10-12T13:54:59.493Z`. Kaggle ha
restituito `COMPLETE` con public MRR@25 visualizzato **0,000**. Nello snapshot
leaderboard delle `14:42:23Z`, il team `MPerni` è 3139 su 3140; il primo score
è 0,491. Quota residua: 4 submission giornaliere.

Il runtime hidden non è esposto dalla CLI/API. La transizione terminale è stata
osservata fra 2.769,79 e 2.816,43 secondi dall'invio; questo è turnaround di
scoring, non runtime del notebook. Il runtime verificato della v4 resta
2.190,94 secondi.

**Valutazione:** il CSV è stato accettato, ma il risultato pubblico è
incompatibile con l'uso della MRR locale closed-world come stima end-to-end.
Poiché E6 riordina soltanto il catalogo train-only, l'ipotesi primaria è un
fallimento di candidate coverage/novelty. Le truth hidden non permettono di
distinguere direttamente target assente e target oltre rank 25.

**Decisione:** conservare la submission come unico punto di calibrazione. Non
modificare E6, non eseguire tuning sul leaderboard e non effettuare una seconda
submission senza nuova approvazione ed evidenza offline.

## EXP-019 - Recovery v1/v2, canonicalizzazione ufficiale e C1

**Data:** 2026-10-13

**Kernel:** `mperni/casmi26-recovery-c1-frozen-e6`

La v1 è terminata `ERROR` dopo 17,28 s: il nuovo runner richiedeva per errore
quattro spettri per identità, mentre il contratto E6 congelato ne usa tre. Il
fail-fast ha impedito inferenza e submission. La v2 corregge esclusivamente
questo parametro e termina `COMPLETE`.

Risultati v2: C1 271.439 strutture con checksum verificati, 127 reference E6,
400 molecole/1.213 spettri, 25 candidati validi e unici per riga, runtime
inference report 1.099,79 s e runtime log completo 1.119,35 s. CSV SHA-256
`dc17aed23d7ab200de4ad8e1781de0bbb147743a7aa612f382c719606c54c663`.
Il test suite chiude con 210 pass e 7 skip PyTorch opzionali.

## EXP-020 - Seconda submission ufficiale recovery

**Data:** 2026-10-13

**Submission ref:** `57135939`

**Kernel/versione:** recovery C1 frozen E6, v2

**Commit:** `cbf641604bccaf42255e14ade5470f7b1448f4a4`

La submission autorizzata termina `COMPLETE`. Public MRR@25 visualizzato
**0,000**; leaderboard snapshot `2026-10-13T08:56:16Z`: rank 3189/3193,
leader 0,491. Il runtime hidden non è esposto; turnaround osservato fra
2.792,30 e 3.113,07 s. Nessun peso/feature è stato modificato in risposta alla
prima submission.

**Decisione:** C1 corregge un difetto reale ma non è sufficiente sul public
set. Non eseguire un terzo invio. La prossima evidenza deve provenire da C2
COCONUT/reference scaling su VM e da controlli hidden-path consentiti.
