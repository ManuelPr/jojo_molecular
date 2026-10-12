# Prima submission ufficiale — preflight E6

Ultimo aggiornamento: 2026-10-12

## Decisione

Il candidato è **READY / AWAITING APPROVAL**. La submission non è stata
effettuata. Va utilizzato esclusivamente il commit Kaggle già completato:

- kernel: `mperni/casmi26-goal4-spectral-ranking`;
- versione: **4**;
- modello: Goal 4 **E6**;
- commit modello: `04a6a89ae7fc6c32d4a65f6f63450864f5a00abc`.

Non creare una nuova versione del kernel prima della prima submission: la v4 è
il commit che ha già eseguito end-to-end la baseline congelata e ha prodotto gli
artifact verificati. Nessun parametro, peso o feature è stato modificato.

## Integrità del codice Kaggle

Il sorgente corrente è stato riscaricato da Kaggle. Il contenuto è identico al
bundle locale dopo normalizzazione LF/CRLF.

| Elemento | SHA-256 |
|---|---|
| Sorgente Kaggle raw | `467ea85105640f235835f9eff1812789135747a5392adae06d17b0e0c6f68875` |
| Sorgente normalizzato / bundle locale | `b41302fee0454252617e852b22cec3e48f218fb097da9cde4e304ba50f2b473d` |
| Metadata remoto | `a9246757be74c9484e87364efbfd4b1e042e65c4baacf5e760c23011d2298167` |
| Log completo v4 | `77c6fed1e554c1d4bc01cd391c410945bc056fbe306c286eef628de5d9bf165b` |

I moduli Goal 4 nel wheel attualmente pubblicato sono invariati rispetto al
commit E6. I file Goal 5 aggiuntivi non sono importati dal runner. La versione
Kaggle v4 conserva inoltre lo snapshot delle sorgenti dati associato al commit.

## Compatibilità con hidden test

Il runner non contiene molecule ID del placeholder né assume 400 query:

1. individua dinamicamente l'unica directory Kaggle con `train.parquet`,
   `test.parquet` e `sample_submission.csv`;
2. legge e raggruppa i `molecule_id` dal `test.parquet` fornito al runtime;
3. legge l'ordine richiesto dal `sample_submission.csv` fornito al runtime;
4. fallisce se mancano predizioni per un ID richiesto;
5. canonicalizza e deduplica ogni riga tramite InChIKey14;
6. scrive `/kaggle/working/submission.csv`.

Kaggle sostituisce il dataset pubblico con quello hidden durante la scoring run.
Il placeholder è stato usato soltanto come rehearsal tecnico, non come sorgente
di identità hard-coded o di truth.

## Asset offline

Metadata del kernel verificati:

- `enable_internet: false`;
- kernel privato;
- competition source collegata;
- dataset `mperni/casmi26-baseline-assets` collegato;
- Tesla T4 selezionata;
- immagine Kaggle identificata dal digest
  `2757e0c7d1e0a9cb43da657b97e223c321a98f5014bdf64f44f2f6b083ad2b2f`.

Il dataset asset corrente contiene un solo wheel progetto, un solo wheel RDKit
2026.03.3 CPython 3.13 e il file identità congelato con hash
`8a1445fbe1f762c464b13364d8f6927baf72d4e7a2d8fa9be39a65ece26364b4`.
Il preflight asset termina senza errori.

## Output e formato

| Controllo | Risultato |
|---|---:|
| Nome root output | `submission.csv` |
| Righe / molecule ID unici | 400 / 400 |
| Candidati per riga | 25–25 |
| SMILES invalidi | 0 |
| Duplicati canonici per riga | 0 |
| Colonne | `molecule_id,smiles` |
| Hash CSV | `52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f` |

L'output riscaricato direttamente dalla versione Kaggle coincide byte-per-byte
con l'artifact congelato locale.

## Runtime e margine

| Fase | Runtime |
|---|---:|
| Benchmark/selezione congelata | 672,53 s |
| Inferenza test | 1.500,43 s |
| Commit end-to-end | 2.190,94 s, circa 36 min 31 s |
| Limite ufficiale CPU/GPU | 9 h |

Il commit usa circa il 6,8% del budget e lascia circa 8 h 23 min di margine.
Peak RSS: 1.689.780.224 byte; VRAM allocata: 0. Il percorso è CPU-bound pur
essendo il commit configurato su T4.

## Limiti e quota

Preflight CLI del 2026-10-12:

- submission oggi: 0;
- submission lifetime: 0;
- quota residua oggi: 5;
- deadline: 2026-12-14 23:59 UTC;
- Internet deve restare disabilitato;
- il file deve chiamarsi `submission.csv`.

## Gate finale

Il controllo UI del pulsante `Submit to Competition` non è stato completato
perché il helper locale di automazione browser non si è inizializzato. Non è un
errore del kernel: stato `COMPLETE`, metadata e output sono disponibili via API
Kaggle. Dopo approvazione esplicita, il primo passo sarà aprire la versione 4 e
verificare visivamente il pulsante; il secondo e ultimo passo sarà inviare
quella stessa versione, senza salvarne una nuova.

Subito dopo l'invio vanno registrati:

- timestamp e versione effettivamente inviata;
- SHA-256 del sorgente;
- runtime hidden;
- public MRR@25;
- posizione pubblica al momento della lettura;
- eventuale errore o differenza rispetto al rehearsal.
