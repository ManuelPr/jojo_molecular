# Prima submission ufficiale — E6 v4

Ultimo aggiornamento: 2026-10-12

## Esito

La submission autorizzata è stata eseguita una sola volta usando esclusivamente
il commit Kaggle già completato:

- kernel: `mperni/casmi26-goal4-spectral-ranking`;
- versione: **4**;
- modello: Goal 4 **E6**;
- commit modello: `04a6a89ae7fc6c32d4a65f6f63450864f5a00abc`.

La v4 è lo stesso snapshot del preflight. Nessun parametro, peso, feature,
asset o sorgente è stato modificato e non è stata creata una nuova versione.

| Campo | Valore |
|---|---|
| Submission ref | `57109254` |
| Timestamp invio | `2026-10-12T13:54:59.493Z` |
| Stato | `COMPLETE` |
| Public MRR@25 visualizzato | **0,000** |
| Posizione allo snapshot | **3139 / 3140** |
| Snapshot leaderboard | `2026-10-12T14:42:23Z` |
| Miglior score allo snapshot | 0,491 |
| Quota dopo l'invio | 1 oggi, 1 lifetime, 4 residue |

Il valore è esposto da Kaggle con tre decimali e va registrato come valore
visualizzato, non come prova che lo score non arrotondato sia esattamente zero.

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

## Limiti e quota al preflight

Preflight CLI del 2026-10-12:

- submission oggi: 0;
- submission lifetime: 0;
- quota residua oggi: 5;
- deadline: 2026-12-14 23:59 UTC;
- Internet deve restare disabilitato;
- il file deve chiamarsi `submission.csv`.

## Invio e runtime

L'approvazione esplicita è stata ricevuta e l'invio è stato effettuato con la
CLI ufficiale, specificando kernel `mperni/casmi26-goal4-spectral-ranking`,
versione 4 e file `submission.csv`. Kaggle ha mantenuto lo stato `PENDING` fino
alla transizione terminale osservata tra `14:41:09.280Z` e `14:41:55.928Z`.
Il turnaround osservato è quindi compreso tra 2.769,79 e 2.816,43 secondi.

Kaggle CLI 2.2.4 e il modello submission dell'API non espongono il runtime del
rerun hidden. Il campo resta correttamente `N.A.`; non viene sostituito con il
turnaround. Il runtime verificato del commit v4 resta 2.190,94 secondi.

## Interpretazione del risultato

Il formato è stato accettato e la submission è `COMPLETE`, quindi il preflight
ha verificato correttamente esecuzione, formato e indipendenza dagli ID del
placeholder. Tuttavia, E6 può soltanto riordinare strutture presenti nel
catalogo chiuso costruito dal train. Il public `0,000` è pertanto evidenza forte
di un problema end-to-end di candidate coverage/novelty sul test nascosto, non
una misura isolata della qualità del reranker E6.

Questa è un'inferenza, perché le identità hidden non sono disponibili: non si
può distinguere direttamente fra target assenti dal catalogo e target presenti
ma tutti oltre la posizione 25. Non viene effettuato tuning sul singolo punto
leaderboard e non viene tentata una seconda submission.
