# Goal 3: neural fingerprints e ranking isomer-aware

Data: 2026-10-09  
Run autorevole: Kaggle privato `mperni/casmi26-goal3-fingerprint-ranking`, versione 2  
Artifact locale: `artifacts/goal3_kaggle_v2/goal3/goal3_results.json`

## 1. Esito decisionale

Il Goal 3 e completato come esperimento negativo informativo. Il sistema spectrum-to-fingerprint, il training OOF e il ranker isomer-aware funzionano, ma nessuna variante migliora in modo credibile nearest-mass sul benchmark realistico. Il modello neurale compatto generalizza peggio del baseline KNN e il model-selection assegna peso zero alla fingerprint nei sistemi lineari E2/E3.

La conclusione non e di aumentare la complessita. La prossima priorita e migliorare dati, rappresentazione e obiettivo fingerprint, insieme alla top-25 candidate generation. ICEBERG/GLACIER e un Transformer piu grande restano sospesi finche un segnale fingerprint semplice non produce un delta positivo molecule-disjoint.

## 2. Audit del Candidate Recall@25

Il Recall@25 pari a 1,0000 di Goal 2 era corretto per un benchmark di ranking controllato, ma non era una stima end-to-end realistica. Il catalogo bounded da 4.096 strutture veniva costruito dando priorita alle identita target selezionate; il target era quindi garantito nel catalogo e, quando necessario, reinserito nel pool controllato. Questo misura l'ordinamento condizionato alla presenza del target.

Goal 3 mantiene esplicitamente due protocolli:

| Audit | Controlled | Realistic |
|---|---:|---:|
| Strutture nel catalogo | 4.096 | 49.620 |
| Target consultati nella costruzione | 128 | 0 |
| Target validation prioritizzati | 32 | 0 |
| Inserimenti target rilevati | 32 | 0 |
| Catalog recall, 32 query | 1,0000 | 1,0000 |
| Pool recall@1000 | 1,0000 | 1,0000 |
| Candidate Recall@25 | 1,0000 | 0,8750 |
| Candidate Recall@100 | 1,0000 | 1,0000 |
| Mediana competitor same-formula nel pool | 0,0 | 10,5 |
| Mediana competitor exact-mass nel pool | 0,0 | 10,5 |

Il protocollo realistico deriva il catalogo soltanto dalle prime 300.000 righe del train, conserva l'ordine target-blind della sorgente e non accetta backstop oracle. Tutti i 32 target sono presenti nel database, ma quattro non entrano nella top-25 nearest-mass. La performance controlled e quindi riportata come conditional ranking; la performance realistic e quella end-to-end primaria.

Un audit metadata-only sul cohort congelato mostra inoltre che 114/128 identita hanno almeno un'altra struttura con la stessa formula nel database; il numero di competitor per formula, escluso il target, ha mediana 9,5, percentile 90 pari a 38 e massimo 84. Il problema isomerico e reale nel database esteso, mentre il catalogo controlled lo nasconde quasi completamente.

## 3. Dati, split e prevenzione del leakage

- Scan massimo: 300.000 righe.
- Strutture uniche valide: 49.620; masse non valide: 0.
- Cohort congelato: 128 InChIKey14, 384 spettri, massimo tre acquisizioni per identita.
- Protocollo: molecule-disjoint con seed 2026.
- Training fingerprint: 192 spettri appartenenti a 96 identita.
- Validation fingerprint/ranking: 64 spettri appartenenti a 32 identita.
- Model-selection e final evaluation: 16 identita ciascuno, fissati nel manifest.
- Candidate pool massimo: 1.000; bootstrap appaiato: 500 repliche per identita.

L'audit leakage passa tutti i controlli: nessun overlap di identita o contenuto spettrale vietato, nessuna observation validation nel fit, nessuna feature derivata dal target e provenance completa.

Le feature neurali usate per addestrare E4/E5 sono predizioni OOF a tre fold separati per identita. Il ranker originale E1, invece, vede durante il training uno spettro di riferimento della stessa identita per tutte le 96 identita train; in validation molecule-disjoint tale overlap e zero. Questa asimmetria e una causa misurata del train/inference mismatch, non leakage del validation set.

## 4. Architetture implementate

### Baseline non neurale

`FingerprintKNNBaseline` costruisce vettori spettrali deterministici con bin di frammenti e neutral loss, precursor mass, collision energy e ion mode. Predice la fingerprint come media pesata delle cinque acquisizioni train piu simili. Le predizioni train per il ranker sono anch'esse identity-OOF.

### Compact peak encoder

Il modello PyTorch di riferimento ha 104.481 parametri e memoria lineare nel numero di picchi:

1. embedding Fourier di fragment m/z e neutral loss, con intensita;
2. MLP condiviso per picco;
3. masked mean, max e gated pooling;
4. precursor mass, collision energy, adduct e ion mode come metadata inference-safe;
5. MLP finale verso 512 bit Morgan/ECFP, radius 2.

La loss e BCE-with-logits pesata per bit con rapporto negativi/positivi, limitato a 25. L'ottimizzatore e AdamW, mixed precision su CUDA, batch 16, massimo 12 epoche, patience 4 e checkpoint per fold/finale.

E implementato anche un piccolo peak Transformer, con masking e test forward/backward, ma non e stato promosso all'esperimento Kaggle: il modello piu semplice e gia fortemente data-limited e aggiungere attenzione non e giustificato dai risultati.

### Ranking e hard negatives

Le feature fingerprint sono Bernoulli log-likelihood, soft Jaccard e frazione di bit attivi del candidato. Sono aggiunti group size per formula e exact mass. E4 usa LightGBM LambdaRank con feature spettrali, massa, fingerprint e contesto chimico.

E5 usa lo stesso ranker su 64 hard negative per query, ordinati per:

1. stessa formula, stesso scaffold e alta Tanimoto;
2. stessa formula e stesso scaffold;
3. stessa formula;
4. massa vicina o alto rank del baseline corrente.

InChIKey14 equivalenti non sono mai negativi. Nel realistic sono stati selezionati 6.144 negativi: 1.388 same-formula e 5 same-scaffold. Nel controlled i same-formula sono soltanto 129/6.144, ulteriore evidenza che quel catalogo sottostima la difficolta isomerica.

## 5. Qualita delle fingerprint

| Modello, molecule-disjoint | Accuracy bit | Micro F1 | Micro Jaccard | Mean sample Jaccard |
|---|---:|---:|---:|---:|
| KNN, validation | 0,9159 | 0,3491 | 0,2114 | 0,2120 |
| Compact encoder, validation | 0,5474 | 0,1639 | 0,0892 | 0,0893 |
| Compact encoder, train OOF | 0,5494 | 0,1582 | 0,0859 | 0,0859 |

Tutti e tre i fold neurali selezionano l'epoca 1. La validation loss migliore e rispettivamente 1,2436, 1,2259 e 1,1944. Tra epoca 1 e 5 la training loss scende, ma la validation loss cresce in ogni fold: e overfitting immediato su 96 identita, non insufficiente capacita del modello. Il modello finale usa quindi una sola epoca, scelta come mediana dei fold.

La v2 esegue inoltre un tiny-overfit deterministico di tre spettri sul T4, con controllo di gradienti finiti: la loss scende da 0,675315 a 0,00001046 in 50 step, rapporto 0,0000155. Questo separa la correttezza implementativa dalla scarsa generalizzazione osservata sul molecule-disjoint.

## 6. Esperimenti E0-E6

Il risultato storico Goal 2 nearest-mass MRR@25 0,7467 resta immutato e riproducibile in EXP-006. Goal 3 non lo sovrascrive: ricostruisce cataloghi con trace controlled/realistic e massa da formula, quindi i valori assoluti E0 sono un nuovo benchmark. Tutti i delta Goal 3 sono calcolati entro lo stesso catalogo, pool, split e scoring.

### Realistic, all validation (32 identita)

Tutti i metodi usano lo stesso pool da 1.000 candidati. Pool recall e Recall@100/1000 sono 1,0000; Recall@25 e 0,8750.

| Esperimento | MRR@25 | Hit@1 | Errori same-formula | Delta vs E0 | IC95% delta |
|---|---:|---:|---:|---:|---:|
| E0 nearest-mass | 0,3750 | 0,2813 | 21 | - | - |
| E1 ranker originale | 0,2029 | 0,1250 | 18 | -0,1721 | [-0,3028; -0,0799] |
| E2 mass + fingerprint | 0,3750 | 0,2813 | 21 | 0,0000 | [0,0000; 0,0000] |
| E3 union + fingerprint | 0,3549 | 0,2500 | 21 | -0,0201 | [-0,0639; -0,0005] |
| E4 LambdaRank completo | 0,3281 | 0,1563 | 23 | -0,0469 | [-0,1136; 0,0118] |
| E5 hard negative same-formula | 0,3299 | 0,1875 | 22 | -0,0450 | [-0,1209; 0,0258] |
| E6 fingerprint-only | 0,0000 | 0,0000 | 13 | -0,3750 | [-0,5322; -0,2494] |
| E6 mass/context | 0,3568 | 0,2500 | 21 | -0,0182 | [-0,0960; 0,0496] |
| E6 spectral-only | 0,3659 | 0,2500 | 21 | -0,0091 | [-0,0762; 0,0515] |

E2 coincide con E0 perche il model-selection sceglie peso fingerprint 0. In E3 il peso selezionato e ancora 0, quindi il risultato misura la retrieval union pura; tutti i pesi fingerprint non nulli sono peggiori sul development split. Fingerprint-only non porta il target nella top-25 in nessuna query.

### Realistic, final congelato (16 identita)

| Esperimento | MRR@25 | Hit@1 | Delta vs E0 | IC95% delta |
|---|---:|---:|---:|---:|
| E0 | 0,4011 | 0,3125 | - | - |
| E1 | 0,2505 | 0,1875 | -0,1506 | [-0,2778; -0,0386] |
| E2 | 0,4011 | 0,3125 | 0,0000 | [0,0000; 0,0000] |
| E3 | 0,3948 | 0,3125 | -0,0062 | [-0,0167; 0,0000] |
| E4 | 0,3679 | 0,1875 | -0,0332 | [-0,1305; 0,0656] |
| E5 | 0,3721 | 0,2500 | -0,0289 | [-0,1329; 0,0898] |

Il final contiene solo 16 identita e gli intervalli di E4/E5 sono ampi, ma non esiste alcun segnale positivo coerente con development/all-validation.

### Controlled

Nel controlled all-validation, E0 ottiene MRR 0,7311; E4 0,7354 e E5 0,7458. I delta +0,0043 e +0,0148 hanno IC95% che attraversano ampiamente zero. Sul final controlled E4 arriva a 0,8229 contro 0,7708 di E0, ma il delta [+0,0521] ha IC95% [-0,0156; 0,1406] e nasce in un catalogo target-informed con quasi nessuna competizione same-formula. Non e evidenza sufficiente per la promozione.

## 7. Diagnosi del peggioramento

### Ranker originale

E1 peggiora E0 in entrambi i protocolli. Nel realistic all-validation, 20/32 query peggiorano, 10 sono invariate e soltanto 2 migliorano. Il delta MRR e significativamente negativo. Il fit contiene 96/96 identita con riferimento spettrale same-identity; l'inferenza molecule-disjoint ne contiene 0/32. Questa e la spiegazione principale del precedente vantaggio nel library holdout e del fallimento disjoint.

La calibration di E1 e degenerata dalla forte imbalance: nel model-selection realistic tutte le 16.000 righe sono nel bin di probabilita [0; 0,1), con probabilita media circa 7,3e-7 e positive rate 0,001. Brier score basso non implica ranking utile; e dominato dai negativi.

Il candidate-prior audit mostra inoltre che tutti i 16 positivi del model-selection provengono da `enveda-180`, mentre i 462 candidati `drug_plus` non contengono positivi. La provenance source non e fornita direttamente al modello, ma source rank e retrieval score ne possono veicolare indirettamente il prior. Nel realistic il positive rate passa da 18,75% al rank 1 a 6,25% nei rank 2-5, 2,19% nei rank 6-25 e 0,013% oltre il rank 25. Questo spiega perche scorciatoie di posizione/massa dominano facilmente una loss per-riga fortemente sbilanciata.

### Drift e importanza

Nel realistic sono flaggate sei feature tra train OOF e model-selection: `fingerprint_log_likelihood`, `fingerprint_soft_jaccard`, `candidate_active_bit_fraction`, `mass_error_ppm`, `abs_precursor_delta` e `retrieval_score`. La fingerprint log-likelihood ha KS 0,307 e PSI 1,333; e il drift piu forte.

L'importanza nativa di E4 assegna molti split alle due feature fingerprint, ma la permutation importance sul validation mette al primo posto `formula_group_size`; permutare diverse feature fingerprint/massa migliora persino la log-loss. Questo e coerente con fitting di shortcut instabili, non con un segnale trasferibile.

### Pool size, formula e difficolta

Nel realistic il target e sempre nel pool da 1.000 e sempre nella top-100, ma e nella top-25 solo per 28/32 query. E0 produce 21/32 errori con un competitor same-formula in top-25; sul final sono 10/16. Nel bin con almeno cinque competitor isomerici, E5 final ottiene MRR circa 0,062, contro valori molto piu alti nei gruppi meno ambigui. L'isomer-aware ranking e quindi rilevante, ma il segnale fingerprint corrente non lo risolve.

## 8. Consumo computazionale

- Ambiente: Kaggle privato, Tesla T4 16 GB, Python 3.13, PyTorch 2.11 CUDA 12.8, LightGBM 4.6, RDKit 2026.03.3, internet disabilitato.
- Parametri compact encoder: 104.481.
- Peak VRAM per fold fingerprint: circa 33,0 MB; massimo process-wide v2 circa 33,8 MB allocati da PyTorch.
- Peak RSS osservato durante i fold: circa 2,14 GB; massimo process-wide circa 2,81 GB.
- Training per fold: 0,50-1,44 s; modello finale: circa 0,16 s.
- Pipeline v2 completa: 632,52 s. La maggior parte del tempo e preprocessing/canonicalizzazione, candidate construction, fingerprint strutturali e bootstrap, non training GPU.
- Precomputazione candidate condivisa: 55,82 s controlled e 370,32 s realistic.
- E1/E4/E5 realistic: circa 1,41/1,91/0,52 s di fit+ranking; gli altri ranker completi sono circa 1,5-2,0 s.

La v2 registra per ogni E0-E6 elapsed time, RSS before/after, massimo RSS osservato e contatori VRAM, oltre alla risorsa condivisa di candidate generation. Nessuna VM a pagamento e stata avviata.

## 9. Decisioni

1. Conservare E0 nearest-mass come baseline primaria.
2. Conservare controlled soltanto come test di ranking condizionato; non usarlo per dichiarazioni end-to-end.
3. Non promuovere E1, E3, E4 o E5: tutti peggiorano realistic all-validation.
4. Non aumentare il modello neurale: il collo di bottiglia e generalizzazione con 96 identita, non capacita.
5. Usare KNN come sanity baseline obbligatoria per ogni nuovo encoder.
6. Migliorare prima la rappresentazione dei candidati, il calibration/bit imbalance e un obiettivo direttamente collegato a MRR o same-formula contrastive ranking.
7. Portare Recall@25 realistico da 0,875 verso Recall@100=1 con reranking mass/formula target-blind prima di modelli forward pesanti.
8. Rimandare ICEBERG/GLACIER: aggiungerli ora confonderebbe il fallimento fingerprint con un nuovo blocco complesso.

## 10. Esperimenti successivi consigliati

1. Espandere il numero di identita train mantenendo invariati manifest final e catalogo realistico; tracciare learning curve a 96, 256, 1.024+ identita.
2. Provare target fingerprint meno sparse o supervisioni ausiliarie gerarchiche; calibrare soglie per bit soltanto su model-selection.
3. Ottimizzare compatibilita/ranking con pairwise same-formula o listwise loss dopo una pretrain BCE, mantenendo predizioni OOF.
4. Testare una rappresentazione candidata learned o count fingerprint e un KNN/linear probe prima di un altro encoder spettrale.
5. Valutare DreaMS congelato come feature soltanto se il linear probe aggiunge delta molecule-disjoint rispetto a KNN.
6. Integrare ICEBERG/GLACIER solo dopo un miglioramento ripetibile del ranking candidati; il ramo novelty rimane separato.

## 11. Verifica dei criteri di completamento

| Criterio | Evidenza |
|---|---|
| Recall@25=1 spiegata | target prioritizzati/iniettati nel controlled; audit per-query |
| Controlled vs realistic | cataloghi, trace e metriche separati |
| Peggioramento ranker diagnosticato | overlap same-identity 96 vs 0, rank shift, drift, importance e calibration |
| Spectrum-to-fingerprint funzionante | PyTorch compact, checkpoint, OOF, forward/backward e tiny-overfit |
| Strategia isomer-aware | E5 LambdaRank con hard negative same-formula/scaffold |
| Ablation quantitative | E0-E6, tre gruppi E6 e pesi E2/E3 |
| Confronto corretto con E0 | stessi pool/split, delta e bootstrap appaiati |
| Test | suite CPU completa e controlli neurali T4 |
| Conclusioni misurate | artifact JSON, manifest, audit e report |
| Prossima priorita | learning curve + obiettivo/rappresentazione fingerprint + top-25 retrieval |

## 12. Riproducibilita e vincoli

Entrypoint locale:

```powershell
.venv\Scripts\python.exe scripts/run_goal3.py --train data/train.parquet --frozen-identities configs/goal3_frozen_identities.txt --output artifacts/goal3 --device cuda
```

Il run autorevole e privato, offline e non effettua submission. Gli artifact Kaggle sono ignorati da Git; decisioni e valori durevoli sono registrati qui e in `docs/EXPERIMENT_LOG.md`.

Verifica locale finale: 111 test passati, 7 skip espliciti per PyTorch assente nella `.venv`, coverage complessiva 78% su 3.625 statement. Le stesse parti neurali opzionali sono state esercitate dal training T4, dai checkpoint e dal tiny-overfit runtime. `compileall` e `git diff --check` passano.

Il lavoro e stato suddiviso fra agente principale e due subagent con ownership disgiunta: audit ranking/validation e spectrum-to-fingerprint. L'integrazione, hard-negative mining, E0-E6 e la decisione finale sono rimasti all'agente principale.
