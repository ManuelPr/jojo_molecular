# Zero-score root-cause analysis

Data dell'audit: 2026-10-12  
Submission: `57109254`  
Esito Kaggle: `COMPLETE`, Public MRR@25 visualizzato `0.000`

## Executive finding

La causa più probabile è il **fallimento closed-world del candidate catalog,
amplificato da una validation Goal 4 selezionata dallo stesso sottoinsieme usato
per costruire C0**. C0 contiene 49.195 identità canoniche ricavate soltanto
dalle prime 300.000 righe del train. Sul proxy domain-matched Goal 5 di sviluppo
contiene 108 target su 188 (catalog recall 57,45%); C1, costruito sull'intero
train, ne contiene 188/188.

Questo risultato dimostra che il valore locale Goal 4 di 0,402 non stimava una
pipeline open-world. Non dimostra quante truth hidden siano assenti: le etichette
hidden e il CSV prodotto dal rerun hidden non sono accessibili. Inoltre `0.000`
è il valore visualizzato a tre decimali e non prova che lo score non arrotondato
sia matematicamente zero.

Non emerge invece evidenza di un errore sistematico di formato, risoluzione del
test, addotti o massa. Rimane una lacuna forense: Kaggle non espone output e log
del rerun hidden, quindi un guasto specifico di quel solo percorso non può essere
escluso definitivamente.

## Evidenza riproducibile

L'audit è prodotto da `scripts/run_zero_score_forensics.py` e salvato in
`artifacts/zero_score_recovery/forensics.json`. Non apre il sealed holdout, non
addestra modelli e non avvia job Kaggle.

| Controllo | Risultato | Interpretazione |
|---|---:|---|
| C0 righe lette | 300.000 | limite effettivo E6 |
| C0 strutture sorgente / canoniche | 49.620 / 49.195 | 425 reject di identità canonica |
| C1 strutture canoniche | 271.439 | indice mmap Goal 5 riusato e verificato |
| C0 catalog recall domain-dev | 108/188 = 57,45% | 80 truth irrecuperabili da E6 |
| C1 catalog recall domain-dev | 188/188 = 100% | C1 chiude la lacuna su questo proxy |
| C0 Recall@25 / @100 / @1000 | 56,91% / 57,45% / 57,45% | recall limitato quasi interamente dalla membership |
| C1 Recall@25 / @100 / @1000 | 89,89% / 99,47% / 100% | coverage risolta, ordinamento più difficile |
| C0 mass-only MRR@25 | 0,4069 | alto perché i target coperti sono il sottoinsieme facile |
| C0 conditional MRR@25 | 0,7082 | non confrontabile come end-to-end |
| C1 mass-only MRR@25 | 0,3801 | più distractor non implicano ranking migliore |
| Same-formula competitor medi C0 / C1 | 1,55 / 14,18 | espandere il catalogo richiede reranking |

Le metriche A e B sono identiche in questo audit perché il candidate generator
mass-only non usa la visibilità degli spettri reference. In Condition C la truth
è rimossa fisicamente e tutte le metriche di retrieval closed-world sono zero per
definizione. Il sealed holdout non è stato aperto.

## Fase A — Submission forensics

### Test e placeholder

Il runner Kaggle v4, SHA-256
`b41302fee0454252617e852b22cec3e48f218fb097da9cde4e304ba50f2b473d`,
risolve dinamicamente la directory contenente `train.parquet`, `test.parquet` e
`sample_submission.csv`. Non contiene ID hardcoded del placeholder. Il writer
itera gli ID del sample corrente e fallisce se manca una query, una lista è
vuota, un candidato è invalido o vi sono duplicati canonici.

Sul rehearsal ufficiale disponibile:

- 400 molecole e 1.213 spettri vengono letti dinamicamente;
- ogni riga contiene 25 identità valide e uniche;
- sono presenti 395 ranking distinti; il ranking più frequente compare 2 volte;
- il 100% dei 10.000 candidati appartiene al catalogo C0;
- nessun addotto è unsupported;
- l'errore del primo candidato rispetto alla massa neutra mediana ha mediana
  1,81 ppm, media 2,58 ppm e p90 3,41 ppm.

Questi dati escludono un fallback globale a una riga di default nel rehearsal.
Non provano il contenuto del file hidden.

### Massa e addotti

Sui 876 spettri delle 188 identità domain-dev, tutti gli addotti sono supportati.
La massa neutra calcolata confrontata con la exact mass della truth C1 mostra:

- mediana 1,65 ppm;
- media 1,76 ppm;
- p90 3,12 ppm;
- massimo 21,01 ppm su un singolo record;
- nessuna query priva di massa.

Sono coperti `[M+H]+`, `[M-H]-`, `[M+Na]+`, `[M+K]+`, `[M+NH4]+`, `[M+Cl]-`,
`[M+CH2O2-H]-`, `[M-H2O+H]+` e `[M-2H2O+H]+`. Non si osserva lo scostamento
di decine o centinaia di ppm che ci si aspetterebbe da una correzione di carica o
addotto sistematicamente errata.

### Catalogo e canonicalizzazione

C0 è costruito solo da metadata train, senza consultare target o test. Dopo la
canonicalizzazione RDKit 2026.03.3 contiene 46.847 strutture `enveda-180` e
2.348 `drug_plus`. La deduplica della submission usa la stessa funzione
tautomer-InChIKey14 usata dal catalogo. Il CSV è stato accettato da Kaggle, perciò
struttura del file e associazione alla competizione sono almeno sintatticamente
valide. La parità semantica con lo scorer privato non è direttamente osservabile.

### Difetto reale ma non causale osservato

Il runner contiene un fallback di selezione: un `selected_experiment` inatteso
viene convertito in E3 e alcuni campi hanno default. È un comportamento troppo
silenzioso e deve diventare fail-fast prima di una seconda pipeline. L'artifact
effettivo v4 registra però E6, `analog_score` e peso 0,5; il fallback non è stato
attivato nella submission 57109254.

## Valutazione delle quattro ipotesi

| Ipotesi | Evidenza a favore | Evidenza contraria | Giudizio |
|---|---|---|---|
| Errore inferenza/submission | output hidden non disponibile; esiste un fallback di selezione | sorgente verificato, root dinamica, 400 output dinamici, CSV valido, run `COMPLETE` | possibile residuo, non causa primaria osservata |
| Target assente dal catalogo | C0 copre solo 57,45% del proxy domain-dev; E6 non genera nuove strutture | coverage hidden non misurabile | **causa primaria, confidenza alta** |
| Domain shift | Goal 4 usa 32 target `enveda-180`/timsTOF, massa 243–438 e pochi addotti; hidden atteso molto più ampio | proxy Goal 5 è ancora train-derived | **co-causa probabile, confidenza medio-alta** |
| Candidate generation/ranking | C1 porta 14,18 isomeri/formula medi e mass-only MRR scende; E6 usa solo 127 reference | conversione massa è accurata e C1 Recall@1000 è 1 sul proxy | problema secondario dopo coverage; errore massa sistematico non supportato |

## Perché la validation Goal 4 era fuorviante

Le 32 identità Goal 4 provenivano dallo stesso universo ristretto da cui veniva
costruito C0 e la truth era quindi presente per costruzione. Il suo Recall@100
di 1,0 significa soltanto che, una volta garantita la membership nel catalogo,
la nearest-mass collocava tutte le truth entro 100. Non misurava la probabilità
che una struttura hidden fosse nel catalogo.

E6 usava inoltre 127 spettri reference, uno per identità congelata, contro 2.748
reference ammissibili nel manifest Goal 5 development A. Questa scarsità non può
rendere recuperabile una truth assente, ma limita anche la capacità di ordinare
gli analoghi quando la truth è presente.

## Conclusione operativa

La strada meno costosa non è modificare E6 o fare tuning sulla leaderboard.
È sostituire C0 con C1 già costruito, misurare separatamente membership e
ranking su domain-dev, e scalare le reference mantenendo il ranking E6
congelato. Solo dopo va aggiunto COCONUT e quindi ChEBI/LIPID MAPS su VM con
checkpoint. Una seconda submission richiede un rehearsal offline completo e
nuova approvazione esplicita.

## Addendum — Goal 5 v4 terminale

Il job preesistente `mperni/casmi26-goal5-scalable-retrieval` v4 è terminato
`COMPLETE`. Gli artifact sono stati scaricati una volta in
`artifacts/goal5_kaggle_v4/`; nessun job sostitutivo o submission è stato
avviato. Il log copre 30.106,64 s, cioè **8 h 21 min 46,64 s**, oltre il budget
operativo di 8 ore. `goal5_results.json` ha SHA-256
`4daa02b1fd9d5b40b30075544f3ed4a809e674c712ec7e190b86bd10d3c65e47` e
l'indice C1 da 271.439 strutture supera la verifica dei checksum.

I risultati confermano che coverage e ranking sono problemi distinti:

| Stage/condizione | E7 C0 MRR@25 | E8 C1 MRR@25 | Delta paired | IC95% | Hit@1 E7→E8 |
|---|---:|---:|---:|---:|---:|
| Development A | 0,4179 | 0,4581 | +0,0403 | [-0,0350; 0,0979] | 0,3457→0,3032 |
| Development B | 0,4107 | 0,4082 | -0,0025 | [-0,0804; 0,0595] | 0,3404→0,2500 |
| Sealed A | 0,5005 | 0,5069 | +0,0065 | [-0,1517; 0,1595] | 0,4565→0,3696 |
| Sealed B | 0,4890 | 0,4703 | -0,0187 | [-0,1727; 0,1290] | 0,4348→0,3261 |

E8 porta Recall@25/100 da 0,5691/0,5745 a 0,8989/0,9947 sul development,
ma nessun delta MRR è statisticamente stabile e Hit@1 peggiora. E9 ed E10
producono lo stesso ranking di E8; E12 migliora la coverage del pool ma lascia
MRR invariata. In Condition C tutte le metriche sono zero perché la struttura è
fisicamente assente.

Quindi C1 è necessario ma non sufficiente e non è promosso automaticamente per
una seconda submission. La causa dello zero pubblico rimane più probabilmente
coverage/novelty hidden più domain shift; il risultato v4 mostra inoltre che il
ranking E6 congelato non sfrutta bene i distractor aggiunti. L'effetto puro
127→2.748 reference non è isolato da una ladder controllata e resta da misurare
su VM.

## Addendum 2026-10-13 — seconda submission di recovery

L'audit dello scorer ufficiale ha trovato un difetto reale: prima della
tautomerizzazione lo scorer esegue `Chem.RemoveStereochemistry`, mentre la
funzione locale non lo faceva. La funzione e il writer sono stati corretti e
coperti da un test derivato dall'implementazione ufficiale. Il confronto sui
10.000 slot della prima submission ha però prodotto **zero** InChIKey14
diversi: il difetto non spiega lo 0,000 della submission 57109254.

Il difetto C0 è stato corretto separatamente con una pipeline fail-fast che
usa C1 da 271.439 strutture e conserva esattamente E6 (`analog_score`, peso
0,5, same-formula, 127 reference). Il rehearsal Kaggle v2 è `COMPLETE`:
400 query, 1.213 spettri, 25 candidati canonici unici per riga, runtime kernel
1.119,35 s e CSV SHA-256
`dc17aed23d7ab200de4ad8e1781de0bbb147743a7aa612f382c719606c54c663`.

La seconda submission autorizzata, ID `57135939`, è `COMPLETE` ma ha ancora
Public MRR@25 visualizzato **0,000**. Il dump leaderboard del
`2026-10-13T08:56:16Z` registra posizione 3189/3193. Questo falsifica
l'ipotesi che il solo troncamento C0 fosse la causa sufficiente. C0 rimane un
bug dimostrato sul proxy domain-matched, ma il public set richiede molto
probabilmente coverage esterna/novelty non contenuta nemmeno in C1, oppure
esiste un difetto hidden-only che i log consentiti non rendono osservabile.
Nessuna terza submission viene proposta senza nuova evidenza offline.

