# Goal 4 — Leaderboard calibration

Ultimo aggiornamento: 2026-10-12

Checkpoint Goal 5 (2026-10-12): il kernel Goal 5 v4 resta separato dalla
calibrazione e non è stato usato. La prima submission ufficiale è stata eseguita
con la baseline Goal 4 E6 congelata.

## Stato

**Submission ufficiale completata.** Kaggle ha accettato ed eseguito la
versione 4; il public MRR@25 visualizzato è **0,000**.

### Submission registrata

La versione inviata è la Kaggle v4 del kernel Goal 4, E6 invariato. Il preflight
e l'esito sono in `FIRST_SUBMISSION_PRECHECK.md`; il manifest machine-readable
è `configs/first_submission_goal4_e6.yaml`.

| Campo | Valore |
|---|---|
| Submission ref | `57109254` |
| Invio | `2026-10-12T13:54:59.493Z` |
| Stato | `COMPLETE` |
| Public MRR@25 visualizzato | **0,000** |
| Rank | **3139 / 3140** |
| Snapshot leaderboard | `2026-10-12T14:42:23Z` |
| Versione kernel | 4 |
| Hash sorgente normalizzato | `b41302fee0454252617e852b22cec3e48f218fb097da9cde4e304ba50f2b473d` |
| Runtime hidden | non esposto dalla CLI/API Kaggle |
| Turnaround scoring osservato | 2.769,79–2.816,43 s |

Quota dopo il completamento: 1 submission oggi, 1 lifetime, 4 residue. Non è
stata creata una nuova versione né effettuata una seconda submission.

La Kaggle CLI 2.2.4 è installata e autenticata via OAuth. Non era disponibile
un tool Kaggle MCP in questa sessione, quindi le operazioni sono state eseguite
con la CLI ufficiale. Tutti i kernel sono privati, Internet è disattivato e non
esistono chiamate `competitions submit` nel bundle.

## Snapshot leaderboard

Il download read-only della leaderboard alle `14:42:23Z` ha restituito:

```text
kaggle competitions leaderboard \
  enveda-CASMI26-molecule-id-mass-spectra --show
```

| Posizione osservata | Team | Public MRR@25 |
|---:|---|---:|
| 1 | CHU1PC | 0,491 |
| 2 | MarvinTMB | 0,484 |
| 3 | pikachu | 0,481 |
| 3139 | MPerni | 0,000 |

Lo score pubblico non è stato usato per scegliere pesi, soglie o feature.

## Perché il confronto non è diretto

La MRR locale e il public score provengono da distribuzioni diverse. Il
benchmark locale contiene 32 identità validation, tutte `enveda-180` e
`timsTOF`, e usa un catalogo costruito da una porzione del train. Il public
leaderboard usa le 400 molecole test nascoste e il catalogo/candidate generator
scelto dal concorrente. Un delta locale non può essere sommato o rapportato al
valore 0,484 come previsione del public score.

La submission autorizzata è il singolo punto di calibrazione. Il divario fra
0,402011 locale e 0,000 pubblico non stima un delta di ranking sulla stessa
distribuzione: rivela che il benchmark closed-world non rappresenta la pipeline
hidden end-to-end. In particolare E6 riordina soltanto candidati del catalogo
train-only; non genera strutture nuove.

L'ipotesi primaria è quindi candidate coverage/novelty insufficiente. Non è una
prova diretta che tutti i target siano assenti: con truth hidden non è possibile
separare assenza dal catalogo e rank oltre 25. Qualunque diagnosi successiva deve
essere svolta offline, non tramite tuning iterativo sul leaderboard.

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
| Submission ufficiale | **eseguita una volta; COMPLETE, public 0,000** |

Artifact pronti: `artifacts/goal4_kaggle_v4/goal4/goal4_results.json`,
`artifacts/goal4_kaggle_v4/goal4_inference/goal4_selected_inference_report.json`
e `artifacts/goal4_kaggle_v4/submission.csv`.

## Decisione di calibrazione

- conservare E6 v4 come baseline storica congelata;
- non modificare E6 in risposta al public score;
- non usare ulteriori submission per diagnosticare candidate coverage;
- prima di un altro invio, dimostrare offline che il candidate generator tratta
  strutture non presenti nel catalogo train-only;
- mantenere Goal 5 e il futuro workflow VM separati da questa calibrazione.
