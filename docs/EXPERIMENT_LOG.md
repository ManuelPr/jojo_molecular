# Registro esperimenti

Tutti i risultati qui riportati sono locali o prodotti da kernel Kaggle privati. Nessuna riga rappresenta una submission ufficiale o un punteggio leaderboard.

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
