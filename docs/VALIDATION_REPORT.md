# Validation report: leakage-free retrieval diagnostics

Data: 2026-10-09  
Run autorevole: Kaggle privato `mperni/casmi26-leakage-free-validation`, versione 4  
Artifact locale: `artifacts/validation_kaggle_v4/validation/validation_results.json`

## 1. Obiettivo e perimetro

Questo studio sostituisce lo smoke test same-identity come evidenza decisionale. Misura separatamente: disponibilita del target nel pool, qualita del ranking quando il target e disponibile e comportamento quando la struttura e assente dal catalogo.

Non sono stati implementati o addestrati DreaMS, ICEBERG/GLACIER o nuovi Transformer. Non e stata effettuata alcuna submission. Il run usa la baseline esistente e un catalogo bounded per validare contratti, protocolli e metriche.

## 2. Protocolli

### Library holdout

Training/reference e validation possono condividere l'identita molecolare, ma usano acquisizioni distinte. I duplicati esatti di contenuto spettrale sono rimossi globalmente. Questo protocollo misura lookup/replicate matching, non generalizzazione chimica.

### Molecule-disjoint

Le identita di validation non compaiono nelle osservazioni di training ne negli spettri di riferimento. Rimangono presenti nel catalogo strutturale: la candidate generation puo recuperarli, ma il modello non ha visto spettri della stessa molecola.

### Novelty holdout

Usa la stessa partizione di identita del molecule-disjoint, ma rimuove le identita di validation anche dal catalogo. Misura esplicitamente il limite di un sistema closed-world.

Ogni protocollo salva un manifest canonico con seed, fingerprint dataset, assegnazione spectrum/identity, partizioni model-selection/final, sommari di dominio e hash SHA-256.

## 3. Audit leakage

L'audit viene eseguito prima del fit e blocca il run in caso di violazione. Controlla:

- unicita degli spectrum ID e completezza delle mappe;
- canonicalizzazione InChIKey14 e coerenza con lo SMILES RDKit;
- sovrapposizione di identita vietata dal protocollo;
- duplicati di contenuto spettrale tra partizioni;
- osservazioni validation presenti nel fit del ranker;
- contamination del catalogo nel novelty holdout;
- provenance delle feature e assenza di target-derived features.

Esito v4: tutti i controlli superati per tutti e tre i protocolli. L'audit indipendente della baseline precedente ha inoltre rilevato che il vecchio holdout era valido solo come library holdout, che non aveva hash del contenuto spettrale e che il fingerprint del primo MiB non era sufficiente a rendere il dataset auditabile.

## 4. Configurazione

| Parametro | Valore |
|---|---:|
| Seed | 2026 |
| Identita | 128 |
| Spettri per identita | 3 |
| Spettri totali | 384 |
| Righe massime scansionate | 300.000 |
| Catalogo strutturale massimo | 4.096 |
| Candidate pool | 1.000 |
| Tolleranza massa | 20 ppm |
| Tolleranza picchi | 0,02 Da |
| Picchi massimi | 256 |
| Repliche bootstrap | 500 |

Il catalogo viene costruito dalle strutture canoniche osservate durante lo scan del train, indipendentemente dalla reference library spettrale. Sono supportati anche gli addotti multimerici `[2M+H]+`, `[2M+Na]+` e `[2M-H]-`.

## 5. Metriche

Per ogni metodo e partizione sono calcolati Candidate Recall@25/100/1000, pool recall, MRR@25, Hit@1/5/10, conditional MRR@25, oracle MRR@25, target mancanti e proxy same-formula. Le confidence interval sono bootstrap percentile al livello molecola; i confronti fra metodi riusano gli stessi resample e sono quindi appaiati.

## 6. Risultati principali

### All validation

| Protocollo | Metodo | Recall@25 | Pool recall | MRR@25 | Hit@1 | Hit@5 | Hit@10 | Same-formula proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Library | Nearest mass | 1,0000 | 1,0000 | 0,7363 | 0,5625 | 0,9766 | 1,0000 | 51 |
| Library | Retrieval union | 1,0000 | 1,0000 | 0,9560 | 0,9297 | 0,9844 | 1,0000 | 7 |
| Library | Ranker | 1,0000 | 1,0000 | 0,9961 | 0,9922 | 1,0000 | 1,0000 | 0 |
| Molecule-disjoint | Nearest mass | 1,0000 | 1,0000 | 0,7467 | 0,5938 | 0,9375 | 1,0000 | 11 |
| Molecule-disjoint | Retrieval union | 1,0000 | 1,0000 | 0,6659 | 0,4688 | 0,9375 | 1,0000 | 11 |
| Molecule-disjoint | Ranker | 1,0000 | 1,0000 | 0,5987 | 0,3750 | 0,9062 | 0,9688 | 13 |
| Novelty | Tutti | 0,0000 | 0,0000 | 0,0000 | 0,0000 | 0,0000 | 0,0000 | 17* |

`*` Nel novelty holdout il target e assente: il conteggio indica candidati top-25 con la stessa formula, non un errore di ranking del target.

Per library holdout, il ranker MRR@25 ha IC95% [0,9844; 1,0000]. Per molecule-disjoint: nearest mass [0,6404; 0,8461], retrieval union [0,5593; 0,7666], ranker [0,4807; 0,7292].

### Confronti appaiati MRR@25

| Protocollo/subset | Retrieval union - mass | IC95% | Ranker - retrieval union | IC95% |
|---|---:|---:|---:|---:|
| Library/all | +0,2197 | [+0,1645; +0,2718] | +0,0401 | [+0,0130; +0,0742] |
| Library/final | +0,2365 | [+0,1628; +0,2998] | +0,0438 | [+0,0078; +0,0910] |
| Molecule-disjoint/all | -0,0807 | [-0,1536; -0,0156] | -0,0672 | [-0,1558; +0,0141] |
| Molecule-disjoint/model selection | -0,0781 | [-0,1875; 0,0000] | -0,1574 | [-0,2925; -0,0414] |
| Molecule-disjoint/final | -0,0833 | [-0,1875; 0,0000] | +0,0229 | [-0,0813; +0,1323] |

Il final molecule-disjoint contiene soltanto 16 query: l'apparente inversione ranker-vs-union non e conclusiva. La conclusione robusta e che l'evidenza spettrale progettata per repliche same-identity non trasferisce al disjoint, mentre il ranker supervisionato non mostra un vantaggio stabile.

## 7. Domain shift e analisi errori

Il cohort e interamente `enveda-180`/`timsTOF`, quindi i breakdown source e instrument coincidono col totale e non permettono un test cross-domain. Nel molecule-disjoint, 30/32 query sono nel bin di massa [200,400) e 2/32 in [400,600); il ranker ottiene rispettivamente MRR 0,5886 e 0,7500. I breakdown per addotto sono disponibili nell'artifact, ma i gruppi sono piccoli: `[2M+H]+` n=1, `[2M+Na]+` n=8, `[2M-H]-` n=3, `[M+CH2O2-H]-` n=2 e `[M+H]+` n=18.

La quota proxy same-formula del ranker molecule-disjoint e 13/32. Non dimostra da sola che ogni errore sia un isomero costituzionale, ma rende prioritario un segnale capace di discriminare strutture a massa/formula uguale.

## 8. Esperimento correttivo sugli addotti

Un confronto controllato tra v2 e v3, con membership train/reference/validation invariata, ha isolato un errore di inversione degli addotti multimerici. L'aggiunta delle formule corrette ha portato la copertura della massa neutra molecule-disjoint da 61/96 a 96/96. Sul vecchio catalogo da 128 strutture il nearest-mass Recall@25 e passato da 0,6563 a 1,0000. Questo risultato e classificato come correzione di validita, non come miglioramento modellistico.

## 9. Decisione

- Non promuovere il ranker corrente come soluzione molecule-disjoint.
- Conservare nearest-mass come controllo forte e la pipeline attuale come harness riproducibile.
- Provare per primo un spectrum-to-fingerprint baseline con hard negatives same-formula e ranking isomer-aware.
- Applicare analog propagation con gating/calibrazione e ablation, non come fusione sempre attiva.
- Espandere catalogo e cohort prima di stimare il valore assoluto finale.
- Rimandare DreaMS e ICEBERG/GLACIER finche il baseline fingerprint non dimostra un delta positivo sul final molecule-disjoint.
- Mantenere separato il ramo novelty generation, che dovra essere valutato con validita chimica, novelty, mass consistency e recovery oltre al ranking chiuso.

## 10. Riproducibilita

Comando locale di verifica:

```powershell
uv run pytest -q --cov=casmi26 --cov-report=term-missing
```

Esito corrente: 78 passed, coverage 87% su 1.781 statement.

Il run Kaggle v4 ha completato la pipeline in 50,97 s. I manifest hanno hash:

- library holdout: `43b1f43cc55cec297ff9cd96259f3a89edd989e84c2fe9bd60202c4d1f3b71ec`;
- molecule-disjoint: `c51e7eed6b5c417b0003f82a7cab97a7b94ebe0e48bede09a40ecaad8d7cbc5c`;
- novelty holdout: `c652a6634bf9eb37cb7a9967b69e31ded7d351fe45441790940f548d02389ec9`.

Gli artifact Kaggle sono intenzionalmente ignorati da Git; risultati e decisioni durevoli sono registrati in questo report e in `docs/EXPERIMENT_LOG.md`.

## 11. Follow-up Goal 3

L'audit successivo ha confermato che il Recall@25=1,0000 qui riportato e proprio del catalogo controlled da 4.096 strutture, costruito con priorita per il cohort target. Nel catalogo target-blind da 49.620 strutture, il Recall@25 nearest-mass scende a 0,8750, pur restando 1,0000 a 100/1000 candidati. Il risultato storico di questo report rimane immutato e riproducibile; la nuova evidenza end-to-end e documentata in [GOAL3_MODEL_REPORT.md](GOAL3_MODEL_REPORT.md).
