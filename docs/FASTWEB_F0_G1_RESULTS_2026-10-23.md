# Fastweb F0/G1 — pilot del 23 ottobre 2026

Completati staging degli input necessari, porting F0 e confronto G1.
**Decisione: nessuna promozione del proxy o della fusione da questo pilot.**
I proxy aumentano la disponibilità delle evidenze ma peggiorano MRR nel cohort
osservato. Nessuna run completa, submission Kaggle, FPNet G2 o esperimento
generativo G4 avviato. Il generatore già interno al controllo resta parte di F0.

## Protocollo e limiti

- Job **2545**, già esistente e autorizzato dopo la cancellazione di 2541:
  H100 80 GB, 8 CPU logiche, limite RAM 32 GiB. Scheduler finale RUNNING,
  TimeLimit=UNLIMITED, EndTime=Unknown. Nessuna nuova allocazione.
- **16 molecole, 58 spettri**, solo acquisizioni `enveda-np-examples`.
  Selezione deterministica per addotto prima dei risultati: 5 real-H,
  5 NH4 blind, 1 water-loss blind, 5 other. Le 6 blind eleggibili producono
  10 proxy, 3 con CE multiple.
- Rimossi **3.490 spettri** di tutte le 16 identità equivalenti dalle reference
  di training, usando il crosswalk scorer RDKit 2026.03.3. Eliminati anche
  **2 spettri esterni** delle query, conservati gli altri 749.
  Cataloghi candidati mantenuti, anche per le strutture escluse dalle reference.
- Cohort pubblico diagnostico, non sealed. Split congelati byte-identici.
  Le funzioni di inferenza consumano picchi, precursore, addotto, polarità,
  CE e strumento. Le etichette non vengono usate come formula oracle,
  feature di ranking o chiave di retrieval.
- **Reference disjoint non equivale a pretraining disjoint.** L'audit upstream
  riporta che Full1 ha visto il panel; A+B, ranker e simulatori non certificano
  l'esclusione di queste strutture. I cinque FPNet fold-safe escludono il panel
  secondo audit/checkpoint pubblici verificati. Questi numeri NON stimano
  MRR unseen-structure o leaderboard nascosto.
- G1 congela pool finale e punteggi base F0: isola il reranking finale.
  L'ordinamento PubChem a monte è comune, non ricalcolato per ogni braccio.
  Non è un'ablation end-to-end di tutti i punti di routing dei simulatori.

## Staging e versioni

Starter completo: **4.342.989.049 byte**, FPNet V5 **55/55 checksum** pubblicati
corrispondenti. Preflight sul vero train.parquet PASS: 2.539.608 righe,
forward/backward CUDA e gradienti finiti. La venv di training è rimasta invariata;
dipendenze aggiuntive nel runtime e sito simulatori separati. Pip check finale PASS.

Aggiunti **421 file, 24.853.073.596 byte**, con SHA256 individuali:

| Dataset fissato | File |
|---|---:|
| attributed-v4g-reproduction-assets V6 | 211 |
| PubChem popularity prior V10 | 112 |
| natural-product knowledge table V9 | 98 |

I 9 file DreaMS grezzi V6 non letti dal controllo sono inventariati come
omessi; nessuna sostituzione con versioni nuove. Il tail DreaMS non è stato
esercitato: nel pilot ogni lista era piena. I tre array PubChem di V6 e V10
hanno SHA256 identici; entrambi registrati.

[Gu V492 V1, script 361010883](https://www.kaggle.com/code/guhongbin/casmi26-v492-dg-v19?scriptVersionId=361010883):
SHA256 `3b05fe5620f0bfe3acb319c782761acb61c61d283d8835b415a4d671cd841aa4`,
identico al pin. Verificati 64/64 file V4b e i pin dei moduli N1A/runner GLACIER.
Lo score pubblico storico 0,464 non è stato riprodotto ufficialmente.
I mount storici per versione restano non certificati: V6/V10/V9 sono lo
snapshot di ricerca esplicito del piano.

Quota personale NFS sconosciuta: servizio RPC quota non raggiungibile.
Nessun errore di quota/spazio durante staging. Credenziali esterne al repository,
mai stampate nei log. Lo spazio condiviso non è stato chiamato quota personale.

## Porting F0 e controlli

Entry point in `scripts/cluster/`:

- `stage_f0_assets.py`: versioni, paginazione, inventario SHA256 e recupero JSON
  ufficiale della stessa versione.
- `prepare_f0_source.py` e `prepare_f0_queries.py`: pin sorgente, moduli,
  cohort stratificato e reference escluse.
- `filter_f0_reference_cache.py`: filtro CSR delle acquisizioni esterne senza
  rimuovere le strutture candidate.
- `run_f0_control.py`: percorsi locali, niente pip nella venv, due worker per
  Engine 2/PubChem, budget di 300 s per simulatore, export e cache vincolati
  agli hash di codice, query, reference, catalogo, asset e runtime.
- `profile_command.py`: timeout e guardia RAM campionata a 26 GiB.
- `resume_f0_analysis.py`: ripresa della sola analisi con parity check.
- `f0_g1_evidence.py`: confronto appaiato, tabelle e missing/failed flags.

Engine 2: **430,19 s**, catalogo 1.137.233 strutture, 1.263 candidati MetFrag-lite,
16 liste. PubChem: 16 liste in circa 150 s, A+B e cinque fold secondo ricetta.
Main: 16 query, **zero errori**, 4 booster/160 feature; derivation self-test:
**0 mismatch**. Cache reference: **66,81 s**.

Il primo passaggio è stato interrotto da un `display` IPython assente dopo
l'inferenza. Adattatore corretto; ripresa solo l'analisi dai punteggi salvati.
Il guard ha rifiutato il primo recupero perché mancavano le formule PubChem
generate prima del reranking. Ripristinate dal sorgente: ricostruzione
**byte-identica**, SHA256
`2aeb2a8899af3031f5241f27675e8ffe8938d69daf1ff370104d2d803112e1fc`.
Nessuna predizione ripetuta.

Il joint G1 ha gli stessi RR del CSV F0 finale per tutte le 16 query.
SHA256 CSV finale:
`e5dffead918dce7a63407c21f99422b89ad6c5b653fc6f0cb23d31cdfdf0a6d5`.
Le etichette ereditate E004/E006 e `hidden_rerun` indicano modalità software,
non un'esecuzione sul test nascosto.

## G1: risultati appaiati

**628 candidati, 2.295 coppie candidato-spettro** nella tabella finale.
Struttura corretta presente per 16/16 query; anche copertura main pre-top60 e
Recall@100/@1000 del ranker main sono 16/16. È un proxy di classe 2 che mantiene
strutture note nel catalogo, non una misura di novelty recall.

| Trattamento | MRR@25, 16 query | MRR eleggibili, 6 query | Delta | Bootstrap 95%, 2.000 campioni per molecola | Regressioni |
|---|---:|---:|---:|---|---:|
| protonated_ice_fallback | 0.871528 | 0.657407 | +0.000000 | [+0.000000, +0.000000] | 0 |
| n1a_complement | 0.811111 | 0.496296 | -0.060417 | [-0.170833, +0.000000] | 2 |
| joint_ice_n1a | 0.804762 | 0.479365 | -0.066766 | [-0.177086, +0.000000] | 3 |

N1A usa `N1A_D` del sorgente fissato, inclusa la sua CE policy: non è un nuovo
braccio multi-CE. Complement applica proxy a 4 query senza ICE finito; joint
a tutte le 6 eleggibili. Routing e ordine dei 5 real-[M+H]+ invariati.

Copertura forward disponibile: **8/16 → 12/16 query** e **270/628 → 391/628
candidati** nel pool finale. GLACIER: **5 → 11 query**; proxy: 186 score
aggiuntivi, di cui 121 non già coperti da ICE. Nessuna predizione fallita.
Score mancanti conservati come missing, non sostituiti da qualità zero.

Regressioni principali: AMOGMTLMADGEOQ **1→5** e HGJXAVROWQLCTP **2→3**
in entrambi i trattamenti; KLLGGGQNRTVBSU **3→5** nel joint.
FBWWXAGANVJTLU migliora **9→7** nel joint, senza compensare le perdite.
Gate di promozione non soddisfatto. Nessuna modifica della policy di produzione;
eventuali ablation successive su development, senza riusare il sealed per tuning.

## Risorse e tempi misurati

Tutti i driver: CUDA, RDKit simulatore **2025.03.6** isolato,
PyTorch 2.14.1+cu130, zero fallimenti. Scorer principale **2026.03.3**.
CE multiple contate come job distinti; cache condivisa fra job equivalenti.

| Modello | Predizioni | Coppie input | Predizione s | Wall driver s | ms/coppia, predizione | ms/coppia, incluso load | Picco torch GiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| iceberg | 1036 | 1169 | 8.34 | 18.89 | 7.13 | 16.16 | 4.09 |
| glacier_real | 678 | 820 | 5.59 | 14.04 | 6.82 | 17.12 | 0.35 |
| glacier_proxy | 1134 | 932 | 9.23 | 17.63 | 9.90 | 18.92 | 0.39 |

Picco GPU totale campionato F0: **10,39 GiB** (10.637 MiB).
RAM cgroup campionata: cache **25,30 GiB**, Engine 2 **24,90 GiB**,
F0 **25,00 GiB**. Picco cumulativo del job letto alla fine **26,41 GiB**
su limite 32 GiB; zero eventi OOM/OOM-kill/max. Include VSCode, trasferimenti
e page cache. Target operativo provvisorio 26 GiB superato di circa 0,4 GiB
nel cumulativo; la guardia campiona ogni 2 s, non è un limite kernel.

## Stima prima della run completa

Proiezione conservativa sulla **stessa H100**, asset già staged: cache e primi
216 s Engine 2 mantenuti fissi, resto scalato dal pilot, incluso recupero CPU
ripetuto dell'analisi. Ipotesi: masse, CE, candidati/acquisizioni simili al cohort.

| Query | Stima |
|---:|---:|
| 32 | 0.50 h |
| 200 | 2.69 h |
| 400 | 5.30 h |

Non è un limite superiore garantito né un benchmark T4/Kaggle.
Cataloghi, fingerprint, fitting ranker e canonicalizzazione CPU dominano;
i tre driver forward hanno impiegato insieme **50,56 s**.
Il riuso delle cache può ridurre i tempi, ma non è misurato su 200 query.
Nessuna run da 32/200/400 query avviata.

## Artifact e ripresa

Root `artifacts/cluster/f0-g1-2545/`:

- `experiment-manifest.json`: input, codice, split, hash, risultati e risorse.
- `complete-assets-manifest.json`: 421 file aggiuntivi con versione/byte/SHA256.
  Lo starter mantiene il proprio manifest in `starter-20261022/`.
- `control/candidate_evidence.parquet`: 628 righe, identità scorer, provenienza,
  score/missing/failed, prior, fingerprint/ranker e ranghi per braccio.
- `control/raw_candidate_evidence.parquet`: 1.244 candidati pre-top60, 160
  feature e label applicate dopo inferenza.
- `control/candidate_spectrum_pairs.parquet`: 2.295 righe, addotto reale/proxy,
  CE. Score molecolari non attribuiti falsamente a singoli spettri.
  Raw proxy per spettro/CE in `control/n1_work/n1_out.json`.
- `control/paired_queries.parquet`, `control/g1_results.json`,
  `forward-benchmark.json`, `runtime-estimate.json`.
- `*-profile/`: log, serie RAM/VRAM, report e fallimenti preservati.
- `final-fusion-parity.json`: parità F0/joint per tutte le query.
- `tests.log`, `tests.xml`: **5 test mirati passati**.
- `training-venv-pip-check.txt`, `job-final.txt`: controlli finali.

Per una ripetizione bounded usare gli entry point e gli stessi asset/runtime,
scegliendo un output nuovo. Non rieseguire setup o richiedere allocazioni.
Gli split hanno gli SHA256 originari riportati nel manifest.
