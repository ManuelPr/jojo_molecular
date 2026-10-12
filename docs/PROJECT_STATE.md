# Stato progetto CASMI 2026

## Recovery checkpoint — 2026-10-12

Audit locale completato senza training, job Kaggle o apertura del sealed
holdout. Sul proxy domain-matched development (188 identità, 876 spettri), C0
copre 108 truth (57,45%) e C1 188 (100%). C1 raggiunge Candidate
Recall@25/100/1000 89,89/99,47/100%, ma la mass-only MRR@25 è 0,3801 contro
0,4069 di C0 perché i competitor same-formula medi crescono da 1,55 a 14,18.

Tutti gli addotti osservati sono supportati; errore massa neutra mediano 1,65
ppm e p90 3,12 ppm. La causa primaria più probabile del public 0,000 è candidate
coverage/selection bias closed-world, con domain shift e sole 127 reference
spettrali come co-cause. C2/C3 non sono stati costruiti.

Goal 5 v4 è terminato `COMPLETE`. Artifact e log sono stati scaricati una sola
volta; durata effettiva dal log 8 h 21 min 46,64 s, oltre il budget di 8 ore.
E8/C1 migliora coverage e Hit@5/10 ma non Hit@1; i delta MRR vs E7 non sono
stabili fra A/B e sealed. Non viene promosso. Goal 6 resta non iniziato e
nessuna seconda submission è autorizzata.

Report: [ZERO_SCORE_ROOT_CAUSE.md](ZERO_SCORE_ROOT_CAUSE.md),
[EXTERNAL_COVERAGE_ANALYSIS.md](EXTERNAL_COVERAGE_ANALYSIS.md) e
[RECOVERY_EXPERIMENT_PLAN.md](RECOVERY_EXPERIMENT_PLAN.md).

Ultimo aggiornamento: 2026-10-12, calibrazione leaderboard 16:42 Europe/Rome

## Stato sintetico

I Goal 1–4 sono completati. **Goal 5 dispone ora di un artifact terminale ma
nessun E8–E12 è promosso; Goal 6 non è iniziato.** Il riferimento end-to-end promosso resta il
realistic benchmark Goal 4 E6, target-blind, con catalogo canonico di 49.195
strutture. Le metriche E7–E12 sono disponibili e mostrano più coverage, ma non
un delta MRR/Hit@1 stabile.

Il run autorevole è il kernel Kaggle privato
`mperni/casmi26-goal4-spectral-ranking`, versione 4, offline. E6 è promosso
come nuova baseline: analog propagation sul top-100 nearest-mass, confinata al
gruppo di formula dell'anchor E0. La prima submission ufficiale è stata
completata: public MRR@25 visualizzato 0,000, rank 3139/3140 allo snapshot.

## Checkpoint Goal 5

Completati:

- baseline E6 congelata e verificata tramite hash e signature;
- C1 full-train costruito: 271.439 strutture canoniche, 50.662 formule, indice
  checksummed/mmap da 34.821.876 byte;
- retrieval mass/formula esatto, pool dinamici, analog prefilter scalabile,
  staged reranking e union/RRF E12;
- protocollo domain-matched A/B/C con 234 identità, 188 development, 46 sealed,
  1.097 spettri query e 2.932 reference capped;
- adapter DreaMS frozen e decisione `NOT RUN / environment-blocked`;
- bundle Kaggle privato offline senza chiamate di submission;
- metriche E7–E12 development/sealed, paired bootstrap, candidate recall e
  diagnostiche domain-shift recuperate dal job v4 terminale;
- suite locale: 204 passed, 7 skipped; `compileall` e `git diff --check`
  verificati prima del checkpoint.

Non completati:

- DreaMS scientific probe nell'ambiente Python 3.11 isolato;
- cataloghi esterni C2/C3, non scaricati né importati;
- ladder controllata per isolare l'effetto del numero di reference;
- nuova pipeline candidata con ranking capace di recuperare Hit@1.

### Job Kaggle

`mperni/casmi26-goal5-scalable-retrieval` v4 è terminato `COMPLETE`. Il log
effettivo copre 30.106,64 s (8 h 21 min 46,64 s). Artifact e log sono stati
scaricati una sola volta sotto `artifacts/goal5_kaggle_v4/`; nessun nuovo job o
submission è stato avviato.

La v2 ha raggiunto il limite dopo circa 43.084 s conservando indice e piani di
dominio. La v3 è terminata in errore dopo 10.254,6 s (2 h 50 min 54,6 s) per
un anchor E12 esterno alla union pool; il bug è corretto e coperto da test. La
v4 ha completato E7–E12 ma ha superato il limite operativo di 8 ore: non va
rilanciata su Kaggle.

### Workflow deciso

- Locale: scrittura codice e unit test brevi.
- Kaggle: smoke test e inferenza offline.
- VM esterna: canonicalizzazione, preprocessing e benchmark lunghi.

Nessuna VM esterna o GPU a pagamento è stata avviata. L'unica submission
autorizzata è E6 v4; nessuna submission Goal 5 è stata effettuata.
La prossima azione è archiviare v4 e spostare la ladder reference/C2-C3 sulla
VM; non avviare un run Kaggle sostitutivo.

## Evidenza Goal 4

| Split realistic | E0 MRR@25 | E6 MRR@25 | Delta paired | IC95% | Hit@1 E0 → E6 |
|---|---:|---:|---:|---:|---:|
| Development, 16 | 0,349104 | 0,365473 | +0,016369 | [+0,001938; +0,033939] | 0,2500 → 0,2500 |
| Final, 16 | 0,401331 | 0,438549 | +0,037218 | [-0,001770; +0,103166] | 0,3125 → 0,3750 |
| All-validation, 32 | 0,375217 | 0,402011 | +0,026794 | [+0,003121; +0,061990] | 0,2813 → 0,3125 |

Candidate Recall@25/100/1000 resta 0,875/1,000/1,000 perché E0–E7 usano lo
stesso pool top-100. Su tutte le query E6 ne migliora 9, ne peggiora 2 e ne
lascia 21 invariate. E1 ed E2 selezionano peso zero. E5 LambdaRank è negativo
sul development e non viene selezionato, anche se il final piccolo mostra un
valore elevato e instabile.

## Benchmark e leakage

- Catalogo sorgente: 49.620 strutture; catalogo canonico: 49.195; reject: 425.
- Validation: 32 identità, 96 spettri, tutte `enveda-180`/`timsTOF`.
- Zero target consultation, prioritization o injection.
- Recall@100=1 è spiegata da truth rank massimo 78; quattro target sono oltre
  rank 25 (29, 46, 37, 78).
- 26/32 query hanno competitor same-formula; 18 errori E0 sono proxy di
  isomeria costituzionale.
- Reference train identity-OOF e validation identity/content-disjoint.
- Nel rehearsal sul test placeholder una reference duplicata per contenuto
  spettrale è stata esclusa automaticamente: 128 reference iniziali, 127
  utilizzate. Il report del rerun hidden non è esposto.

## Componenti Goal 4

- `spectral_evidence.py`: peak matching, cosine/modified/shifted, entropy,
  neutral losses monoisotopiche e aggregazione multi-spettro.
- `analog_propagation.py`: retrieval analogico, mass shift, relazione
  strutturale, compatibilità frammenti/addotto e guardie anti-leakage.
- `goal4_audit.py`: distribuzioni ppm, rank, breakdown e tassonomia errori.
- `candidate_catalogs.py`: canonicalizzazione, deduplica, mass/formula index,
  mmap e fingerprint bit-packed.
- `goal4_ranking.py` e `goal4_pipeline.py`: E0–E7, selection development-only,
  bootstrap appaiato e resource accounting.
- `goal4_inference.py`: catalogo target-blind e inferenza E6 offline.

## Inferenza e calibrazione pubblica

Il CSV di rehearsal Kaggle v4 contiene 400 molecule ID ed esattamente 25 SMILES
validi e unici per riga. SHA-256:
`52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f`.
Benchmark e selezione richiedono 672,53 s; l'inferenza test 1.500,43 s. Peak
RSS è 1,69 GB e la pipeline non alloca VRAM.

Dopo approvazione esplicita, la stessa versione 4 è stata inviata come
submission `57109254` alle `2026-10-12T13:54:59.493Z`. Stato `COMPLETE`, public
MRR@25 visualizzato 0,000, rank 3139/3140 alle `14:42:23Z`. Il runtime hidden
non è esposto; il turnaround osservato è 2.769,79–2.816,43 s. Nessun nuovo
commit Kaggle, tuning o secondo invio.

## Qualità

- Unit test: 153 passati, 7 skip PyTorch opzionali.
- Coverage: 66% su 5.197 statement; moduli Goal 4 centrali 87–93%, ranking 91%.
- `compileall` e `git diff --check`: passati.
- E2E Kaggle offline: passato su train/test ufficiali.
- Nessuna VM a pagamento o grande training; una sola submission E6 autorizzata.

## Decisione successiva

Goal 5 segue principalmente lo Scenario C: ampliare e indicizzare la libreria
spettrale leakage-safe, migliorare retrieval analogico/confidence e provare
DreaMS soltanto come embedding congelato. L'espansione Tier 1 del catalogo va
misurata in parallelo. ICEBERG/GLACIER diventano prioritari solo se il residuo
same-formula dimostra la necessità di forward spectral reranking.

Dettagli: [GOAL4_SPECTRAL_RANKING_REPORT.md](GOAL4_SPECTRAL_RANKING_REPORT.md),
[CANDIDATE_COVERAGE_REPORT.md](CANDIDATE_COVERAGE_REPORT.md) e
[LEADERBOARD_CALIBRATION.md](LEADERBOARD_CALIBRATION.md).

## Esito prima submission ufficiale

La baseline Goal 4 E6 è stata inviata una volta dalla versione Kaggle 4 già
`COMPLETE`, senza modifiche e senza includere Goal 5. Lo score pubblico
visualizzato 0,000 mostra che la validation locale closed-world non è
rappresentativa della pipeline hidden end-to-end.

L'ipotesi primaria è candidate coverage/novelty: il catalogo E6 è train-only e
il reranker non può recuperare strutture assenti. È un'inferenza, non una prova
diretta sulle truth hidden. La priorità successiva, quando Goal 5 riprenderà, è
validare offline un candidate generator open-world prima di un'altra
submission. Dettagli in `FIRST_SUBMISSION_PRECHECK.md` e
`LEADERBOARD_CALIBRATION.md`.
