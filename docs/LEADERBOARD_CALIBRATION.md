# Goal 4 — Leaderboard calibration

Ultimo aggiornamento: 2026-10-10

Checkpoint Goal 5 (2026-10-12): nessuna submission è stata aggiunta. Il kernel
Goal 5 v4 è un benchmark privato offline e non contiene chiamate di submission;
era ancora `RUNNING` dopo 2 h 09 min 00,6 s al checkpoint. La baseline candidata
alla prima calibrazione ufficiale resta Goal 4 E6 finché Goal 5 non produce un
artifact terminale con evidenza migliore.

## Stato

**Nessuna submission ufficiale è stata effettuata.** Il kernel privato prepara
un CSV e si ferma. L'invio richiede approvazione esplicita dell'utente.

### Candidato prima submission

Stato al 2026-10-12: **READY / AWAITING APPROVAL**. Il candidato è la versione
Kaggle 4 del kernel Goal 4, E6 invariato. Il preflight completo è in
`FIRST_SUBMISSION_PRECHECK.md`; il manifest machine-readable è
`configs/first_submission_goal4_e6.yaml`.

Non va creato un nuovo commit Kaggle: la versione 4 già completata è lo snapshot
verificato da sottoporre alla scoring rerun hidden. Quota verificata: 0
submission oggi, 0 lifetime, 5 residue. I campi public score, posizione e
runtime hidden restano `N.A.` fino all'approvazione e all'esecuzione effettiva.

La Kaggle CLI 2.2.4 è installata e autenticata via OAuth. Non era disponibile
un tool Kaggle MCP in questa sessione, quindi le operazioni sono state eseguite
con la CLI ufficiale. Tutti i kernel sono privati, Internet è disattivato e non
esistono chiamate `competitions submit` nel bundle.

## Snapshot leaderboard

Il comando read-only

```text
kaggle competitions leaderboard \
  -c enveda-CASMI26-molecule-id-mass-spectra --show
```

ha restituito nuovamente il 2026-10-10:

| Posizione osservata | Team | Public MRR@25 |
|---:|---|---:|
| 1 | MarvinTMB | 0,484 |
| 2 | pikachu | 0,481 |
| 3 | Oliver Ford | 0,459 |

Il valore riportato dall'utente è quindi confermato. Non è stato usato per
scegliere pesi, soglie o feature.

## Perché il confronto non è diretto

La MRR locale e il public score provengono da distribuzioni diverse. Il
benchmark locale contiene 32 identità validation, tutte `enveda-180` e
`timsTOF`, e usa un catalogo costruito da una porzione del train. Il public
leaderboard usa le 400 molecole test nascoste e il catalogo/candidate generator
scelto dal concorrente. Un delta locale non può essere sommato o rapportato al
valore 0,484 come previsione del public score.

La submission autorizzata servirà come singolo punto di calibrazione. Non verrà
usata ripetutamente per tuning.

## Baseline e notebook/kernel

- Kernel: `mperni/casmi26-goal4-spectral-ranking`, privato.
- Entrypoint: `kaggle/run_goal4.py`.
- Competition source: `enveda-CASMI26-molecule-id-mass-spectra`.
- Asset source: `mperni/casmi26-baseline-assets`.
- Internet: disabilitato.
- Hardware verificato: Tesla T4 disponibile; la pipeline Goal 4 è CPU-bound e
  non alloca VRAM per il ranker non neurale.
- RDKit: 2026.03.3 installato da wheel offline CPython 3.13.
- Candidate pool: top-100 mass-based, target-blind.
- Output: massimo 25 SMILES, canonicalizzazione e deduplica InChIKey14.
- Checkpoint: non richiesto per E0/E3/E6; i pesi sono scalar selection values e
  il reference library è ricostruito deterministicamente dal train consentito.

Il run canonico privato v4 ha selezionato E6 (`analog_score`, peso 0,5), ha
prodotto 400 righe per 400 molecule ID con esattamente 25 candidati validi e
unici per riga e non ha effettuato submission. Runtime: 672,53 s per benchmark
e selezione, 1.500,43 s per inferenza test, circa 2.190 s end-to-end. Peak RSS
validation: 1,69 GB; VRAM allocata: 0 byte.

La guardia anti-leakage ha escluso una delle 128 reference prima
dell'inferenza perché il suo contenuto spettrale era identico a una query test;
127 reference sono state utilizzate. SHA-256 del CSV pronto:
`52cdeac4ad5e3907d807c16a457fbe327ccfa40cd82205daf6f1642eec2b363f`.

## Checklist pre-submission

| Controllo | Stato |
|---|---|
| Kernel privato | verificato |
| Internet off | verificato |
| Competition e asset associati | verificato |
| Wheel progetto/RDKit offline | verificato |
| Compilazione entrypoint | verificata |
| Nessuna chiamata di submission | verificata |
| Catalogo target-blind | verificato |
| Canonicalizzazione RDKit/InChIKey14 | verificata; mismatch source filtrati nel run finale |
| 400 molecule ID esatti | verificato nel run v4 |
| 1–25 candidati validi/unici | verificato; 25/25 nel run v4 |
| Runtime/RAM/VRAM | registrati negli artifact Goal 4 |
| Submission ufficiale | **non autorizzata / non eseguita** |

Artifact pronti: `artifacts/goal4_kaggle_v4/goal4/goal4_results.json`,
`artifacts/goal4_kaggle_v4/goal4_inference/goal4_selected_inference_report.json`
e `artifacts/goal4_kaggle_v4/submission.csv`.

## Dati da registrare dopo autorizzazione

Una eventuale submission dovrà aggiungere, senza riscrivere la storia locale:

- versione kernel e versione dataset asset;
- commit Git o hash completo del source bundle;
- esperimento selezionato e configurazione congelata;
- score local all/development/final;
- public score, runtime e risorse;
- differenze rispetto alle aspettative e possibili cause;
- dichiarazione esplicita che il public score non è stato riutilizzato per
  ottimizzare iperparametri.
