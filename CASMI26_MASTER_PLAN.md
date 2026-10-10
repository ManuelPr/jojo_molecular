# MASTER PROMPT — Enveda CASMI 2026
## Sviluppo autonomo di una soluzione competitiva per l'identificazione molecolare da spettri MS/MS

### 0. Ruolo, obiettivo e modalità di lavoro

Agisci come un team integrato composto da:

- Principal Machine Learning Research Scientist, specializzato in deep learning, representation learning, contrastive learning, metric learning e learning-to-rank.
- Computational Chemist, esperto di spettrometria di massa tandem, frammentazione molecolare, RDKit, metabolomica e identificazione di prodotti naturali.
- Senior Machine Learning Engineer, esperto in PyTorch, ottimizzazione GPU, sistemi di retrieval e pipeline di inferenza.
- MLOps Engineer, esperto in Kaggle, MCP, Docker, GCP, training distribuito, orchestrazione e riproducibilità.
- Kaggle Grandmaster, esperto di strategie competitive, metriche di ranking, validazione, ensemble e prevenzione del leaderboard overfitting.

**Il tuo obiettivo è progettare, implementare, addestrare, validare e portare in submission una soluzione altamente competitiva per la competizione Enveda CASMI 2026.**

Competizione ufficiale:

https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra

Non limitarti a fornire un piano teorico o una spiegazione. Devi realizzare una codebase funzionante e verificata, organizzata per consentire ricerca modellistica iterativa, training su infrastruttura esterna e inferenza su Kaggle.

La priorità assoluta è massimizzare il risultato sulla metrica ufficiale MRR@25, mantenendo una rigorosa validazione scientifica e il rispetto del regolamento.

Non assumere che le architetture qui suggerite siano necessariamente ottimali. Considerale ipotesi di ricerca ad alta priorità, da confrontare sperimentalmente.

Modalità operative:

1. Analizza e verifica prima di implementare.
2. Riutilizza criticamente quanto di valido esiste nei notebook pubblici, invece di reinventare da zero ogni componente.
3. Implementa in modo incrementale, verificando ogni incremento prima di procedere.
4. Distingui sempre i risultati misurati dalle ipotesi.
5. Non inventare performance, risultati sperimentali, risorse disponibili o accessi non verificati.
6. Non interromperti dopo aver scritto una roadmap: procedi con l'implementazione effettiva.
7. Se una risorsa o autorizzazione manca, completa tutto il lavoro indipendente da essa e documenta chiaramente il blocco.
8. Non avviare VM a pagamento né consumare submission ufficiali senza mia approvazione esplicita.
9. Mantieni codice, configurazioni, metriche, log e decisioni tecniche tracciabili.
10. Punta a una soluzione realmente nuova o migliorata, non a un clone di una submission pubblica.

La data finale indicata dalla competizione è il 14 dicembre 2026, salvo modifiche ufficiali. Verifica subito il calendario attuale.

---

# 1. Comprensione della competizione

## 1.1 Problema scientifico

Il task consiste nell'identificare la struttura molecolare 2D di piccole molecole utilizzando i loro spettri di massa tandem MS/MS.

Una molecola viene ionizzata, sottoposta a collisione e frammentata. Lo spettrometro misura i rapporti massa/carica dei frammenti e le loro intensità.

Il modello deve risalire alla struttura chimica che più probabilmente ha generato gli spettri osservati.

Per ogni molecola sconosciuta sono disponibili una o più acquisizioni, potenzialmente con energie di collisione, modalità di ionizzazione e addotti differenti.

**L'unità di predizione è la molecola, non il singolo spettro.**

Tutti gli spettri appartenenti allo stesso `molecule_id` devono contribuire a produrre una sola lista ordinata di strutture candidate.

## 1.2 Dataset

La competizione mette a disposizione approssimativamente:

- 2,5 milioni di spettri MS/MS etichettati.
- 275.000 strutture molecolari distinte nel training.
- Circa 400 molecole nel test nascosto.
- Circa 1.500 spettri nel test, con 1–16 acquisizioni per molecola e una mediana di circa 3.
- Spettri del test acquisiti con strumentazione Bruker timsTOF.
- Masse monoisotopiche del test indicativamente comprese fra 157 e 1.159 Da.

I file principali sono:

- `train.parquet`
- `test.parquet`
- `sample_submission.csv`

Il `test.parquet` scaricabile è un placeholder composto da osservazioni del training. Durante la valutazione il contenuto viene sostituito dal test nascosto.

**Non utilizzare il test placeholder per misurare le performance predittive reali.** Può essere utile per verificare il formato dei dati e il corretto funzionamento tecnico della pipeline.

Tra i campi importanti figurano:

- `molecule_id`
- `spectrum_id`
- `ms2_mzs`
- `ms2_normalized_intensities`
- `precursor_mz`
- `adduct`
- `ionization_mode`
- `collision_energy_ev`
- `instrument_type`
- `base_peak_intensity`

Verifica lo schema completo, i campi specifici del training e le possibili anomalie prima di implementare il preprocessing.

Gli addotti presenti nel test comprendono:

- `[M+H]+`
- `[M+NH4]+`
- `[M-H2O+H]+`
- `[M-2H2O+H]+`
- `[M+Na]+`
- `[M+K]+`
- `[M-H]-`
- `[M-H2O-H]-`
- `[M+CH2O2-H]-`
- `[M+Cl]-`

Implementa una gestione esplicita e verificabile degli addotti, inclusi i casi di perdita neutra, masse esatte, carica e modalità di ionizzazione.

## 1.3 Le tre classi del test

La competizione suddivide concettualmente le molecole in tre classi di difficoltà.

**Classe 1 — Public spectral library**

La struttura della molecola possiede spettri MS/MS di riferimento pubblici.

Strategie rilevanti:

- Exact spectral matching.
- Modified cosine similarity.
- Spectral entropy similarity.
- Adduct-aware matching.
- Analog propagation.
- Spectral embedding retrieval.

**Classe 2 — Known structure, unknown spectrum**

La struttura è presente in database molecolari come PubChem o COCONUT, ma non possiede spettri pubblici.

Strategie rilevanti:

- Candidate retrieval basato sulla massa e sulla formula.
- Spectrum-to-fingerprint prediction.
- Neural structure ranking.
- Simulazione forward degli spettri.
- Molecular graph representation.
- Retrieval supervisionato.

**Classe 3 — Novel structure**

La struttura non è presente in PubChem.

Il semplice retrieval da database non è sufficiente.

Strategie rilevanti:

- Generazione di analoghi strutturali.
- Chemical graph editing.
- Regioisomer generation.
- Molecular formula constrained generation.
- Fragmentation-guided generation.
- De novo structure elucidation.
- Ranking di strutture generate mediante simulazione forward.

La distribuzione delle tre classi nel test è nascosta.

La soluzione deve evitare di ottimizzare soltanto la Classe 1, poiché il risultato finale dipende anche dalla capacità di generalizzare a strutture prive di spettri o completamente nuove.

## 1.4 Metrica ufficiale

La metrica è Mean Reciprocal Rank at 25, MRR@25.

Per ogni molecola si possono proporre al massimo 25 strutture in ordine decrescente di plausibilità.

La formula è:

MRR@25 = mean(1 / rank_first_correct_candidate)

Se la struttura corretta è assente dai primi 25 candidati, il contributo è zero.

Contributi:

- Posizione 1: 1.0.
- Posizione 2: 0.5.
- Posizione 3: 0.333.
- Posizione 5: 0.2.
- Posizione 10: 0.1.
- Posizione 25: 0.04.
- Assente: 0.

La correttezza non viene valutata tramite semplice uguaglianza delle stringhe SMILES.

Le strutture vengono normalizzate usando la canonicalizzazione dei tautomeri di RDKit e successivamente confrontate tramite il primo blocco dell'InChIKey, ossia InChIKey14.

La versione RDKit indicata dalla competizione è `2026.03.3`.

Conseguenze:

- Stereoisomeri equivalenti sotto questa normalizzazione non richiedono ranking separato.
- I tautomeri che collassano nello stesso InChIKey14 non vanno trattati come candidati distinti.
- La deduplicazione deve essere coerente con la metrica ufficiale.
- Gli hard negatives devono essere effettivamente differenti secondo la normalizzazione di scoring.

Implementa una replica verificata della funzione di scoring ufficiale e usala in tutti gli esperimenti.

## 1.5 Submission

L'output è un CSV con colonne:

`molecule_id,smiles`

Ogni `molecule_id` deve apparire una sola volta.

La colonna `smiles` deve contenere fino a 25 candidati separati da punto e virgola, ordinati dal più probabile al meno probabile.

Non sono consentite righe mancanti, identificativi duplicati, campi nulli o più di 25 candidati per molecola.

È una Code Competition: la submission ufficiale deve essere generata tramite esecuzione di un notebook Kaggle.

Verifica le regole attuali prima dell'invio.

I limiti pubblicati includono:

- Fino a cinque submission al giorno.
- Fino a due final submission selezionabili.
- Notebook eseguito con Internet disabilitato.
- Limite di esecuzione GPU indicato di nove ore.

Non assumere che la dotazione GPU sia sempre identica: controlla gli acceleratori effettivamente disponibili per il mio account e per la competizione.

---

# 2. Ricerca approfondita su tutti i notebook Kaggle pubblici

Prima dell'implementazione, effettua una ricognizione sistematica dei notebook disponibili per la competizione.

Non limitarti a leggere i notebook più popolari o i risultati delle ricerche web.

Utilizza:

- Kaggle MCP.
- Kaggle CLI e API ufficiali.
- Pagina Code della competizione.
- Ricerca per competizione, tag, titolo e autore.
- Download del sorgente dei notebook quando consentito.
- Cronologia delle versioni e relativi output.
- Discussion ufficiali.
- GitHub e repository collegati.

Recupera il maggior numero possibile di notebook pubblici accessibili, gestendo correttamente paginazione, versioni, duplicati e notebook derivati.

Per ciascun notebook registra:

1. URL e autore.
2. Versione analizzata.
3. Data della versione.
4. Licenza.
5. Score pubblico, se verificabile.
6. Tempo di esecuzione e acceleratore.
7. Modelli utilizzati.
8. Dataset e checkpoint esterni richiesti.
9. Candidate generation.
10. Feature engineering.
11. Architettura di ranking.
12. Validazione.
13. Tecniche di ensemble.
14. Limiti e debolezze.
15. Idee concretamente riutilizzabili.
16. Disponibilità effettiva del codice sorgente.
17. Differenze rispetto alle versioni precedenti.

Non confondere:

- Score attuale.
- Best score storico.
- Score autodichiarato.
- Risultato locale.
- Risultato riprodotto indipendentemente.

Se un notebook non è accessibile integralmente, registralo come non verificato anziché inventarne l'implementazione.

## 2.1 Notebook prioritari

Studia almeno questi notebook, salvo indisponibilità documentata.

**Analog Propagation — prvsiyan**

https://www.kaggle.com/code/prvsiyan/analog-propagation-casmi-2026-baseline

Approfondisci:

- Mass-shifted analog propagation.
- Adduct-aware spectral matching.
- Candidate pool.
- Modified cosine.
- MetFrag-lite.
- Spectrum-to-fingerprint.
- Calibrated ranking.
- Problemi di candidate cap e recall.
- Validazione ed early stopping.

**Enveda CASMI 2026 — Evgen Dvorkin**

https://www.kaggle.com/code/evgendvorkin/enveda-casmi-2026

Approfondisci:

- Architettura ibrida.
- Modelli fingerprint.
- Database esterni.
- DreaMS.
- Candidate ranking.
- Versioni successive e relativi miglioramenti.

**From Spectra to Structures — Dmitrii Gluzdov**

https://www.kaggle.com/code/dmitriigluzdov/casmi-26-eda-search-model

Approfondisci:

- Validazione identity-disjoint.
- Domain adaptation.
- Knowledge sui prodotti naturali.
- Asset utilizzati.
- Candidate retrieval.
- Risultati riproducibili.

**CASMI26 v4m Inference — Ahmed Berat Özer**

https://www.kaggle.com/code/ahmedberatozer/casmi26-v4m-inference

Approfondisci:

- Fingerprint network.
- Feature engineering.
- Candidate pool.
- Modelli forward.
- Organizzazione dell'inferenza offline.
- Requisiti GPU.
- Tempi di esecuzione.

**Protected Bio-DB Tail — Den Pugovkin**

https://www.kaggle.com/code/denpugovkin/casmi-2026-protected-bio-db-tail

Studia protezione dei library match, database coverage e gestione dei candidati aggiuntivi.

**Next Direct W088 — Jiachen Li**

https://www.kaggle.com/code/llccqq624/casmi26-next-direct-w088

Studia dual ranker, domain shift e combinazione dei modelli.

**Fast Spectral Cosine Baseline**

https://www.kaggle.com/code/haideptry/enveda-casmi-2026-fast-spectral-cosine-baseline

Studia un retrieval economico e riproducibile, utile come baseline.

**Baseline — ektarr**

https://www.kaggle.com/code/ektarr/baseline-enveda-casmi-2026

Usalo come riferimento minimale per verificare il formato della competizione.

## 2.2 Notebook di diagnostica

Analizza anche:

https://www.kaggle.com/code/josefreitasalvesneto/casmi-2026-a-complete-statistical-tour

https://www.kaggle.com/code/dariushafshar/casmi26-your-ppm-window-drops-121-805-spectra

https://www.kaggle.com/code/sharif485/casmi-interactive-data-explorer

Approfondisci in particolare:

- Differenze fra sorgenti degli spettri.
- Numero di picchi per spettro.
- Distribuzione delle intensità.
- Effetto delle soglie di denoising.
- Effetto dei filtri ppm.
- Differenze fra strumenti.
- Domain shift verso timsTOF.
- Frequenza e distribuzione degli addotti.
- Possibili problemi di preprocessing.

Valuta sperimentalmente le soglie relative di intensità, inclusa l'ipotesi di rimuovere picchi inferiori all'1%.

Non assumere che una soglia sia ottimale soltanto perché riduce il divario distributivo tra training e test.

## 2.3 Repository sperimentale aggiuntivo

Studia:

https://github.com/gnshx/Enveda-CASMI-2026---Molecule-ID-From-Mass-Spectra

Contiene una progressione documentata che include:

- Neural fingerprint prediction.
- Analog propagation.
- Two-ranker ensemble.
- PubChem retrieval.
- ICEBERG.
- GLACIER.
- Molecular popularity priors.
- Library match protection.
- PubChem join.

Il repository dichiara una progressione storica da circa 0.145 fino a 0.420 MRR pubblico.

Questi risultati sono autodichiarati dall'autore e non devono essere considerati benchmark controllati senza verifica.

Approfondisci specificamente il miglioramento attribuito a PubChem Join.

Il punto concettuale è importante: i candidati esterni non devono essere inseriti soltanto in posizioni predefinite della lista finale, perché questo impedisce loro di raggiungere la prima posizione.

Devono essere inseriti nel candidate pool principale, arricchiti con feature comparabili e valutati dallo stesso ranker, oppure da un ranker opportunamente calibrato.

Studia inoltre:

- Reciprocal Rank Fusion.
- Union forward rescoring.
- Confidence gating.
- Priors basati su PubChem Substance e PubMed.
- Feature chimiche degli isomeri.
- Differenze fra i ranker.
- Frag rescoring.
- Gestione dei library hit ad alta confidenza.

Non copiare automaticamente iperparametri scelti sul public leaderboard.

## 2.4 Output obbligatorio della ricerca

Produci:

- `docs/competition_analysis.md`
- `docs/notebook_inventory.csv`
- `docs/public_solutions_comparison.md`
- `docs/research_gaps.md`

Il risultato della ricerca deve indicare quali tecniche sono consolidate, quali sono semplici ipotesi e quali esperimenti potrebbero offrire un vantaggio reale rispetto allo stato attuale delle soluzioni pubbliche.

Mantieni aggiornata la ricognizione quando emergono notebook nuovi e rilevanti.

---

# 3. Principio architetturale fondamentale

Non affrontare inizialmente il problema come semplice generazione diretta:

MS/MS -> Transformer -> SMILES.

Il training set, pur grande come numero di spettri, copre un numero molto inferiore di strutture distinte e non garantisce esempi sufficienti per apprendere da zero tutta la chimica di frammentazione.

Il problema deve essere inizialmente affrontato con un'architettura ibrida:

**Spettri -> Preprocessing -> Candidate generation -> Evidence extraction -> Candidate ranking -> Reranking -> Top 25.**

La pipeline dovrà comprendere canali indipendenti e complementari:

1. Library spectral retrieval.
2. Analog propagation.
3. Molecular formula e mass-constrained retrieval.
4. Spectrum-to-fingerprint neural models.
5. Retrieval da grandi database molecolari.
6. Forward fragmentation prediction.
7. Isomer-aware ranking.
8. Novel candidate generation.
9. Ensemble e confidence-aware fusion.

Ogni componente deve essere disattivabile da configurazione, così da misurare il suo contributo reale tramite ablation.

Prima di aumentare la complessità, riproduci una baseline pubblica competitiva.

---

# 4. Preprocessing spettrale e chimico

Implementa un modulo robusto per:

- Lettura streaming e batch da Parquet.
- Raggruppamento per molecola.
- Validazione dei picchi e delle intensità.
- Eliminazione dei valori non finiti.
- Gestione di array vuoti e picchi ripetuti.
- Ordinamento dei picchi.
- Calibrazione e tolleranze ppm.
- Normalizzazione delle intensità.
- Rimozione del rumore.
- Selezione dei picchi.
- Gestione dei picchi vicini al precursore.
- Neutral loss features.
- Adduct correction.
- Conversione precursor m/z -> massa neutra.
- Aggregazione multi-spettro.
- Feature relative alla qualità dell'acquisizione.

La massa neutra deve essere derivata tenendo conto della composizione chimica dell'addotto e della carica.

Non usare una semplice sottrazione della massa del protone per tutti gli addotti.

Presta attenzione a:

- Picchi a bassa intensità potenzialmente informativi.
- Frammenti condivisi da più strutture.
- Perdite di H2O, NH3, CO2 e altre neutral losses.
- Differenze fra energia di collisione alta e bassa.
- Acquisizioni positive e negative.
- Shift introdotti dalla strumentazione.
- Correlazione fra spettri della stessa molecola.

Per il Peak Transformer sperimenta una selezione di 128, 256 e 512 picchi, monitorando l'impatto su performance, VRAM e inferenza.

Evita di rimuovere automaticamente tutti i picchi deboli senza validazione.

---

# 5. Candidate generation

La candidate generation è una delle due componenti più importanti della soluzione.

Il principio è:

**Un ranker perfetto non può selezionare una struttura corretta che non è mai stata inserita nel candidate pool.**

Costruisci e confronta più sorgenti.

## 5.1 Database

Considera:

- Strutture del training Kaggle.
- PubChem.
- COCONUT.
- ChEBI.
- LIPID MAPS.
- Eventuali altre librerie di prodotti naturali con licenza compatibile.

Analizza gli overlap tra database.

Normalizza le strutture e deduplicale secondo la logica della competizione.

Memorizza:

- SMILES originale e normalizzato.
- InChIKey14.
- Formula molecolare.
- Massa monoisotopica.
- Fingerprint.
- Provenienza.
- Eventuali ID nei database.
- Priors e metadati disponibili.
- Informazioni utili alla frammentazione.

Utilizza rappresentazioni efficienti, fingerprint bit-packed e indici su disco.

Non caricare inutilmente milioni di oggetti RDKit in memoria.

## 5.2 Mass and formula retrieval

Implementa:

- Ricerca per massa neutra.
- Indicizzazione per formula.
- Filtri ppm.
- Correzione per addotti.
- Gestione dell'incertezza sulla formula.
- Relaxation dei filtri quando necessario.
- Formula prediction/ranking da MS/MS se utile.

Parti da tolleranze indicative di 5–10 ppm e validale.

Non introdurre filtri talmente stretti da compromettere la candidate recall.

Valuta anche MIST-CF e SIRIUS se i loro modelli, le licenze e i costi d'integrazione sono appropriati.

## 5.3 Spectral library matching

Implementa diversi algoritmi di confronto:

- Standard cosine.
- Modified cosine.
- Spectral entropy similarity.
- Neutral loss matching.
- Precursor-shifted similarity.
- Adduct-shifted matching.
- Embedding similarity.

Utilizza le acquisizioni a energia differente in modo appropriato.

Investiga la possibilità che una molecola ignota sia un analogo della struttura di riferimento, con una piccola modifica di massa.

## 5.4 Analog propagation

Cerca analoghi strutturali utilizzando:

- Similarità degli spettri.
- Differenze di massa.
- Neutral losses condivise.
- Fingerprint chimici.
- Trasformazioni chimiche plausibili.

Considera modifiche strutturali come ossidazione, metilazione, idrossilazione e altre trasformazioni biologicamente plausibili.

Evita di attribuire una trasformazione chimica a una differenza di massa senza ulteriore evidenza.

## 5.5 Neural candidate retrieval

Predici fingerprint molecolari partendo dagli spettri.

Confronta i fingerprint predetti con quelli dei candidati utilizzando:

- Logit-based compatibility.
- Tanimoto e varianti appropriate.
- Similarità supervisionata.
- Reranking neurale.

Sperimenta Morgan/ECFP, MACCS e altre rappresentazioni se aggiungono segnale.

## 5.6 Recall del candidate pool

Per ogni sorgente e ogni unione di sorgenti, misura:

- Candidate Recall@25.
- Candidate Recall@100.
- Candidate Recall@1000.
- Oracle MRR/Hit@1 achievable dal candidate pool.
- Recall per formula.
- Recall su strutture presenti nel training.
- Recall su strutture non presenti nel training.
- Recall su novelty holdout.
- Tempo e memoria necessari.

Non introdurre candidate cap arbitrari senza misurare la perdita di recall.

Sperimenta candidate pool di ampiezza diversa e confronta il trade-off tra recall e costo del reranking.

---

# 6. Modelli neurali

La preferenza tecnologica è PyTorch.

Prima di sviluppare un grande Transformer da zero, valuta backbone già addestrati.

## 6.1 DreaMS

Repository:

https://github.com/pluskal-lab/DreaMS

Analizza:

- Disponibilità dei pesi.
- Architettura.
- Rappresentazione dei picchi.
- Input metadata.
- Embedding pre-addestrati.
- Strategia di fine-tuning.
- Licenza.
- Compatibilità con Kaggle offline.

Confronta almeno:

A. DreaMS frozen, usato come feature extractor.

B. DreaMS con fine-tuning supervisionato.

C. DreaMS più una testa di predizione dei fingerprint.

D. DreaMS più ranking contrastivo.

Non effettuare un fine-tuning completo senza aver prima dimostrato che gli embedding frozen siano insufficienti.

## 6.2 Peak Transformer supervisionato

Implementa un encoder alternativo, con parametri configurabili.

Input potenziali:

- m/z dei frammenti.
- Intensità.
- Massa del precursore.
- Neutral loss.
- Collision energy.
- Adduct.
- Ionization mode.
- Qualità dello spettro.

Utilizza embedding continui o Fourier/sinusoidal per m/z e neutral loss, evitando quantizzazioni eccessivamente grossolane.

Configurazione iniziale indicativa:

- 4–8 Transformer layers.
- Hidden dimension 256–512.
- Numero massimo di picchi 128–256, eventualmente 512.
- Mixed precision.
- Batch size adattato all'hardware.
- Attention efficiente quando compatibile.

Questi valori sono punti di partenza, non requisiti definitivi.

Confronta Transformer e alternative più economiche, incluse convoluzioni o aggregazioni di picchi, se risultano competitive.

## 6.3 Obiettivi di training

Valuta una loss multitask:

L = lambda_fp * L_fingerprint + lambda_contrast * L_InfoNCE + lambda_rank * L_listwise

Dove:

- L_fingerprint può essere Binary Cross Entropy sui fingerprint.
- L_InfoNCE apprende compatibilità tra spettro e rappresentazione molecolare.
- L_listwise ottimizza la discriminazione tra strutture candidate.

Confronta anche:

- Pairwise ranking loss.
- LambdaRank o obiettivi ranking equivalenti.
- Distillation dai modelli forward.
- Auxiliary molecular formula classification.

Non considerare la sola loss di training come indicatore del successo.

Le metriche decisionali sono quelle di retrieval e ranking sulle molecole non viste.

## 6.4 Aggregazione multi-spettro

Non assumere che la media semplice degli embedding sia ottimale.

Confronta:

- Mean pooling.
- Max pooling.
- Weighted mean.
- Attention pooling.
- Gated aggregation.
- Late fusion dei ranking per singolo spettro.
- Reciprocal Rank Fusion.
- Aggregazione condizionata all'energia di collisione.

Possibile formulazione:

score(candidate) = bias(candidate) + sum_k weight_k * score(spectrum_k, candidate)

I pesi possono dipendere da:

- Collision energy.
- Adduct.
- Signal quality.
- Numero di picchi.
- Base peak intensity.
- Confidenza del modello.

La dipendenza tra più acquisizioni della stessa molecola deve essere considerata per evitare confidence score artificialmente elevati.

---

# 7. Ricerca principale: Isomer-Aware Ranking

Questa è una delle priorità scientifiche del progetto.

Diversi sistemi riescono a trovare molecole con massa o formula corretta, ma fanno fatica a distinguere strutture con la stessa formula e connettività diversa.

Uno dei partecipanti ha riportato un'analisi secondo cui, nel proprio holdout, molti errori di ranking fra candidati presenti nel pool riguardavano molecole con la stessa formula.

Non trattare quel risultato come universale: ripeti l'analisi sul nostro sistema.

## 7.1 Hard negative mining

Costruisci gruppi di candidati negativi con difficoltà crescente.

Livello 1:

Molecole con massa o formula diversa.

Livello 2:

Stessa formula, scaffold differente.

Livello 3:

Stessa formula, scaffold simile.

Livello 4:

Regioisomeri o isomeri costituzionali difficili.

Livello 5:

Candidati con struttura simile e spettri simulati estremamente simili.

Non etichettare come hard negative molecole equivalenti secondo l'InChIKey14 normalizzato utilizzato dalla competizione.

Non utilizzare il true candidate come negativo per errore di canonicalizzazione.

## 7.2 Neural pair scorer

Implementa un modello:

score = f(spectrum_embedding, molecular_graph_embedding, chemistry_features)

Valuta:

- Concatenazione di embedding e MLP.
- Cross-attention fra frammenti e rappresentazione molecolare.
- Graph neural network.
- Contrastive dual encoder.
- Cross encoder per i candidati più difficili.

Il dual encoder può essere utile per retrieval veloce, mentre un cross encoder più costoso può essere riservato agli ultimi candidati.

## 7.3 Training listwise

Per ogni spettro o gruppo di spettri, crea una lista contenente:

- Candidato corretto.
- Negativi casuali.
- Negativi della stessa formula.
- Negativi estratti dal ranker corrente.
- Negativi isomerici difficili.

Implementa una loss listwise o una variante di softmax ranking, con temperatura configurabile.

Studia sampling equilibrato, curriculum learning e mining offline/online.

## 7.4 Valutazione

Misura separatamente:

- Rank del candidato corretto.
- MRR condizionata alla presenza nel pool.
- Hit@1 fra candidati della stessa formula.
- Confusione tra isomeri.
- Vantaggio rispetto a LightGBM.
- Robustezza structure-disjoint.
- Effetto sui library match ad alta confidenza.

Il nuovo modello deve superare baseline più economiche a parità di candidate pool.

---

# 8. Forward spectrum prediction: ICEBERG e GLACIER

Repository:

https://github.com/coleygroup/ms-pred

Studia gli approcci forward che partono da uno SMILES e simulano uno spettro MS/MS:

SMILES -> Predicted MS/MS spectrum.

Questa operazione consente di valutare quanto una struttura candidata spieghi uno spettro sperimentale.

## 8.1 ICEBERG

Analizza:

- Checkpoint disponibili.
- Dataset di training originali.
- Modello di frammentazione.
- Intensità predette.
- Metadata richiesti.
- Supporto per addotti.
- Collision energy.
- Costo di inferenza.

## 8.2 GLACIER

Analizza analogamente:

- Predizione della frammentazione.
- Multi-bond breakages.
- Intensità dei frammenti.
- Robustezza su molecole non viste.
- Differenze rispetto a ICEBERG.

## 8.3 Strategia operativa

Non riaddestrare immediatamente ICEBERG o GLACIER.

Parti dai checkpoint pretrained, se licenza e copertura sono idonee.

Implementa un sistema di cascaded reranking.

Esempio iniziale da validare:

1. Retrieval di circa 1.000 candidati.
2. Primo ranking economico.
3. Selezione di circa 100 candidati.
4. Simulazione forward.
5. Calcolo delle feature di confronto.
6. Reranking finale.
7. Output dei migliori 25.

Ottimizza questi numeri sulla candidate recall e sui tempi effettivi.

Feature da valutare:

- Spectral cosine.
- Modified cosine.
- Spectral entropy.
- Peak coverage.
- Fragment mass error.
- Neutral loss coverage.
- Intensità relative.
- Compatibility con collision energy e adduct.
- Score di frammentazione chimica.
- Differenze fra forward models.

Usa un confidence gate.

Per esempio, se un experimental library match ha confidenza molto elevata, evita che uno spettro simulato imperfetto lo penalizzi senza evidenza sufficiente.

I valori di soglia devono essere calibrati localmente.

Valuta feature forward soltanto quando disponibili e affidabili; gestisci missing predictions e addotti non supportati.

Misura il guadagno di ciascun modello separatamente e congiuntamente.

---

# 9. Novel molecule generation — Classe 3

La Classe 3 richiede un canale distinto perché la molecola corretta può essere assente da ogni database.

Non trattare la sola espansione di PubChem come soluzione a questo problema.

Implementa progressivamente:

## 9.1 Analog-derived generation

Partendo da analoghi ad alta somiglianza spettrale:

- Proponi trasformazioni chimiche compatibili con la differenza di massa.
- Genera possibili sostituzioni.
- Esplora regioisomeri.
- Utilizza trasformazioni SMARTS verificabili.
- Controlla valenza e formula.
- Evita strutture chimicamente impossibili.
- Deduplica rispetto ai database.

## 9.2 Formula-constrained structure generation

Se una formula molecolare affidabile è disponibile:

- Vincola la generazione alla formula.
- Penalizza strutture incompatibili con i frammenti.
- Utilizza priors appropriati sui prodotti naturali.
- Confronta gli spettri simulati delle strutture generate.

## 9.3 Modelli generativi neurali

Considera un generatore SMILES/graph condizionato allo spettro soltanto dopo aver verificato:

- Sufficienza dei dati.
- Disponibilità di pretrained chimici.
- Capacità di rispettare la formula.
- Validità e unicità dei candidati.
- Candidate recall aggiuntiva.
- Tempo di esecuzione su Kaggle.

Un Transformer encoder-decoder addestrato da zero non deve essere la prima strategia.

Il generatore deve essere un canale complementare di candidate generation e non sostituire arbitrariamente quelli più affidabili.

---

# 10. Final ranking ed ensemble

Implementa un sistema di fusione delle evidenze.

Considera:

- LightGBM.
- CatBoost.
- HistGradientBoosting.
- Learning-to-rank.
- Calibrated score fusion.
- Reciprocal Rank Fusion.
- Neural reranking.
- Confidence-aware gating.

Il ranker finale può utilizzare:

- Similarità spettrale.
- Analog propagation score.
- Formula compatibility.
- Massa e ppm error.
- Spectrum-to-fingerprint compatibility.
- DreaMS features.
- ICEBERG similarity.
- GLACIER similarity.
- Fragmentation features.
- Molecular descriptors.
- Database source.
- Molecular popularity prior.
- Library match confidence.
- Candidate novelty indicators.
- Isomer-aware score.
- Multi-energy consistency.

Evita feature non disponibili durante il test o che producano leakage.

Valuta se convenga un unico ranker oppure ranker specializzati per tipologia di evidenza.

La tipologia di classe nel test è nascosta: qualsiasi routing deve basarsi su caratteristiche inferibili dallo spettro e dal retrieval, non su etichette oracle.

I candidati provenienti da sorgenti esterne devono poter raggiungere il rank 1.

Non forzarli in posizioni fisse.

Deduplica il risultato finale utilizzando la normalizzazione ufficiale e conserva fino a 25 SMILES validi.

---

# 11. Validazione scientifica rigorosa

Questa sezione è obbligatoria e deve essere implementata prima dei training più costosi.

## 11.1 Leakage prevention

La separazione train/validation non deve avvenire soltanto a livello di singolo spettro.

Una stessa molecola può avere molti spettri.

Se alcuni finiscono nel training e altri nella validation, il modello potrebbe apparentemente generalizzare senza farlo realmente.

Crea split per identità molecolare normalizzata.

Considera anche scaffold split e novelty split.

Quando necessario, elimina dai reference spectra usati dal retrieval le identità molecolari appartenenti all'holdout.

## 11.2 Split richiesti

**Split A — Library holdout**

Simula la presenza di spettri di riferimento, con acquisizioni differenti da quelle da valutare.

Serve per misurare la robustezza del library matching.

**Split B — Structure-disjoint**

Le molecole della validation non devono essere presenti come identità etichettate nel training supervisionato.

Serve per verificare la generalizzazione verso molecole con struttura non vista.

**Split C — Novelty holdout**

Rimuovi le strutture della validation dai candidate pool e dalle reference library utilizzate per il test.

Serve per simulare la necessità di generare strutture esterne al database disponibile.

**Split D — Domain-shift validation**

Utilizza un sottoinsieme comparabile al dominio timsTOF, considerando in particolare la sorgente `enveda-np-examples`.

Questa sorgente comprende circa 250 prodotti naturali acquisiti in condizioni vicine a quelle del test e richiede una gestione accurata degli overlap.

Evita leakage attraverso spettri duplicati, analoghi di training, asset pretrained e metadati di provenienza.

Gli split sono proxy della difficoltà reale e non repliche esatte delle classi nascoste.

## 11.3 Metriche

Registra per ogni esperimento:

- MRR@25.
- Hit@1.
- Hit@5.
- Hit@10.
- Recall@25.
- Candidate pool recall.
- Conditional MRR dato candidate present.
- Oracle ranking score.
- Performance per formula.
- Performance per massa.
- Performance per adduct.
- Performance per collision energy.
- Performance per sorgente.
- Performance su same-formula candidates.
- Performance su structure-disjoint.
- Performance su novelty holdout.
- Performance su domain-shift.
- Runtime.
- RAM peak.
- VRAM peak.
- Dimensione degli artifact.
- Inference time per molecola.

## 11.4 Robustezza statistica

Il test pubblico è relativamente piccolo.

Evita di interpretare ogni oscillazione di 0.001–0.005 come miglioramento reale.

Implementa:

- Bootstrap per molecola.
- Intervalli di confidenza.
- Confronti paired fra modelli.
- Più seed quando appropriato.
- Error analysis delle molecole che migliorano o peggiorano.

Valuta l'affidabilità degli esperimenti prima di attribuire conclusioni scientifiche.

Non utilizzare il public leaderboard come validation principale.

## 11.5 Training dei ranker

Non usare le stesse osservazioni per:

- Addestrare un ranker.
- Scegliere i suoi iperparametri.
- Calibrare l'ensemble.
- Dichiarare il risultato finale.

Utilizza out-of-fold predictions o split separati, secondo necessità.

Presta attenzione agli hard negatives estratti da modelli che potrebbero aver già visto le strutture della validation.

---

# 12. Piano di esperimenti

Organizza gli esperimenti in priorità.

## P0 — Baseline riproducibile

Obiettivo: avere rapidamente una pipeline Kaggle funzionante.

Esperimenti:

- Preprocessing completo.
- Metrica ufficiale.
- Spectral cosine.
- Analog propagation.
- Fingerprint prediction.
- Candidate generation.
- Ranker semplice.
- Inferenza Kaggle offline.
- Prima submission tecnica.

Non passare ai modelli complessi senza una baseline realmente misurata.

## P0 — Validazione

Implementa tutti gli split e le metriche principali.

Misura la candidate recall.

Individua dove il sistema perde più punti.

## P1 — Candidate pool expansion

Sperimenta:

- COCONUT.
- ChEBI.
- LIPID MAPS.
- PubChem.
- Unione e deduplicazione.
- Priors.
- Candidate pool cap differenti.

Misura l'effetto separando candidate recall e ranking.

## P1 — Forward reranking

Aggiungi ICEBERG e GLACIER pretrained.

Confronta:

- Solo ICEBERG.
- Solo GLACIER.
- Entrambi.
- Gating su library match.
- Forward reranking sui candidati unificati.
- Forward reranking limitato agli isomeri difficili.

## P1 — Isomer-Aware Reranker

Implementa:

- Hard negative mining.
- Same-formula sampling.
- Contrastive training.
- Listwise ranking.
- Pair scorer.

Confronta sempre con LightGBM a parità di candidate pool.

## P2 — DreaMS e Transformer

Confronta:

- DreaMS frozen.
- DreaMS fine-tuned.
- Peak Transformer.
- Multi-energy aggregation.
- Spectrum-to-structure contrastive learning.
- Ensemble fra embedding.

## P2 — Ensemble avanzati

Prova:

- Reciprocal Rank Fusion.
- Ranker specialistici.
- Calibrated probabilities.
- Confidence gating.
- Priors chimici.
- Dynamic candidate selection.

## P3 — Novel generation

Implementa una strategia di generazione di analoghi e regioisomeri.

Valutala su novelty holdout.

Considera un generatore neurale solo se l'evidenza sperimentale lo giustifica.

## Gestione degli esperimenti

Per ogni esperimento registra:

- ID univoco.
- Commit Git.
- Configurazione.
- Dataset e loro versioni.
- Split.
- Seed.
- Modello e checkpoint.
- Metrica locale.
- Intervalli di confidenza.
- Risorse utilizzate.
- Runtime.
- Eventuale score pubblico Kaggle.
- Conclusioni.
- Decisione: mantenere, scartare o approfondire.

Utilizza MLflow, oppure un sistema equivalente, evitando dipendenze cloud inutili.

Mantieni una tabella di ablation aggiornata.

Non cambiare contemporaneamente più componenti se questo impedisce di attribuire il miglioramento.

---

# 13. Risorse hardware e strategia di sviluppo

Il sistema deve funzionare con tre ambienti distinti.

## 13.1 Ambiente di sviluppo

Hardware indicativo:

- 32–64 GB RAM.
- GPU NVIDIA da 8–16 GB VRAM, se disponibile.
- CPU ordinaria.
- SSD da 500 GB a 1 TB.

Una Tesla T4 da 16 GB è sufficiente per buona parte del lavoro.

È possibile utilizzare direttamente Kaggle Notebooks come ambiente di sviluppo e test.

Su questa macchina devono funzionare:

- Unit tests.
- Preprocessing.
- Mini training.
- Forward e backward.
- Calcolo della loss.
- Embedding generation.
- Candidate retrieval.
- Ranker CPU.
- Validation.
- Inference.
- Checkpoint loading e saving.

## 13.2 Ambiente di training completo

Configurazione consigliata:

- 128 GB RAM.
- Una GPU da 48 GB VRAM.
- CPU con 16–24 core.
- NVMe almeno 1 TB.
- Linux.
- CUDA/PyTorch compatibili.

Configurazioni alternative:

- 1 GPU da 24 GB per fine-tuning e modelli meno impegnativi.
- 2 GPU da 24 GB o superiori per esperimenti paralleli e determinati training distribuiti.
- GPU 80 GB per modelli molto grandi, se realmente necessaria.

La documentazione di ICEBERG e GLACIER riporta configurazioni di training con due GPU da almeno 24 GB ciascuna per riprodurre gli esperimenti degli autori.

Non assumere che due GPU da 24 GB forniscano automaticamente 48 GB contigui a un singolo processo.

Per modelli distribuiti valuta DDP, FSDP o altre tecniche soltanto se necessarie.

Una macchina con 2–4 GPU, 512 GB RAM e 5 TB di storage sarebbe più che sufficiente, ma non deve essere richiesta senza giustificazione.

Privilegia l'efficienza.

## 13.3 Differenza tra training e inferenza

Un modello può richiedere molta VRAM durante il training a causa di:

- Attivazioni.
- Gradienti.
- Stati dell'optimizer.
- Batch size.
- Buffer temporanei.

La stessa rete può richiedere molta meno VRAM durante l'inferenza.

È dunque accettabile addestrare su 48–80 GB e fare inferenza su 16 GB, purché i pesi e le attivazioni di inferenza entrino realmente in memoria.

Usa:

- `torch.inference_mode()`.
- Batch piccoli.
- FP16 quando appropriato.
- Inferenza sequenziale per i modelli grandi.
- Cache selettiva.
- Precomputazione.
- Chunking.
- Data loading efficiente.

La T4 non supporta nativamente BF16 come le GPU più recenti; verifica precisione numerica e kernel compatibili.

---

# 14. Testare su Kaggle prima del training grande

La strategia di sviluppo desiderata è:

**Sviluppare e verificare su hardware piccolo/Kaggle -> Addestrare sulla VM potente -> Tornare su Kaggle per inferenza e submission.**

Il codice deve essere identico nei diversi ambienti.

Devono cambiare soltanto configurazioni, percorsi di input, batch size e parametri di esecuzione appropriati.

## 14.1 Livello 1 — Unit test CPU

Implementa test per:

- Lettura degli spettri.
- Array di picchi.
- Adduct correction.
- Massa neutra.
- Formula molecolare.
- Fingerprint.
- RDKit.
- Canonicalizzazione dei tautomeri.
- InChIKey14.
- Candidate deduplication.
- Ranking.
- MRR@25.
- Creazione CSV.
- Gestione delle strutture non valide.

## 14.2 Livello 2 — Forward/backward test

Su GPU piccola esegui:

- Forward pass.
- Loss computation.
- Backward pass.
- Optimizer step.
- Gradient check.
- Controllo NaN/Inf.
- Shape assertions.

Verifica tutti i modelli che devono essere addestrati.

## 14.3 Livello 3 — Overfit tiny dataset

Seleziona 32–128 esempi controllati.

Verifica che il modello riesca a memorizzarli quando l'obiettivo lo consente.

Se non ci riesce, investiga loss, target, sampling e gradienti prima di spendere risorse aggiuntive.

## 14.4 Livello 4 — Mini-training end-to-end

Esegui alcune epoche su circa 5.000 spettri, oppure un subset appropriato.

La pipeline deve completare:

- Data loading.
- Training.
- Validation.
- Checkpoint.
- Resume.
- Inferenza.
- Ranking.
- Creazione del CSV.

## 14.5 Livello 5 — Kaggle smoke test

Pubblica una versione completa del notebook Kaggle.

Verifica:

- Import.
- Wheel offline.
- Pesi disponibili.
- Input datasets.
- Inferenza di una o più molecole.
- Produzione di `submission.csv`.
- Compatibilità con GPU T4.
- Internet disabilitato.

Esegui presto una submission tecnica, previo consenso, per verificare il percorso di valutazione nascosto.

## 14.6 Livello 6 — Preflight sulla VM grande

Prima del training definitivo:

- Verifica driver.
- Verifica CUDA.
- Verifica versioni PyTorch.
- Verifica il modello intero.
- Esegui batch alla dimensione definitiva.
- Misura VRAM.
- Misura throughput.
- Controlla DataLoader e worker.
- Salva e ripristina un checkpoint.
- Esegui una breve validazione.
- Verifica che il training riprenda correttamente dopo interruzione.

Solo dopo avvia il training costoso.

## 14.7 Livello 7 — Full inference rehearsal

Dopo il training:

- Carica i pesi su Kaggle.
- Verifica tutto il notebook offline.
- Misura VRAM e RAM.
- Esegui il percorso completo di inferenza.
- Verifica tempi e limiti.
- Esegui controlli finali sul file.
- Procedi alla submission con approvazione.

Non considerare il successo di un mini-training una garanzia assoluta che il training grande sia privo di bug.

---

# 15. Kaggle MCP per Codex

Voglio utilizzare Codex come orchestratore operativo del progetto.

Kaggle mette a disposizione un MCP ufficiale:

https://www.kaggle.com/docs/mcp

Endpoint:

https://www.kaggle.com/mcp

## 15.1 Configurazione

Verifica che Codex supporti la connessione MCP HTTP remota.

La configurazione desiderata per Codex CLI è:

`codex mcp add kaggle --url https://www.kaggle.com/mcp`

Successivamente:

`codex mcp login kaggle`

E verifica:

`codex mcp list`

L'alternativa è aggiungere nel file `~/.codex/config.toml` la sezione `[mcp_servers.kaggle]`, con URL `https://www.kaggle.com/mcp`.

Verifica il flusso OAuth effettivamente supportato.

Se l'accesso non è configurato, guida l'utente nell'autenticazione senza richiedere di copiare password o token in chat, log o repository.

Non esporre le credenziali.

## 15.2 Funzionalità MCP

Esamina gli strumenti effettivamente esposti dal server autenticato.

Utilizza l'MCP, dove supportato, per:

- Esplorare competizioni.
- Recuperare informazioni sui notebook.
- Cercare dataset.
- Consultare risorse.
- Eseguire operazioni disponibili sui notebook.
- Verificare stato e output.
- Esaminare risultati della competizione.

Non presumere che ogni azione sia disponibile via MCP.

Dove una funzione manca, utilizza Kaggle CLI o API ufficiali.

## 15.3 Kaggle CLI

Repository ufficiale:

https://github.com/Kaggle/kaggle-cli

Integra la CLI come fallback e per le procedure automatizzate.

Operazioni richieste:

- Ricerca e download dei dati.
- Pubblicazione dei notebook.
- Controllo dello stato.
- Download dei log.
- Download degli output.
- Gestione di dataset e modelli.
- Submission delle versioni Kaggle.

Esempi di operazioni:

`kaggle kernels push -p kaggle/`

`kaggle kernels status USERNAME/casmi26-test`

`kaggle kernels logs USERNAME/casmi26-test`

`kaggle kernels output USERNAME/casmi26-test -p outputs/`

Per una Code Competition, verifica la versione effettivamente generata e usa il comando di submission con i parametri `-k` per il kernel, `-v` per la versione e `-f` per il file di output.

Un esempio parametrico è:

`kaggle competitions submit enveda-CASMI26-molecule-id-mass-spectra -k USERNAME/casmi26-test -f submission.csv -v VERSION -m "Experiment description"`

Non usare identificativi o versioni inventati.

Verifica la sintassi disponibile nella versione installata.

## 15.4 Automazione del debugging

Il ciclo desiderato è:

1. Codex modifica il codice.
2. Esegue i test locali.
3. Pubblica su Kaggle.
4. Avvia l'esecuzione quando consentito.
5. Recupera stato e log.
6. Identifica errori.
7. Applica correzioni mirate.
8. Ripete i test fino al successo o a un limite ragionevole di tentativi.
9. Registra artifact e risultati.
10. Aggiorna lo stato dell'esperimento.

Distingui:

- Errore di autenticazione.
- Errore di configurazione.
- Errore nel codice.
- CUDA OOM.
- Kernel incompatibile.
- Timeout.
- Dataset mancante.
- Checkpoint mancante.
- Errore nel formato di submission.
- Errore del servizio Kaggle.

Non nascondere errori con retry infiniti.

Implementa timeout, limite dei tentativi e diagnostica leggibile.

---

# 16. Training sulla VM esterna

Il training completo deve essere eseguibile su una VM cloud, preferibilmente GCP se disponibile.

Non assumere che la VM sia già creata o accessibile.

Verifica prima:

- Project.
- Regione e zona.
- GPU e VRAM.
- Quota disponibile.
- Disco.
- RAM.
- Driver.
- Costo stimato.
- Credenziali.
- Permessi.

Usa SSH, gcloud CLI o API cloud per le operazioni realmente disponibili.

## 16.1 Esecuzione

Il training deve essere un processo persistente, indipendente dalla sessione interattiva di Codex.

Considera:

- Job scheduler.
- tmux/systemd.
- Docker.
- Job cloud gestito.
- Checkpoint periodici.
- Logging strutturato.

Non dipendere dalla sopravvivenza di una singola shell.

## 16.2 Artifact

Produci:

- Checkpoint di training.
- Checkpoint finali per inferenza.
- Configurazione.
- Versione codice.
- Metriche.
- Manifest delle dipendenze.
- Hash dei file.
- Metadata del training.
- Eventuali embedding precalcolati.

Preferisci `safetensors` per i pesi, ove compatibile.

Evita deserializzazione non sicura di checkpoint di provenienza sconosciuta.

## 16.3 Trasferimento verso Kaggle

I pesi addestrati esternamente devono essere trasferiti a Kaggle come Dataset, Model o altro artifact consentito.

Il notebook finale deve poterli leggere senza connessione Internet.

Prevedi:

- Upload.
- Versioning.
- Validazione checksum.
- Compatibilità del caricamento.
- Verifica della dimensione.
- Test del path Kaggle.

Non ricostruire grandi database durante la submission se possono essere precalcolati legalmente prima.

## 16.4 Gestione dei costi

Codex non deve avviare risorse a pagamento senza approvazione.

Prima del training costoso deve comunicare:

- Configurazione richiesta.
- Motivo della scelta.
- Stima del costo.
- Durata stimata come parametro di budget, non promessa di completamento.
- Piano di checkpoint.
- Criteri di arresto.
- Possibilità di ripresa.

Quando il job termina, la macchina deve essere arrestata secondo un meccanismo affidabile.

---

# 17. Inferenza finale su Kaggle

Questa è una restrizione progettuale fondamentale.

La pipeline finale deve funzionare nell'ambiente effettivamente assegnato dalla competizione, con Internet disabilitato.

La configurazione T4 x2, se disponibile, offre 16 GB di VRAM separati per GPU.

Non progettare un modello che richieda necessariamente una singola allocazione superiore ai 16 GB senza una tecnica di partizionamento esplicitamente testata.

Obiettivo iniziale:

**Rendere l'intera inferenza eseguibile su una T4 da 16 GB, utilizzando la seconda GPU come accelerazione opzionale.**

Per riuscirci:

- Usa FP16 dove supportato.
- Riduci batch size.
- Usa `torch.inference_mode()`.
- Esegui i modelli neurali sequenzialmente se necessario.
- Evita di caricare contemporaneamente modelli forward molto pesanti.
- Usa feature precalcolate.
- Mantieni gli indici compatti.
- Leggi dal disco selettivamente.
- Elimina gli oggetti GPU non più necessari.
- Utilizza la CPU per RDKit e LightGBM quando appropriato.
- Minimizza serializzazioni e copie di grandi array.

Non è obbligatorio addestrare e inferire sulla stessa GPU.

È obbligatorio verificare empiricamente che i checkpoint della VM siano compatibili con Kaggle.

Effettua benchmark su:

- 1 molecola.
- 10 molecole.
- 100 molecole.
- Tutto il test placeholder.
- Un workload sintetico rappresentativo, quando utile.

Misura:

- Peak RAM.
- Peak VRAM.
- Tempo per componente.
- Tempo per molecola.
- Tempo totale stimato.
- Caricamento dei modelli.
- Costi di candidate retrieval.
- Costi ICEBERG/GLACIER.

Il test nascosto può differire dal placeholder: mantieni un margine di sicurezza rispetto alle nove ore.

---

# 18. Struttura della codebase

Utilizza una struttura modulare, indicativamente:

- `configs/`
  - Configurazioni dev, smoke, full train e Kaggle inference.
- `data/`
  - Raw.
  - Processed.
  - External metadata.
- `src/spectra/`
  - Preprocessing.
  - Similarity.
  - Adducts.
  - Multi-spectrum aggregation.
- `src/chemistry/`
  - Canonicalization.
  - Molecular formula.
  - Fragmentation.
  - Molecular descriptors.
- `src/retrieval/`
  - Library search.
  - Analog search.
  - Candidate databases.
  - Candidate union.
- `src/models/`
  - Peak Transformer.
  - DreaMS adapter.
  - Fingerprint network.
  - Isomer ranker.
  - Forward scorer.
- `src/ranking/`
  - Feature generation.
  - LightGBM/CatBoost training.
  - Calibration.
  - Ensemble.
- `src/validation/`
  - Splits.
  - Metrics.
  - Leakage checks.
  - Ablations.
  - Diagnostics.
- `scripts/`
  - Dataset preparation.
  - Training.
  - Evaluation.
  - Benchmarking.
  - Artifact export.
- `kaggle/`
  - Notebook/script.
  - Kernel metadata.
  - Submission validation.
- `tests/`
  - Unit.
  - Integration.
  - GPU.
  - Kaggle smoke.
- `docs/`
  - Research.
  - Experiments.
  - Results.
  - Architecture.
- `artifacts/`
  - Manifest e riferimenti agli artifact, evitando commit di file enormi.

Tecnologie preferite:

- Python 3.11 quando compatibile.
- PyTorch.
- RDKit.
- NumPy.
- Polars/PyArrow.
- LightGBM/CatBoost.
- Numba per ottimizzazioni numeriche.
- Hydra oppure configurazioni YAML equivalenti.
- Pytest.
- MLflow.
- Git.
- Docker per gli ambienti controllati.

Non introdurre framework aggiuntivi se non hanno una funzione concreta.

Mantieni una separazione rigorosa tra codice di ricerca, training e inferenza.

La pipeline Kaggle non deve richiedere il codice e le dipendenze di training non necessari.

---

# 19. Reproducibility, qualità e gestione dei bug

Implementa:

- Random seed controllati.
- Versioni bloccate delle dipendenze.
- Manifest dei dati.
- Commit Git in ogni esperimento.
- Configurazioni serializzate.
- Checkpoint versionati.
- Logging dei parametri.
- Monitoraggio delle risorse.
- Resume training.
- Test di serializzazione.
- Test di compatibilità CUDA.
- Test di precisione FP16.
- Test di output deterministico dove realistico.
- Confronto CPU/GPU su piccoli casi.
- Test su batch incompleti.
- Test su input problematici.
- Test di memoria.
- Test di inferenza offline.

Implementa controlli fail-fast.

Non consentire che un training continui silenziosamente quando:

- La loss è NaN.
- I gradienti sono invalidi.
- Mancano feature essenziali.
- Lo split contiene leakage.
- Il candidate pool è vuoto inaspettatamente.
- La canonicalizzazione fallisce sistematicamente.
- Il checkpoint non è ripristinabile.

Produci messaggi di errore diagnostici.

Non considerare la semplice esecuzione del codice come prova della correttezza statistica o scientifica.

---

# 20. Configurazioni di sviluppo e training

Predisponi almeno queste configurazioni.

## dev

- Dataset: subset di circa 5.000 spettri.
- Batch size iniziale: 4.
- Epoche iniziali: 3.
- Workers: 2.
- Precisione: FP16 mixed precision, se supportata.
- GPU: T4 da 16 GB.
- Logging dettagliato.
- Salvataggio checkpoint.
- Test rapidi.

## smoke

- Dataset: 32–128 esempi.
- Batch molto piccolo.
- Forward/backward.
- Overfit test.
- Checkpoint.
- Inferenza.
- Submission formatting.

## train

- Dataset completo.
- Batch size iniziale indicativo: 64, da adattare alla memoria.
- Epoche iniziali indicative: massimo 50 con early stopping, se appropriato.
- Workers: 8, da adattare.
- Gradient accumulation configurabile.
- Mixed precision.
- Checkpoint periodici.
- Validazione molecule-disjoint.
- Monitoraggio risorse.
- Resume automatico controllato.

## kaggle_inference

- No optimizer.
- No gradient computation.
- Internet off.
- T4-compatible.
- Modelli caricati da artifact.
- Candidate index offline.
- Output ufficiale.
- Profiling.
- Memory management.

L'architettura di un modello deve rimanere identica tra mini-training e training completo quando lo scopo è verificare la correttezza dello stesso codice.

Non ridurre arbitrariamente layer o hidden dimension nei test per poi dichiarare verificato un modello più grande non testato.

---

# 21. AGENTS.md e automazione Codex

Crea un file `AGENTS.md` contenente le regole operative permanenti del progetto.

Deve specificare:

- Obiettivo della competizione.
- Fonti ufficiali.
- Priorità della validazione.
- Comandi per test locali.
- Comandi Kaggle.
- Procedure per la VM.
- Checkpoint.
- Naming degli esperimenti.
- Criteri di successo.
- Limiti di costo.
- Limiti delle submission.
- Politiche su token e credenziali.
- Divieto di inventare risultati.
- Politiche di sicurezza sui dati.
- Regole di riproducibilità.

Codex deve poter continuare lo sviluppo in sessioni successive senza perdere lo stato del progetto.

Mantieni:

- `docs/PROJECT_STATE.md`
- `docs/EXPERIMENT_LOG.md`
- `docs/NEXT_STEPS.md`
- `docs/DECISIONS.md`

Aggiornali dopo ogni fase sostanziale.

Prevedi script ripetibili per i workflow frequenti invece di affidarti esclusivamente all'esecuzione manuale di comandi da parte dell'agente.

---

# 22. Sequenza operativa richiesta

Segui questo ordine, adattandolo soltanto quando emergono evidenze tecniche solide.

### Fase A — Discovery

- Verifica regole e dati ufficiali.
- Configura Kaggle MCP.
- Verifica Kaggle CLI.
- Esplora notebook e repository.
- Analizza i metodi pubblici.
- Identifica baseline e lacune tecniche.
- Definisci metriche e split.

Deliverable: report completo della competizione e inventario degli approcci.

### Fase B — Baseline

- Implementa preprocessing.
- Implementa metrica ufficiale.
- Implementa spectral retrieval.
- Implementa candidate generation.
- Implementa ranker iniziale.
- Esegui test CPU/GPU.
- Verifica il notebook Kaggle.
- Produci una submission tecnica valida con approvazione.

Deliverable: pipeline end-to-end riproducibile.

### Fase C — Diagnostica e candidate coverage

- Misura candidate recall.
- Analizza gli errori.
- Valuta PubChem/COCONUT/ChEBI/LIPID MAPS.
- Ottimizza gli indici.
- Verifica la generalizzazione.
- Identifica i veri colli di bottiglia.

Deliverable: baseline ottimizzata con ablation.

### Fase D — Forward models

- Integra ICEBERG pretrained.
- Integra GLACIER pretrained.
- Implementa forward scoring.
- Implementa gating.
- Verifica l'inferenza T4.
- Misura il guadagno reale.

Deliverable: pipeline con forward reranking.

### Fase E — Ricerca neurale

- Implementa fingerprint network.
- Valuta DreaMS.
- Implementa Peak Transformer.
- Costruisci hard negatives.
- Addestra un Isomer-Aware Ranker.
- Esegui contrastive/listwise experiments.
- Valuta multi-spectrum aggregation.

Deliverable: modelli neurali verificati, con confronto quantitativo.

### Fase F — Training grande

- Prepara artifact e dataset.
- Verifica risorse VM.
- Esegui preflight.
- Richiedi approvazione sul costo.
- Avvia training persistente.
- Salva checkpoint.
- Registra metriche.
- Esporta i modelli.

Deliverable: checkpoint di training e inferenza riproducibili.

### Fase G — Ensemble e novelty

- Integra i migliori modelli.
- Ottimizza ranking e fusione.
- Implementa generazione di analoghi.
- Valida su novelty holdout.
- Esegui ablation finale.
- Seleziona le componenti che aggiungono valore.

Deliverable: soluzione integrata competitiva.

### Fase H — Kaggle submission

- Prepara artifact offline.
- Carica su Kaggle.
- Verifica la compatibilità.
- Esegui profiling completo.
- Rispetta i limiti hardware.
- Valida `submission.csv`.
- Richiedi approvazione alla submission.
- Invia il notebook.
- Registra il punteggio e la versione.

Deliverable: submission ufficiale funzionante.

---

# 23. Criteri di successo

Non considerare il progetto completato perché il codice esiste.

La soluzione deve soddisfare tutti questi criteri tecnici:

**Correttezza**

- Metrica replicata fedelmente.
- Test automatici superati.
- Nessun leakage identificato negli split utilizzati.
- Candidate deduplication corretta.
- Submission valida.
- Checkpoint ripristinabili.

**Riproducibilità**

- Ambiente documentato.
- Dipendenze versionate.
- Configurazioni riproducibili.
- Seed e commit registrati.
- Artefatti identificabili.

**Qualità modellistica**

- Baseline pubblica riprodotta o differenze spiegate.
- Candidate recall misurata.
- Ranker valutati a parità di candidate pool.
- Ablation disponibili.
- Miglioramenti sostenuti da evidenza locale.
- Robustezza a structure novelty e domain shift.

**Efficienza**

- Training eseguibile sulla VM designata.
- Inferenza eseguibile su Kaggle.
- Rispetto dei limiti di RAM, VRAM e runtime.
- Nessun download Internet richiesto durante il test nascosto.
- Nessuna dipendenza da servizi esterni durante la submission.

**Competitività**

- MRR@25 superiore alla baseline di partenza sui validation split rilevanti.
- Buona candidate coverage.
- Buon comportamento sugli isomeri.
- Miglioramento documentato del ranking.
- Capacità aggiuntiva sulle strutture novel, se supportata dagli esperimenti.

La qualità va misurata principalmente attraverso la validazione locale.

Il public leaderboard è una verifica aggiuntiva, non la principale fonte di ottimizzazione.

Non fissare target numerici arbitrari come prova del successo; usa il confronto con gli approcci pubblici e con i risultati riproducibili.

---

# 24. Vincoli scientifici, etici e regolamentari

Consulta direttamente:

https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra/rules

https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra/overview

https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra/data

Verifica sempre:

- Regole sul training esterno.
- Utilizzo di dati esterni.
- Licenze di codice e modelli.
- Restrizioni sulla condivisione privata.
- Requisiti di open source per i vincitori.
- Eventuali eccezioni previste per pretrained models e dati di terze parti.
- Limiti di submission.
- Scadenze.
- Risorse GPU consentite.
- Regole di riproducibilità.

Non utilizzare etichette del test nascosto, informazioni ottenute con leakage o annotazioni vietate.

Non includere nel training informazioni sulla soluzione del test che non siano consentite.

---

# 25. Comportamento autonomo richiesto

Voglio che tu lavori come un ricercatore e ingegnere senior, non come un esecutore che si limita a seguire una checklist.

Devi:

- Formulare ipotesi.
- Leggere codice e documentazione.
- Criticare soluzioni pubbliche.
- Proporre esperimenti.
- Implementarli.
- Verificarli.
- Misurarne i risultati.
- Interpretare gli errori.
- Prendere decisioni tecniche motivate.
- Eliminare approcci inefficaci.
- Migliorare progressivamente la pipeline.

Non inseguire esclusivamente la complessità modellistica.

Se una soluzione basata su retrieval e LightGBM supera un grande Transformer, privilegia la soluzione migliore.

Se un nuovo modello aumenta il costo senza migliorare il ranking, documentalo e scartalo.

Se il principale collo di bottiglia è la candidate recall, concentrati su quello prima di sviluppare altri ranker.

Se il collo di bottiglia sono gli isomeri, concentra la ricerca su forward simulation, fragmentation evidence e hard-negative learning.

Se il problema principale è il domain shift verso timsTOF, investi in data adaptation, preprocessing e calibration.

Se una nuova soluzione migliora soltanto il public leaderboard ma peggiora validation robuste, considera il rischio di overfitting.

Non inventare risultati sperimentali.

Non nascondere errori.

Non fermarti a una spiegazione generale.

Non utilizzare costose risorse cloud senza autorizzazione.

Non sprecare submission per verifiche che possono essere effettuate localmente.

---

# 26. Primo incarico immediato

Inizia adesso con le seguenti attività, nell'ordine:

1. Ispeziona il repository di lavoro esistente, se presente, e preservane codice e modifiche.
2. Verifica che la competizione sia ancora attiva e controlla regolamento, dataset, metrica e submission.
3. Verifica la connessione Kaggle MCP e la Kaggle CLI.
4. Se manca l'autenticazione, documenta la procedura necessaria e prosegui con tutto il lavoro pubblico accessibile.
5. Recupera e analizza sistematicamente i notebook pubblici rilevanti, inclusi quelli elencati in questo prompt.
6. Studia in particolare Analog Propagation, le pipeline più recenti di fingerprint/ranking, PubChem Join, ICEBERG e GLACIER.
7. Crea una codebase professionale con configurazioni, test e documentazione.
8. Implementa la metrica ufficiale e la canonicalizzazione RDKit.
9. Definisci split e controlli di leakage.
10. Implementa una prima baseline end-to-end e testala su un subset locale.
11. Se l'accesso Kaggle lo consente, esegui il primo smoke test del notebook.
12. Documenta i risultati effettivi e le opportunità di miglioramento.
13. Prosegui in modo incrementale con gli esperimenti a maggiore valore atteso.

La ricerca iniziale non deve bloccare indefinitamente lo sviluppo: una volta raccolte evidenze sufficienti, implementa e misura.

Prepara il progetto in modo tale che l'intero workflow possa essere orchestrato da Codex tramite Kaggle MCP, Kaggle CLI e strumenti di gestione della VM.

## Risultato atteso

Voglio ottenere una soluzione per Enveda CASMI 2026 che:

- Sia scientificamente motivata.
- Sfrutti criticamente lo stato dell'arte.
- Utilizzi bene i dati disponibili.
- Distingua correttamente retrieval, candidate generation e ranking.
- Si concentri sui veri errori, soprattutto la confusione fra isomeri e la candidate coverage.
- Possa essere sviluppata e verificata su hardware economico.
- Possa essere addestrata su una VM GPU potente.
- Possa essere eseguita offline su Kaggle.
- Sia riproducibile.
- Sia automaticamente testabile e monitorabile.
- Sia progettata per massimizzare la MRR@25 e competere seriamente per le prime posizioni.

**Procedi con il lavoro effettivo. Pianifica quanto necessario, poi implementa, testa, misura e migliora.**
