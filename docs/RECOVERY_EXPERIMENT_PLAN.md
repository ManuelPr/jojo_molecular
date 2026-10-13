# Recovery experiment plan

Data: 2026-10-12  
Vincoli: niente Goal 6, grandi training, nuovi benchmark Kaggle multi-ora o
seconda submission senza approvazione

## Obiettivo

Ottenere una seconda pipeline competitiva separando rigorosamente coverage,
retrieval e ranking. Il public score 0,000 è un punto di calibrazione, non un
segnale per fare tuning.

## Stato di partenza

- E6 resta congelato: `analog_score`, peso 0,5, reranking same-formula.
- C0: 49.195 strutture, domain-dev catalog recall 57,45%.
- C1: 271.439 strutture mmap già costruite, domain-dev catalog recall 100%.
- C1 mass-only: Recall@25/100/1000 89,89/99,47/100%, MRR@25 0,3801.
- E6 v4 usa 127 reference spectra; il manifest Goal 5 rende disponibili 2.748
  reference nel development A prima di ulteriori ladder.
- Goal 5 Kaggle v4 è `COMPLETE`; log effettivo 30.106,64 s
  (8 h 21 min 46,64 s), oltre il budget di 8 ore. Artifact e log sono stati
  recuperati senza rilancio.

## Milestone R0 — Rendere il percorso fail-fast

**Implementazione**

- eliminare, nella futura pipeline candidata, il fallback E6→E3 e i default
  impliciti di feature/peso;
- scrivere nel report runtime hash runner, artifact, catalogo, reference library
  e sample/test fingerprint;
- validare cardinalità query dal sample corrente, non da costanti;
- registrare distribuzione candidati, membership catalogo, ppm del primo e dei
  25 candidati, addotti unsupported e quota di ranking duplicati;
- salvare `submission.csv` e report anche se il job è solo rehearsal.

**Done verificabile**

- una configurazione mancante o inattesa termina con errore;
- test di regressione per test sostituito, ordine query, nessun default row,
  addotti ufficiali e canonicalizzazione;
- hash del catalogo caricato uguale al manifest atteso.

**Costo**: locale, meno di 1 ora di sviluppo/test; nessun training.

## Milestone R1 — C1 con ranking E6 congelato — completata

**Ipotesi**: C1 risolve la maggior parte del problema di membership, ma serve
reranking per i distractor same-formula.

**Esperimenti terminali v4**

1. C0/E7 ed E8/C1 con E6 congelato sono stati misurati.
2. E9 exact-index replica E8.
3. E10 dynamic pool replica la MRR E8 e porta pool recall a 1,0.
4. E12 RRF-union aumenta la coverage del pool ma non la MRR.

Misurare per A/B: catalog recall, Recall@25/100/1000, MRR@25, conditional MRR,
Hit@1/5/10, paired delta, migliorate/peggiorate, same-formula e runtime/RSS.
Condition C resta un test di assenza strutturale, non una metrica da ottimizzare.

**Esito del gate**: non promosso. E8−E7 development A è +0,0403 MRR, ma l'IC95%
[-0,0350; 0,0979] attraversa zero e Hit@1 scende di 0,0426. In development B
il delta è −0,0025; sul sealed A/B è rispettivamente +0,0065/−0,0187, entrambi
incerti. C1 migliora coverage e Hit@5/10, non la selezione del primo candidato.

**Costo osservato**: il notebook completo ha richiesto 8 h 21 min 46,64 s; non
è compatibile con il nuovo ruolo Kaggle. I rerun devono usare VM e checkpoint.

## Milestone R2 — Scaling della reference library

**Ipotesi**: 127 reference non sono sufficienti per generalizzare retrieval
analogico.

Mantenendo identici C1, E6, peso e candidate pool, valutare una ladder
pre-dichiarata:

- 127 reference (baseline);
- 512;
- 2.000;
- 2.748 reference ammissibili development;
- tutte le reference ammissibili solo se distinte per identity/content e dentro
  il budget.

Per ogni gradino misurare retrieval hit/coverage degli analoghi, delta paired
MRR e Hit@1, query migliorate/peggiorate, breakdown per adducto e numero di
spettri, query time e peak RSS. La selezione delle reference deve usare qualità
e provenance disponibili in inferenza, non la truth query.

**Gate**: proseguire oltre 2.748 solo se il gradino precedente porta un delta
stabile e il costo cresce sub-quadraticamente. Nessuna modifica dei pesi E6 in
questa fase.

**Costo**: VM CPU 16–32 vCPU, 64 GB RAM, 4–8 ore stimati. GPU non necessaria.

## Milestone R3 — C2 e C3

Costruire su VM, in ordine:

1. C2 = C1 + COCONUT;
2. C3 = C2 + ChEBI + LIPID MAPS;
3. eventuale PubChem selettivo solo dopo una decisione esplicita.

Ogni tier produce raw manifest, normalizzazione shardata, reject report,
provenance/licenza, overlap, Parquet canonico, indice mmap e checksum. Prima si
misura catalog/candidate recall; solo dopo si esegue E6 congelato.

**Gate**: un tier non viene promosso solo perché è più grande. Deve aumentare
coverage su holdout pertinente senza rendere Recall@25 o MRR irrecuperabili e
deve rientrare nel budget Kaggle di inferenza.

**Costo**: 16–32 vCPU, 64 GB RAM, 100–250 GB disco, 8–16 ore per C2/C3 come
budget iniziale da calibrare con uno shard smoke. PubChem escluso dalla stima.

## Milestone R4 — Rehearsal Kaggle di sola inferenza

Solo dopo il congelamento offline:

- pubblicare artifact C1/C2 scelto e reference index già costruiti;
- eseguire un unico smoke bounded su subset;
- eseguire una sola inferenza offline completa sul test fornito;
- verificare runtime <9 ore con margine minimo 25%, RAM/VRAM, hash e formato;
- nessuna canonicalizzazione completa, benchmark o training nel notebook;
- scaricare output/log una volta e confrontare il report con l'atteso.

**Done verificabile**: 400/numero dinamico di query, 1–25 candidati validi e
unici, nessun fallback, nessun addotto unsupported, catalog hash corretto,
runtime proiettato <6 h 45 min.

## Milestone R5 — Approval gate

La seconda submission viene proposta, non eseguita, soltanto se:

- non rimane un errore significativo di percorso;
- la coverage offline è maggiore di C0 su benchmark domain-matched;
- il ranking con catalogo ampliato è stato misurato e non scelto sul public LB;
- sealed holdout è stato aperto una sola volta dopo congelamento e conferma il
  segnale o ne documenta l'incertezza;
- notebook e artifact hanno hash/versione, compatibilità offline e runtime;
- l'utente concede nuova approvazione esplicita.

Dopo l'eventuale invio si registrano public MRR@25, posizione, hash, versione e
runtime, senza lanciare automaticamente un terzo tentativo.

## Job Goal 5 v4

Stato finale: `COMPLETE`. Il log termina a 30.106,64 s (8 h 21 min 46,64 s).
Artifact recuperati sotto `artifacts/goal5_kaggle_v4/`; `goal5_results.json`
SHA-256 `4daa02b1fd9d5b40b30075544f3ed4a809e674c712ec7e190b86bd10d3c65e47`.
Nessuna submission è stata effettuata. Il job non va rilanciato su Kaggle.

## Ordine economico consigliato

1. archiviare Goal 5 v4 terminale come evidenza negativa sulla promozione C1;
2. rendere fail-fast il runner candidato;
3. eseguire soltanto la ladder reference controllata sulla VM riusando C1;
4. costruire C2, poi C3, misurando coverage e degradazione Hit@1;
5. fare un solo rehearsal Kaggle di inferenza;
6. fermarsi al gate di approvazione.

Questo percorso attacca prima il difetto dimostrato (membership C0), poi la
capacità di ordinare i nuovi distractor, e rinvia i database più costosi finché
non producono informazione decisionale.

## Checkpoint eseguito 2026-10-13

R0 e R4 sono completate nel commit
`cbf641604bccaf42255e14ade5470f7b1448f4a4`. Il kernel recovery v2 ha usato C1
verificato, E6 congelato e nessun fallback; runtime 1.119,35 s, 400 righe e 25
candidati per riga. La seconda submission autorizzata `57135939` è terminata
con public 0,000 e rank 3189/3193. Di conseguenza R1 risolve la coverage sul
proxy ma non supera il gate pubblico. Il passo successivo resta R2/R3 su VM,
partendo da COCONUT; non eseguire una terza submission né iniziare Goal 6.

