# Goal 4 — Spectral ranking e analog propagation

Ultimo aggiornamento: 2026-10-10

## 1. Esito decisionale

Il Goal 4 implementa e verifica un canale spettrale non neurale,
candidate-specific e leakage-free sopra un unico pool realistico top-100. Il
risultato autorevole è il kernel Kaggle privato
`mperni/casmi26-goal4-spectral-ranking`, versione 4; nessuna submission è stata
effettuata.

E6 è la configurazione promossa: analog propagation con peso 0,5, limitata ai
candidati aventi la formula del primo candidato nearest-mass. Su tutte le 32
query migliora MRR@25 da 0,375217 a 0,402011 (delta +0,026794; IC95%
[+0,003121; +0,061990]); sul final holdout passa da 0,401331 a 0,438549
(delta +0,037218; IC95% [-0,001770; +0,103166]). La direzione è coerente, ma
il final è troppo piccolo per una conclusione autonoma di significatività.

Il risultato non è confrontato direttamente con il public leaderboard 0,484:
le distribuzioni e i cataloghi sono differenti. Il precedente 0,7467 Goal 2
rimane un risultato controlled e non viene riutilizzato come misura end-to-end.

## 2. Contratto sperimentale

- Manifest molecule-disjoint congelato:
  `138055fca36fb37bd29bf27e970a6f8ee853bdd955546a17cb815cf49f1390d0`.
- Cohort: 128 identità, 384 spettri, tre acquisizioni per identità.
- Train/reference: 96 identità; validation: 32 identità.
- Model selection/final: 16/16 identità disgiunte e fissate nel manifest.
- Candidate generator: nearest neutral mass su catalogo target-blind.
- Candidate pool: esattamente 100 candidati per query, invariato E0–E7.
- Output metric: top-25 dello stesso pool.
- Bootstrap: 500 repliche appaiate per molecola.
- Reference analogiche train: identity-OOF a tre fold.
- Reference validation: soltanto identità train; tutte le identità e gli hash
  di contenuto validation sono proibiti dalla `LeakagePolicy`.

Il controlled benchmark Goal 3 resta disponibile come ranking condizionato ma
non è stato usato per scegliere le varianti Goal 4. Il final holdout non è stato
usato per pesi, soglie o selezione di feature.

## 3. Integrità del benchmark

L'audit Goal 4 è fail-closed su target consultation, prioritization, injection
e candidati fuori catalogo. Misura l'intero catalogo per i conteggi ppm, non il
solo pool troncato.

| Proprietà realistic benchmark | Valore |
|---|---:|
| Catalogo sorgente / canonico | 49.620 / 49.195 |
| Query / spettri validation | 32 / 96 |
| Candidate pool per query | 100 |
| Recall@25 / @100 / @1000 | 0,8750 / 1,0000 / 1,0000 |
| MRR@25 / Hit@1 E0 | 0,375217 / 0,28125 |
| Target consultati / iniettati | 0 / 0 |
| Truth rank mediano / massimo | 7,5 / 78 |

Le 32 query hanno massa neutra 243,14–438,13 Da, mediana 334,64 Da. Nel catalogo
canonico, il numero mediano di candidati entro 5/10/20/50 ppm è
14,5/17,5/27,0/56,0; i massimi sono 84/85/101/200. Il truth rank mediano è 7,5
e il massimo 78. I quattro miss top-25 sono:

| Query | Rank | Competitor exact-mass/same-formula |
|---|---:|---:|
| `DSRJKXYSTOZVCB` | 29 | 42 |
| `FCWDQPSWCREWIQ` | 46 | 70 |
| `FZFSTIVUFMTJEG` | 37 | 45 |
| `GPNBPHAIMUWFGE` | 78 | 82 |

Recall@100=1 è quindi spiegato da presenza indipendente nel catalogo e truth
rank massimo 78, non da backstop oracle. L'audit registra zero target consultati
e zero injection.

## 4. Architetture implementate

### 4.1 Spectral evidence

`spectral_evidence.py` implementa con NumPy:

- peak matching one-to-one deterministico con tolleranza Da e/o ppm;
- cosine standard, precursor-shifted e modified cosine direct+shifted;
- spectral entropy similarity con contributo dei picchi unmatched;
- neutral-loss similarity e fingerprint;
- 15 perdite con masse monoisotopiche esatte, incluse H2O, NH3, CO, CO2,
  CH3OH, HCOOH, pentose, deoxyhexose e hexose;
- matched peaks, mass error, intensity distribution, coverage low/high mass;
- aggregazione mean, max, weighted, confidence-weighted e RRF;
- bilanciamento per addotto e bin di collision energy.

I descrittori `spectrum_*` sono separati per contratto dalle feature di ranking.
Uno score query-only non viene assegnato a tutti i candidati come se fosse
discriminativo. La compatibilità candidato-spettro richiede una reference
associata alla struttura, una previsione forward o una regola di formula
esplicitamente debole.

### 4.2 Analog propagation

`analog_propagation.py` usa due retrieval separati:

1. top-100 candidati da massa;
2. top analoghi spettrali da una library train identity-disjoint entro ±200 Da.

Per ogni candidato propaga il massimo di una funzione composta da similarità
spettrale elevata a potenza, Tanimoto strutturale candidato–analogo, shared
fragment coverage, neutral-loss similarity, mass alignment, trasformazione di
massa plausibile e compatibilità addotto. Le trasformazioni sono ipotesi, non
assegnazioni strutturali.

L'implementazione pubblica prioritaria
<https://www.kaggle.com/code/prvsiyan/analog-propagation-casmi-2026-baseline>
è stata analizzata, non copiata. Il principio `spectral^3 × structural` è stato
ricostruito in codice originale e sottoposto ad ablation. La licenza del
notebook non è esposta dal metadata ottenuto via CLI, quindi il suo source non è
stato riutilizzato.

### 4.3 Ranking E0–E7

| ID | Implementazione |
|---|---|
| E0 | nearest mass |
| E1 | mass + compatibilità formula/neutral loss |
| E2 | mass + frammenti condivisi via analogo candidato-specifico |
| E3 | mass + analog propagation, peso selezionato sul development |
| E4 | RRF di E0/E1/E2/E3 |
| E5 | LightGBM LambdaRank su feature OOF |
| E6 | E3 soltanto nel gruppo della formula del candidato mass-top |
| E7 | gate E3/E0 calibrato sulla confidence analogica |

E6 non usa la formula vera. L'anchor è la formula del primo candidato E0,
disponibile in inferenza. Questo evita un oracle formula reranker.

## 5. Risultati quantitativi

### All-validation, 32 query

| Esperimento | MRR@25 | Hit@1 | Hit@5 | Hit@10 | Delta MRR vs E0 | IC95% paired |
|---|---:|---:|---:|---:|---:|---:|
| E0 | 0,375217 | 0,2813 | 0,4375 | 0,5625 | — | — |
| E1 | 0,375217 | 0,2813 | 0,4375 | 0,5625 | 0,000000 | [0; 0] |
| E2 | 0,375217 | 0,2813 | 0,4375 | 0,5625 | 0,000000 | [0; 0] |
| E3 | 0,401817 | 0,3125 | 0,5000 | 0,5625 | +0,026600 | [+0,002638; +0,061603] |
| E4 | 0,375861 | 0,2813 | 0,4375 | 0,5313 | +0,000643 | [-0,000749; +0,002442] |
| E5 | 0,379178 | 0,2500 | 0,5625 | 0,6875 | +0,003961 | [-0,110376; +0,119523] |
| **E6** | **0,402011** | **0,3125** | **0,5000** | **0,5625** | **+0,026794** | **[+0,003121; +0,061990]** |
| E7 | 0,401817 | 0,3125 | 0,5000 | 0,5625 | +0,026600 | [+0,002638; +0,061603] |

### Final holdout, 16 query mai usate per selezione

| Esperimento | MRR@25 | Hit@1 | Hit@5 | Hit@10 | Delta MRR vs E0 | IC95% paired |
|---|---:|---:|---:|---:|---:|---:|
| E0 | 0,401331 | 0,3125 | 0,4375 | 0,5625 | — | — |
| E3 | 0,438549 | 0,3750 | 0,5000 | 0,5625 | +0,037218 | [-0,001770; +0,103166] |
| E4 | 0,403311 | 0,3125 | 0,4375 | 0,5625 | +0,001980 | [0; +0,005278] |
| E5 | 0,494942 | 0,3750 | 0,7500 | 0,8125 | +0,093612 | [-0,097660; +0,297764] |
| **E6** | **0,438549** | **0,3750** | **0,5000** | **0,5625** | **+0,037218** | **[-0,001770; +0,103166]** |

Nel development split E6 migliora 6 query, ne peggiora 1 e porta MRR da
0,349104 a 0,365473 (delta +0,016369; IC95% [+0,001938; +0,033939]). Sul
final migliora 3 query, ne peggiora 1 e ne lascia 12 invariate. E5 non viene
selezionato: nel development scende a 0,263413, delta -0,085691 con IC95%
[-0,183036; -0,005763], nonostante il valore final elevato e instabile.

Candidate Recall@25/100/1000 è identico per tutti gli esperimenti perché il
pool è fissato. I delta misurano soltanto ranking.

## 6. Ablation

| Variante analogica, development | MRR@25 | Peso selezionato |
|---|---:|---:|
| combined / max / no-transform | 0,365086 | 0,50 |
| spectral power 2 | 0,362278 | 0,25 |
| no-adduct | 0,362178 | 0,25 |
| weighted / confidence-weighted | 0,356241 | 0,25 |
| RRF multi-acquisition | 0,355199 | 0,25 |
| mean | 0,353116 | 0,25 |
| spectral power 1 | 0,351277 | 0,50 |

Il massimo fra acquisizioni è preferito a mean, weighted e RRF. La potenza 3
del termine spettrale supera le potenze 1 e 2; rimuovere la compatibilità
addotto peggiora. Il termine di trasformazione non produce delta misurabile in
questo cohort e non costituisce ancora evidenza positiva autonoma.

E1 e E2 selezionano peso zero quando il loro segnale isolato peggiora il
development split. Una neutral loss compatibile con la formula è una condizione
necessaria molto debole e non distingue isomeri same-formula. Il frammento
condiviso diventa utile soltanto quando è combinato con relazione strutturale e
similarità dell'analogo.

E5 non viene promosso sulla sola performance del final: la selezione avviene
sul development split e un final di 16 identità ha intervalli troppo ampi.

## 7. Error analysis

L'audit E0 classifica:

- 4/32 target presenti oltre rank 25;
- 19/32 target nella top-25 ma non rank 1;
- 26/32 query con ambiguità same-formula;
- 18 errori top-1 same-formula/isomer proxy;
- 5 errori top-1 con formula diversa.

E6 migliora 9/32 query, ne peggiora 2 e ne lascia 21 invariate. Le query
migliorate sono `ANCDUEJHQYXHAB`, `CDLRMVRGMDBATP`, `CMHJWUOQJRYJIW`,
`DPRLEWVWYKVBLB`, `DSRJKXYSTOZVCB`, `FBMPGWPFSJQFTB`, `FDPVGWDLJOFEGX`,
`FKDVVEGBBJEBBR` e `HFCLFQASLDBBJU`; peggiorano `CFUWCLXEEBETDT` e
`DQNUSRPOQGIDES`. Sul final i tre miglioramenti sono `CDLRMVRGMDBATP`,
`FDPVGWDLJOFEGX` e `FKDVVEGBBJEBBR`; l'unico peggioramento è
`DQNUSRPOQGIDES`.

Tutte le query validation sono `enveda-180`/`timsTOF` e hanno 2–3 spettri nel
query group; i breakdown instrument/source/spectrum-count non permettono quindi
una conclusione sul domain shift. Gli addotti con pochissime query sono riportati
ma non usati per decisioni generali.

## 8. Costo computazionale

| Stadio/run | Tempo | Risorsa massima |
|---|---:|---:|
| Raccolta dataset validation | 83,10 s | — |
| Candidate generation mass, 12.800 righe | 0,11 s | — |
| Feature spettrali e analogiche | 223,99 s | — |
| Pipeline validation completa | 672,53 s | 1,69 GB RSS |
| E5 fit / inferenza | 0,38 / 0,07 s | CPU |
| Inferenza test E6, 400 molecole | 1.500,43 s | 0 byte VRAM |
| Kernel completo | circa 2.190 s | Tesla T4 disponibile, non usata |

Il costo dominante è il confronto spettrale/analogico e la canonicalizzazione,
non LightGBM. Nessun training neurale, DreaMS, ICEBERG o GLACIER è stato
eseguito. La GPU T4 è disponibile nel kernel ma il path Goal 4 non alloca VRAM.

## 9. Software quality

- Unit test per peak matching, cosine/modified/entropy, neutral loss, mass
  shift, addotto, analog propagation, aggregazione multi-spettro, catalog
  index, leakage, ranking, deduplica e inference.
- Compileall su `src`, `scripts` e `kaggle`.
- Bundle preflight statico: kernel privato, Internet off, wheel offline,
  competition/asset associati e nessuna chiamata di submission.
- Test end-to-end Kaggle privato con train/test ufficiali e CSV completo.
- Coverage locale limitata ai test unitari, coerentemente con il vincolo di non
  eseguire training/esperimenti reali in locale.

Risultato finale locale: **153 passed, 7 skipped**, coverage complessiva 66%
su 5.197 statement; i sette skip sono rami PyTorch opzionali non installati
localmente e già verificati nei run T4 Goal 3. I moduli centrali Goal 4 hanno
coverage: spectral evidence 91%, analog propagation 93%, audit 87%, cataloghi
90%, ranking 91%. `compileall` e `git diff --check` passano.

Il run Kaggle v4 ha inoltre verificato l'inferenza offline end-to-end. Una
reference train con hash spettrale identico a una query test è stata esclusa
prima dello scoring: 128 reference iniziali, 127 utilizzate. Il CSV finale ha
400 righe, 25 candidati validi e unici per riga e SHA-256
`52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f`.

## 10. Decisione Goal 5

Le evidenze selezionano principalmente lo **Scenario C**: analog propagation
produce un delta positivo e stabile sul development/all-validation, mentre E1,
E2 e LambdaRank non forniscono un guadagno ripetibile. Il Goal 5 deve quindi:

1. ampliare la reference library spettrale in modo leakage-safe e indicizzato;
2. migliorare retrieval analogico, calibrazione della confidence e
   aggregazione multi-spettro, mantenendo E0/E6 come controlli;
3. valutare DreaMS soltanto come embedding pretrained congelato;
4. misurare in parallelo l'espansione Tier 1 del catalogo, perché il benchmark
   locale non stima la coverage delle 400 identità test;
5. introdurre ICEBERG/GLACIER solo se il residuo same-formula dimostra la
   necessità di uno scorer forward candidato-spettro.

ICEBERG/GLACIER restano candidati per un forward reranking successivo, non per
il primo passo Goal 5. Il loro costo è giustificabile solo dopo aver ampliato e
stabilizzato il retrieval analogico o se un'analisi mirata dimostra che il
residuo dominante è incompatibilità frammento-struttura fra isomeri.

## 11. Limiti

- 32 validation e 16 final sono campioni piccoli; anche un delta positivo può
  avere intervallo final che attraversa zero.
- Tutte le validation provengono da un solo source/strumento.
- La library analogica è piccola rispetto al train completo.
- Formula compatibility non risolve isomeri costituzionali.
- Il public leaderboard resta non osservato per il nostro sistema finché
  l'utente non autorizza una submission.
- I risultati Goal 4 closed-world non misurano novelty generation.
