# Stato progetto CASMI 2026

Ultimo aggiornamento: 2026-10-12, checkpoint 15:31:34 Europe/Rome

## Stato sintetico

I Goal 1–4 sono completati. **Goal 5 è in corso e congelato a un checkpoint
sicuro; Goal 6 non è iniziato.** Il riferimento end-to-end promosso resta il
realistic benchmark Goal 4 E6, target-blind, con catalogo canonico di 49.195
strutture. Le metriche E7–E12 Goal 5 non sono ancora disponibili.

Il run autorevole è il kernel Kaggle privato
`mperni/casmi26-goal4-spectral-ranking`, versione 4, offline. E6 è promosso
come nuova baseline: analog propagation sul top-100 nearest-mass, confinata al
gruppo di formula dell'anchor E0. Nessuna submission ufficiale è stata
effettuata.

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
- suite locale: 204 passed, 7 skipped; `compileall` e `git diff --check`
  verificati prima del checkpoint.

Non completati:

- metriche E7–E12 development/sealed, paired bootstrap e ablation complete;
- candidate Recall@25/100/1000 misurata su C1;
- statistiche domain-shift finali dal result artifact;
- DreaMS scientific probe nell'ambiente Python 3.11 isolato;
- cataloghi esterni C2/C3, non scaricati né importati;
- rehearsal Goal 5 completo e decisione modellistica successiva.

### Job Kaggle

L'unico job attivo è `mperni/casmi26-goal5-scalable-retrieval` v4. Avvio:
2026-10-12 11:22:34 UTC / 13:22:34 Europe/Rome. Stato alle 15:31:34 locali:
`RUNNING`, wall time 2 h 09 min 00,6 s. Non è stato avviato alcun nuovo job dopo
la richiesta di checkpoint. Gli altri kernel CASMI noti risultano `COMPLETE`.

La v2 ha raggiunto il limite dopo circa 43.084 s conservando indice e piani di
dominio. La v3 è terminata in errore dopo 10.254,6 s (2 h 50 min 54,6 s) per
un anchor E12 esterno alla union pool; il bug è corretto e coperto da test. La
v4 non è ancora classificabile come bloccata, perché al checkpoint non aveva
raggiunto quel runtime e Kaggle non espone log intermedi. Stop-rule: proporre
cancellazione oltre 4 ore senza artifact terminale; limite operativo 8 ore.

### Workflow deciso

- Locale: scrittura codice e unit test brevi.
- Kaggle: smoke test e inferenza offline.
- VM esterna: canonicalizzazione, preprocessing e benchmark lunghi.

Nessuna VM esterna, GPU a pagamento o submission è stata avviata/autorizzata.
La prossima azione consentita è raccogliere il terminal artifact di v4 o
proporne l'interruzione secondo la stop-rule; non avviare un run sostitutivo.

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
- Nell'inferenza nascosta una reference duplicata per contenuto spettrale è
  stata esclusa automaticamente: 128 reference iniziali, 127 utilizzate.

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

## Inferenza pronta, non inviata

Il CSV Kaggle v4 contiene 400 molecule ID ed esattamente 25 SMILES validi e
unici per riga. SHA-256:
`52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f`.
Benchmark e selezione richiedono 672,53 s; l'inferenza test 1.500,43 s. Peak
RSS è 1,69 GB e la pipeline non alloca VRAM. Il file resta un artifact locale;
l'invio richiede approvazione esplicita.

## Qualità

- Unit test: 153 passati, 7 skip PyTorch opzionali.
- Coverage: 66% su 5.197 statement; moduli Goal 4 centrali 87–93%, ranking 91%.
- `compileall` e `git diff --check`: passati.
- E2E Kaggle offline: passato su train/test ufficiali.
- Nessuna VM a pagamento, grande training o submission.

## Decisione successiva

Goal 5 segue principalmente lo Scenario C: ampliare e indicizzare la libreria
spettrale leakage-safe, migliorare retrieval analogico/confidence e provare
DreaMS soltanto come embedding congelato. L'espansione Tier 1 del catalogo va
misurata in parallelo. ICEBERG/GLACIER diventano prioritari solo se il residuo
same-formula dimostra la necessità di forward spectral reranking.

Dettagli: [GOAL4_SPECTRAL_RANKING_REPORT.md](GOAL4_SPECTRAL_RANKING_REPORT.md),
[CANDIDATE_COVERAGE_REPORT.md](CANDIDATE_COVERAGE_REPORT.md) e
[LEADERBOARD_CALIBRATION.md](LEADERBOARD_CALIBRATION.md).
