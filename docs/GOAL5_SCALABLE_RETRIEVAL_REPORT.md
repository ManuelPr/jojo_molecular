# Goal 5 — Scalable analog retrieval and domain adaptation

## Checkpoint operativo — 2026-10-12

**Stato: IN CORSO.** Il codice, i contratti di leakage e l'indice C1 sono
implementati, ma non esistono ancora metriche scientifiche complete E7–E12 sul
cohort domain-matched. Il Goal 5 non è quindi dichiarato concluso e il Goal 6
non è iniziato.

Il solo job attivo al checkpoint è il kernel privato
`mperni/casmi26-goal5-scalable-retrieval`, versione 4. È partito il
2026-10-12 alle 11:22:34 UTC (13:22:34 Europe/Rome) e alle 15:31:34 locali era
ancora `RUNNING`, con **2 h 09 min 00,6 s** di wall time. Kaggle non espone log
parziali del kernel in esecuzione; non è quindi possibile attestare la fase
raggiunta. Il job non era ancora oltre il precedente punto di errore di v3
(2 h 50 min 55 s) e non viene classificato come bloccato al checkpoint.

Non sono stati avviati nuovi run. Se v4 resta `RUNNING` oltre 4 ore senza un
artifact terminale, va proposta l'interruzione; non deve superare 8 ore per
questa classe di benchmark. Prima di una cancellazione vanno salvati stato CLI,
versione del kernel e, se Kaggle li rende disponibili, log e output parziali.
Queste soglie sono stop-rule operative, non una previsione del runtime.

## Executive summary

Goal 5 preserves Goal 4 E6 byte-for-byte as the submission baseline and adds a
separate scalable experiment path.  It does not retrain a neural model and does
not perform an official submission.

The delivered architecture consists of:

1. a full-train C1 structural catalog built by streaming metadata;
2. a checksummed memory-mapped mass/formula index;
3. an exact sorted-mass prefilter for expensive analog spectral scoring;
4. dynamic candidate pools with mass fallback and staged reranking;
5. an instrument-matched `enveda-np-examples` validation with independent A/B/C
   visibility conditions and a sealed stage;
6. a frozen DreaMS adapter and a documented environment-based NO-RUN decision;
7. a private offline Kaggle runner that also regenerates, but never submits,
   the frozen E6 CSV.

## Frozen E6 gate

Baseline commit: `04a6a89ae7fc6c32d4a65f6f63450864f5a00abc`.

The Goal 4 v3 and v4 artifacts have an identical selection-critical signature:

| Quantity | Frozen value |
|---|---:|
| Source catalog | 49,620 |
| Canonical C0 | 49,195 |
| Selected model | E6 |
| Analog feature | `analog_score` |
| Evidence weight | 0.5 |
| All-validation E0 MRR@25 | 0.3752173584 |
| All-validation E6 MRR@25 | 0.4020109048 |
| Paired delta | +0.0267935464 |
| 95% bootstrap interval | [0.0031211670, 0.0619899892] |
| Final E0 → E6 | 0.4013307571 → 0.4385488022 |

Dataset, manifest, result and submission hashes are frozen in
`configs/goal5_e6_frozen.yaml`.  `verify_goal5_baseline.py` rejects any change
to the split, selected aggregation, weight or E0/E6 metric signature.  The new
code never modifies Goal 4 experiment files.

## Architecture

### Structural catalog and candidate retrieval

The C1 builder reads only structure columns from Parquet, groups repeated
spectra by identity, canonicalizes with RDKit 2026.03.3 and emits explicit
reject/conflict/provenance counters.  The index stores sorted mass arrays,
formula postings and variable text in compact offset-addressed blobs.  Every
array is hashed and can be reopened with memory mapping.

Dynamic retrieval expands exact windows through 5, 10, 20 and 50 ppm.  If the
requested pool is still sparse, nearest mass fills it.  An uncertain formula is
only an annotation; it never removes the mass fallback.  The first mass
candidate is retained as the E6 anchor even after channel fusion.

### Scalable analog retrieval

Goal 4 compared every query with each in-memory reference.  Goal 5 sorts
reference spectra by neutral mass and applies an exact `searchsorted` window
before the unchanged modified-cosine/entropy/neutral-loss scorer.  It audits the
entire library against forbidden identities and content hashes before querying,
so an out-of-window leak cannot pass unnoticed.

On identical references, window and policy, unit tests prove that analog IDs,
order and similarity values equal the Goal 4 brute-force result.  The report
records total references, window references, actually scored references,
reduction fraction and elapsed time per query.

### Ranking

No new learned ranker is trained.  The Goal 4 E6 rule is held fixed:

- feature `analog_score`;
- weight 0.5;
- analog evidence can reorder only candidates sharing the nearest-mass
  candidate's formula;
- only the first 100 candidates receive expensive structural/analog scoring in
  staged variants; unscored candidates remain in the pool in mass order.

This isolates catalog and retrieval effects from model-capacity changes.

## Experiments

| ID | Catalog / retrieval | Ranking |
|---|---|---|
| E7 | C0, legacy brute nearest mass, top 100 | frozen E6 control |
| E8 | C1, legacy brute nearest mass, top 100 | frozen E6 |
| E9 | C1, exact indexed nearest mass, top 100 | frozen E6; must equal E8 |
| E10 | C1, dynamic pool up to 1,000 | E6 on bounded expensive head |
| E11 | not run | no verified inference-safe database prior |
| E12 | C1 mass + reference-analog RRF union | frozen E6 with mass anchor |

All variants are fixed before opening the sealed domain stage.  E8/E9 ordered
candidate equality is a runtime assertion, not a tolerance-based metric.

## Evaluation contract

For every stage and A/B/C condition the artifact reports:

- Candidate Recall@25/100/1000 and full-pool recall;
- MRR@25, Hit@1/5/10 and Conditional MRR;
- Oracle MRR, equal to the candidate-generation ceiling;
- same-formula error count and formula/mass/adduct/instrument breakdowns;
- molecule-level paired bootstrap versus E7;
- improved, unchanged and worsened query counts;
- retrieval time, ranking time, candidate rows and index size;
- analog-window reduction per query.

Comparisons with different catalogs use a common union pool for the paired rank
statistics.  Coverage is always reported separately; a target recovered only
by C1 is not misrepresented as a ranking improvement.

## Software verification

The complete local suite after integration passes: **204 passed, 7 skipped**.
The seven skips are the existing PyTorch tests in the intentionally lightweight
local environment.  New coverage includes:

- frozen E6 signature and artifact hashes;
- domain A/B/C membership, sealing and deliberate leakage mutations;
- streaming C1 construction, provenance and holdout exclusion;
- checksummed mmap index and tamper failure;
- brute/index retrieval equality;
- analog-index equivalence and whole-library leakage audit;
- dynamic pools, mass fallback, channel union, cache and staged ranking;
- DreaMS embedding validation, identity exclusion and aggregation;
- integrated E7–E12 behavior on synthetic domain data.

`compileall` and `git diff --check` pass.  No official submission API is present
in the Goal 5 runner.

## DreaMS

DreaMS was not scientifically evaluated.  The adapter is ready, but the
official environment pins Python 3.11, PyTorch 2.2.1, NumPy 1.25, PyArrow 15 and
RDKit 2023.9.6, while the verified offline competition runtime is Python 3.13
with RDKit 2026.03.3.  The official embedding checkpoint is 1.24 GB and is not
in the offline assets.  Relaxing dependencies inside the scoring environment
would invalidate reproducibility and canonicalization parity.

This is an environment NO-RUN, not a model NO-GO.  The isolated probe protocol
and promotion criteria are in `DREAMS_FROZEN_PROBE.md`.

## Submission state

The selected official-submission candidate remains frozen E6 until Goal 5
sealed results justify promotion.  The private runner regenerates a 400-row CSV
with at most 25 valid unique candidates per molecule and records runtime and
hashes.  It never calls the Kaggle submission endpoint.  Public score therefore
remains `NOT SUBMITTED / N.A.` pending explicit user approval.

## Goal 6 decision rule

- If B has high C1 recall but same-formula MRR remains weak, prioritize a
  forward-spectrum reranker such as pretrained ICEBERG/GLACIER.
- If B recall rises materially from C0 to C1 but remains the dominant ceiling,
  prioritize C2 (COCONUT) and formula-conditioned retrieval.
- If indexed analog evidence helps robustly in B, first scale and embed the
  spectral reference library, then run isolated DreaMS.
- If the domain cohort remains poorly calibrated to test diagnostics, prioritize
  timsTOF adaptation and acquisition-matched validation.

The final choice is made from sealed quantitative evidence, not from roadmap
order.

## Evidenza quantitativa disponibile al checkpoint

| Evidenza | Valore verificato |
|---|---:|
| Baseline congelata E6, MRR@25 all-validation Goal 4 | 0.4020109048 |
| E0 nearest-mass, stesso benchmark | 0.3752173584 |
| Delta paired E6−E0 | +0.0267935464 |
| IC95% bootstrap del delta | [0.0031211670, 0.0619899892] |
| C1 canonical structures | 271,439 |
| Formule C1 uniche | 50,662 |
| Dimensione array indice C1 | 34,821,876 byte |
| Identità domain-matched eleggibili | 234 |
| Identità development / sealed | 188 / 46 |
| Spettri query domain-matched | 1,097 |
| Reference dopo cap v3/v4, prima delle mask A/B/C | 2,932 |

Il commitment del sealed holdout è
`a1aa831fe34de659c58c1f3e3aba746525297d6a960b149402f7db9dc9e0e959`.
Non sono disponibili MRR, Recall, paired delta o ablation E7–E12 validi: v2 è
terminata al limite di circa 12 ore durante la canonicalizzazione; v3 è arrivata
alla valutazione development ma ha fallito prima di produrre risultati
completi; v4 è ancora attiva.

## Nuovo confine di esecuzione

- Locale: sviluppo, lint/compile e unit test brevi.
- Kaggle: smoke test ridotti e inferenza offline finale; niente preprocessing o
  benchmark completi di molte ore.
- VM esterna: canonicalizzazione completa, costruzione artifact, benchmark
  E7–E12 e probe isolati lunghi. Nessuna VM viene avviata senza approvazione.

La prossima operazione sicura è soltanto raccogliere l'output di v4 quando
diventa terminale, oppure proporne la cancellazione secondo la stop-rule. Non
va aperto il sealed stage manualmente e non va avviato un sostituto Kaggle.
