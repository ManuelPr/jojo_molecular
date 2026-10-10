# CASMI 2026 — Piano implementativo tecnico

Ultimo aggiornamento: 2026-10-10

## 1. Obiettivo e principi

Costruire una pipeline ibrida, riproducibile e leakage-free per massimizzare
MRR@25 e Hit@1, separando candidate coverage, ranking condizionato e novelty.
Ogni componente viene promosso solo con evidenza appaiata su benchmark
realistico; il public leaderboard non è un set di tuning.

Vincoli operativi:

- locale: codice e unit test CPU, nessun training reale;
- Kaggle offline/T4: smoke, esperimenti bounded e inferenza;
- VM grande: solo dopo un go sperimentale, mai avviata automaticamente;
- niente training iniziale di grandi Transformer, DreaMS, ICEBERG o GLACIER;
- nessuna submission senza approvazione esplicita.

## 2. Reference architecture

```text
Parquet MS/MS
  -> schema validation, adduct/neutral-mass correction, peak preprocessing
  -> grouping multi-spectrum per molecule_id
  -> spectral retrieval
       cosine / modified cosine / entropy / shifted / neutral loss
  -> analog propagation
       spectrum analog -> structure analog -> mass transform evidence
  -> candidate generation
       mass/formula indices + curated external catalogs
  -> candidate union + canonicalization + InChIKey14 deduplication
  -> candidate-specific feature store
       mass + fragment + neutral loss + analog + fingerprint + provenance
  -> fingerprint networks / frozen DreaMS probes
  -> isomer-aware learning-to-rank
  -> optional ICEBERG/GLACIER forward spectral scoring
  -> confidence gating + calibrated ensemble / rank fusion
  -> novelty generation branch for catalog misses
  -> validation, top-25 writer, offline Kaggle artifact
```

Le feature spectrum-only sono conservate come descrittori della query. Entrano
nel confronto fra candidati soltanto attraverso una previsione forward, un
analogo associato a una struttura o una regola chimica verificabile.

## 3. Moduli e interfacce

| Modulo | Input | Output / contratto |
|---|---|---|
| Ingest/preprocessing | record Parquet | `ProcessedSpectrum`, masse corrette, provenance |
| Split/leakage | identità, spettri, cataloghi | manifest immutabile e audit fail-closed |
| Spectral evidence | coppie o gruppi di spettri | score, matched peaks, losses, confidence |
| Analog propagation | query, reference library, candidati | feature candidato-specifiche e trace analoghi |
| Candidate catalog | SMILES/formula/source | record canonici, mass/formula index, mmap |
| Candidate generation | neutral mass/formula opzionale | pool ordinato con source e missingness |
| Fingerprint/DreaMS | spettro o struttura | embedding/logit OOF e similarity |
| Ranker | gruppi di candidate feature | ranking top-k e score calibrato |
| Forward scorer | spettro+candidato | compatibilità frammentazione prevista |
| Ensemble/gating | ranking e confidence | ranking unico, fallback deterministico |
| Novelty | spettro/formula/massa | nuove strutture con validità e mass consistency |
| Submission | ranking per molecule_id | CSV esatto, massimo 25 validi/unici |

Tutte le interfacce portano `molecule_id`, `candidate_id`, source, versione del
preprocessing e provenance. Le feature usate dal ranker devono essere
disponibili in inferenza e OOF quando apprese.

## 4. Benchmark e protocolli

Mantenere tre protocolli:

1. library holdout per retrieval same-identity;
2. molecule-disjoint per generalizzazione strutturale;
3. novelty holdout con target fisicamente esclusi dai cataloghi.

Mantenere inoltre due modalità:

- controlled ranking: target garantito nel pool, misura il ranker;
- realistic end-to-end: pool costruito solo da informazioni d'inferenza,
  riferimento principale.

Un final holdout indipendente non viene usato per pesi, feature o soglie.
Metriche obbligatorie: MRR@25, Hit@1/5/10, Recall@25/100/1000, conditional e
oracle MRR, same-formula MRR, delta paired con bootstrap, migliorati/peggiorati,
runtime, RAM/VRAM e costo per molecola.

## 5. Milestone incrementali

### M0 — Contratti, test e riproducibilità

**Priorità:** P0. **Dipendenze:** nessuna. **Hardware:** locale CPU.

- Definire schemi, config `dev/smoke/experiment/kaggle_inference`, seed e
  manifest hash.
- Golden test per addotti, massa neutra, canonicalizzazione e scorer.
- Audit identity/content/candidate/feature provenance fail-closed.

**Completamento:** fixture E2E deterministica, manifest riproducibile, suite
unit verde e nessuna feature target-derived.

### M1 — Benchmark integrity

**Priorità:** P0. **Dipendenze:** M0. **Hardware:** CPU, <32 GB.

- Audit masse, ppm, formule, isomeri, rank truth, addotti, strumenti e numero
  di acquisizioni.
- Spiegare Recall@100 e distinguere injection, prioritization e catalog bias.
- Congelare development e final.

**Completamento:** report per-query, controlled/realistic separati, zero leakage
nel realistic e bootstrap paired operativo.

### M2 — Candidate catalog e indici

**Priorità:** P0. **Dipendenze:** M0–M1. **Hardware:** locale per fixture;
64–128 GB e NVMe per build grandi.

- Canonicalizzazione RDKit e deduplica InChIKey14 con provenance.
- Mass/formula index ordinato, streaming/mmap, fingerprint bit-packed.
- Novelty exclusion prima dell'indicizzazione.
- Tier: current, LIPID MAPS, ChEBI, COCONUT, poi PubChem prefiltrato.

**Completamento:** conteggi e checksum riconciliati, query deterministiche,
curve recall/costo e artifact Kaggle compatti.

### M3 — Spectral retrieval baseline

**Priorità:** P0. **Dipendenze:** M1. **Hardware:** CPU/T4 opzionale.

- Peak matching one-to-one, cosine, modified/shifted cosine, entropy.
- Neutral losses monoisotopiche, fragment coverage e mass accuracy.
- Mean/max/weighted/confidence/RRF multi-spectrum, collision/adduct-aware.
- Fallback nearest-mass.

**Completamento:** metriche sugli stessi dati/preprocessing, unit test
metamorfici, runtime/memoria e CSV tecnico valido.

### M4 — Analog propagation e reranking E0–E7

**Priorità:** P0. **Dipendenze:** M2–M3. **Hardware:** Kaggle CPU/T4, <32 GB.

- Reference retrieval identity/content-disjoint.
- Mass-shift, trasformazioni plausibili, shared fragments, losses, Tanimoto,
  adduct e instrument compatibility.
- Pool top-100 fisso per isolare E0–E7.
- E5 LambdaRank solo con feature train OOF; E6 formula anchor inference-safe;
  E7 confidence gate.

**Completamento:** ablation e CI paired, error transitions, final untouched,
inferenza offline su test ufficiale e nessuna submission.

### M5 — Fingerprint networks

**Priorità:** P1. **Dipendenze:** M4. **Hardware:** T4 16 GB per piccoli run.

- KNN fingerprint come controllo.
- Peak encoder compatto verso Morgan/MACCS con learning curve.
- Hard negative same-formula e obiettivo pairwise/listwise.
- Nessun aumento di scala se il probe non supera KNN/E0.

**Completamento:** Jaccard/F1 e delta ranking OOF positivi e ripetibili; in caso
contrario no-go documentato.

### M6 — DreaMS pretrained

**Priorità:** P1. **Dipendenze:** M4. **Hardware:** T4 frozen; GPU maggiore solo
dopo go.

- Verificare licenza/checkpoint e roster pretraining.
- Estrarre embedding congelati e confrontare retrieval/linear probe con E6.
- Fine-tuning solo dopo delta frozen positivo.

**Completamento:** nessun overlap proibito, artifact offline, incremento paired
o riduzione di costo a qualità equivalente.

### M7 — Isomer-aware forward reranking

**Priorità:** P1/P2. **Dipendenze:** M4–M6. **Hardware:** T4 per probe;
24–48 GB solo dopo approvazione.

- Integrare ICEBERG/GLACIER pretrained su top-N ristretto.
- Confrontare frammenti previsti/osservati con mass/energy/adduct awareness.
- Misurare specificamente same-formula e isomeri costituzionali.

**Completamento:** delta paired sul residuo E6, costo compatibile con Kaggle e
ablation che attribuisce il guadagno allo scorer forward.

### M8 — Ensemble e confidence

**Priorità:** P1. **Dipendenze:** M4–M7.

- Calibrare gating e rank fusion soltanto OOF/development.
- Conservare fallback E0/E6 per segnali rumorosi o mancanti.
- Penalizzare complessità, latenza e failure rate.

**Completamento:** miglioramento stabile su almeno due split, nessun degrado
materiale sui casi high-confidence e trace completa delle decisioni.

### M9 — Novelty generation

**Priorità:** P2. **Dipendenze:** M2, M7–M8. **Hardware:** VM grande solo dopo
approvazione.

- Ramo separato, attivato quando catalog coverage/confidence è bassa.
- Generazione condizionata da spettro, massa e formula; filtri RDKit e dedup.
- Fusione soltanto dopo validità, novelty e mass consistency.

**Completamento:** exact Recall@N addizionale sul novelty holdout, validità,
unicità/diversità e budget risorse documentati.

### M10 — Rehearsal Kaggle e training scalato

**Priorità:** P0 finale. **Dipendenze:** componenti promossi.

- Wheelhouse offline, checksum, loading sequenziale, profiling e resume.
- Benchmark 1/10/100/400 query e validazione completa submission.
- Training scalato su VM solo dopo preflight e approvazione costo/config.

**Completamento:** runtime <70% e RAM/VRAM <80% del limite osservato, artifact
riproducibili, CSV valido; submission resta azione separata.

## 6. Esperimenti e criteri decisionali

Ogni esperimento registra ID, commit/hash source, config, dati, split, seed,
metriche con CI, risorse, runtime e decisione keep/drop/inconclusive.

- Promozione: point estimate positivo e limite inferiore IC95% positivo sulla
  metrica primaria, oppure evidenza coerente predefinita su più split.
- Inconclusive: IC attraversa zero o guadagno solo su un singolo split piccolo.
- Drop: regressione significativa, leakage, mismatch train/inference o costo
  sproporzionato.
- Fra sistemi equivalenti scegliere il più semplice, rapido e piccolo.

## 7. Hardware

| Ambiente | CPU/RAM | GPU | Uso |
|---|---:|---:|---|
| Locale | circa 10 core / 16 GB | nessuna | codice e unit test |
| Kaggle | runtime standard, <32 GB | T4 16 GB | smoke, bounded experiment, inference |
| Build catalogo | 16–32 core / 64–128 GB | non richiesta | streaming index, NVMe 1–2 TB |
| VM training futura | 16–24 core / 128 GB | 1×48 GB consigliata | solo modelli promossi |

Due GPU da 24 GB non equivalgono a 48 GB contigui. Peak RSS, VRAM, artifact
size, candidate generation, reranking e tempo/molecola sono metriche di gate.

## 8. Rischi

- Leakage da identità, contenuto spettrale, pretrained roster o target backstop.
- Canonicalizzazione/versione RDKit diversa dallo scorer.
- Domain shift timsTOF, addotti rari e collision energy.
- Cataloghi grandi: recall maggiore ma ranking più difficile.
- Licenze/provenance di database, codice e checkpoint.
- Overfitting del ranker o del public leaderboard.
- Runtime CPU di forward/analog scoring e artifact Kaggle troppo grandi.
- Novelty non misurabile con sole metriche closed-world.

## 9. Stato raggiunto

Al 2026-10-10 M0–M3 e la parte non neurale di M4 sono completate. Il kernel
Kaggle privato v4 seleziona E6: all-validation MRR@25 0,402011 contro 0,375217
di E0, delta +0,026794 e IC95% [+0,003121; +0,061990]. Il catalogo canonico ha
49.195 strutture; Recall@25/100/1000 è 0,875/1,000/1,000. Il CSV test da 400
righe è valido, non inviato. Goal 5 procede con scaling/indexing analogico,
DreaMS frozen probe e coverage Tier 1; ICEBERG/GLACIER rimangono successivi.

Kaggle CLI 2.2.4 è installata e autenticata via OAuth. Nel runtime Goal 4 non
era disponibile Kaggle MCP, quindi è stata usata la CLI ufficiale. Credenziali
e token non sono registrati nel repository.
