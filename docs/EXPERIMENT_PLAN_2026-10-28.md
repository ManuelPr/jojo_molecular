# Piano esperimenti H — 28 ottobre 2026

Obiettivo: passare da **0.464 (rank 959/4243)** alla fascia alta del leaderboard
entro il 14 dicembre 2026, con submission finali riproducibili ed eleggibili.
> **Revisione 28/10 pomeriggio (indicazione utente): obiettivo prime posizioni, non piccoli
> recuperi di rank.** Meno gate formali, più submission e più dati, uso pieno delle H100.
> La sezione 9 sostituisce le priorità delle sezioni 5–6: H1 resta solo come controllo leggero,
> il binario principale diventa "J" (scorer neurale nostro, grande, con dati extra).

Questo piano segue F0–G4 di [FASTWEB_GPU_EXPERIMENT_PLAN.md](FASTWEB_GPU_EXPERIMENT_PLAN.md)
e resta subordinato a `CASMI26_MASTER_PLAN.md`. Coordinamento operativo
Claude ⇄ Codex in [COLLAB_BOARD.md](COLLAB_BOARD.md).

## 1. Stato misurato (28/10/2026, 14:15 UTC)

| Voce | Valore | Fonte |
|---|---|---|
| Nostro best public | **0.464** (F0 = Gu V492, sub 57552927) | `kaggle competitions submissions` |
| Nostro rank | **959 / 4243** | CSV leaderboard scaricato |
| Primo posto | 0.513 (Savko) | leaderboard |
| Team ≥0.48 / ≥0.47 / ≥0.464 | 17 / 378 / 986 | CSV leaderboard |
| Miglior notebook pubblico | **0.477** (busyaprime m1, sub 57722897) | pagina notebook |
| Pila di team a 0.472 | ~273 | forum 753525 |
| Molecole public LB | ~125 (31% di ~400) → 1 molecola rank 2→1 ≈ +0.004 | forum 753525, notebook pubblici |

Snapshot locali (non versionati): `artifacts/public_notebook_audit_2026-10-28/`
(CSV leaderboard, 12 sorgenti notebook, `SOURCE_SHA256SUMS.txt`, metadata modello sanpier).

### Esperimenti programmati: cosa è stato fatto

| ID | Stato | Esito |
|---|---|---|
| F0 port Gu V492 | **Fatto** | LB 0.464, nuovo controllo |
| G1 GLACIER proxy + ICEBERG | Fatto solo pilot 16 query | Nessuna promozione: proxy in regressione (0.872 → 0.805) |
| G2 FPNet identity-excluded | **Non fatto** | — |
| G3 ranker finale appreso | Fatto (200 query panel) | OOF 0.982 ma LB **0.388**; versione conservativa (top1 fisso, coda riordinata) **0.451**. Respinto |
| G4 generazione | Non fatto (condizionale) | — |

Dal 23/10 nessun nuovo esperimento: cinque giorni in cui il pubblico è passato da 0.464 a 0.477.

## 2. Cosa ha imparato il campo (evidenze pubbliche verificate)

1. **Una sola linea di pipeline.** 103 dei 112 notebook ≥0.460 montano gli asset v4g di Dmitrii.
   Da 0.465 a 0.477 i guadagni vengono tutti da un **re-ranking neurale "leader-safe"**:
   punteggio `1/(3+b) + w/(3+n)` (b = rango pipeline, n = rango neurale), con `w_top = 0.25`
   per il rango 1 e `w_mid = 0.75` per i ranghi 2–25, più un fragment check MetFrag-lite
   (Spectral Parallax) che può spostare solo il leader.
2. **Il rango 1 decide.** Dare più peso al neurale sul rango 1 crolla: w_top 0.50 → 0.448,
   1.00 → 0.359. Il nostro G3 (0.388) ha fallito per lo stesso motivo.
3. **Il modello neurale chiave è minuscolo** (`sanpier/casmi-spectrum-model-v1`: transformer
   3 layer × 192, 12 MB, 16×500 step, holdout molecolare casuale *non* scaffold-disjoint,
   refit su tutto il train). La versione addestrata più a lungo (40×2000 step) **perde 0.019 sul LB**,
   7 FPNet riaddestrati da alexchilton perdono tutti (0.418–0.443) pur migliorando offline.
   → La metrica offline di tutti (anche la nostra, vedi G3) non predice il LB.
4. **Il LB pubblico è rumoroso**: SE ≈ 0.04 su 125 molecole; un guadagno nullo appare +0.005 per
   caso nel 40% dei casi se le pipeline concordano all'85%. Gli sweep di manopole sono rumore.
5. **I primi 10 team non hanno notebook pubblici.** Il distacco 0.477 → 0.513 viene da qualcosa
   che il pubblico non ha.
6. **Classe 3 con generazione a regole**: guadagno atteso +0.004–0.010 (forum 753400). Bassa priorità.

## 3. Dati e modelli aggiuntivi consentiti (risposte host verificate)

| Risorsa | Stato regole | Valore atteso | Note |
|---|---|---|---|
| **ICEBERG PubChem atlas** (91,4 M strutture, pesi NIST'23, NIST structures escluse) | **Consentito** come predizioni precalcolate in dataset privato + codice di download (host, 28/10, topic 745134) | **Alto**: forward model più forte dei pesi MassSpecGym usati da tutti i notebook pubblici; quasi nessuno lo usa | Download per formula via WebDAV `https://iceberg-ms.mit.edu/dav/public/{h_plus,h_minus}/C*/O*/H*/<formula>.mgf`; richiede account web registrato (azione dell'utente). Energie/addotti inclusi da verificare |
| Membership list atlas (InChIKey14) | Consentito | Medio: feature di prior | Leggera |
| **MIST** checkpoint Zenodo 23303289 (MIT, MassSpecGym; variante aug con GLACIER) | Consentito (host 26/10) | Medio: ranker spettro→fingerprint indipendente | |
| MS2DeepScore 2.0, FIORA-OS | Consentiti (addestrati solo su librerie pubbliche) | Basso–medio; FIORA neg-mode blend −0.014 offline (alexchilton) | |
| DreaMS SSL backbone | Consentito, fine-tuning con nostro codice | Medio–alto come encoder spettrale per H5 | Pesi fine-tuned altrui non consentiti senza codice |
| FRIGID checkpoint (CC BY-NC) | Consentito | Basso (classe 3) | |
| TabPFN v2/2.5 | Consentito | Basso–medio per ranker su poche righe | |
| Conteggi PubChem CID-PMID / Patent / SID | Consentiti come feature | Medio per prior | |
| LOTUS, NPAtlas, COCONUT recente, PubChemLite | Consentiti | Medio: copertura candidati NP | |
| Release più recenti delle librerie del train (GNPS, MassBank, MoNA, MSnLib…) | Consentite ("more recent updates", host 27/10) | Da misurare: nuovi spettri di riferimento = classe 1 in più | Diff per InChIKey14 contro train |
| Relazioni fra spettri di test diversi | Consentite (host 26/10) | Basso (−0.003 offline per altri) | |
| NIST, SIRIUS/CSI:FingerID | **Vietati** | — | |

Correzione massa elettrone: applicata **solo al test nascosto** (m/z positivi −0.000548 Da),
non a train né a Enveda-180 Zenodo. Va verificato che la nostra pipeline non la applichi due
volte né la ignori nelle finestre ppm (H8).

**Rischio conformità:** l'host può rimuovere dal LB submission non riproducibili. Il modello
sanpier v1 dichiara training "riproducibile con config e source", ma il codice di training
pubblico non è ancora stato localizzato da noi. Verificarlo prima di sceglierlo per le finali (H0).

## 4. Strategia

Due binari in parallelo:

- **Binario A — controllo competitivo.** Portare la ricetta pubblica 0.477 nella nostra
  infrastruttura come controllo `C477`, con export delle evidenze per candidato. Serve come
  base e come submission finale "sicura". Non è un risultato di ricerca.
- **Binario B — differenziatori.** Solo componenti che il pubblico non ha: atlas ICEBERG
  NIST-trained, encoder spettrale addestrato da noi con validazione onesta, ranker indipendenti
  (MIST), recall dei candidati. Ogni componente entra prima nei ranghi 2–25 (leader-safe), e
  tocca il rango 1 solo con un gate di precisione misurato.

Il prerequisito comune è **H1: una validazione che predica il LB**. Senza di essa ripetiamo G3.

## 5. Esperimenti

Priorità: P0 subito, P1 dopo H1, P2 se c'è margine. GPU = H100 cluster salvo indicazione.

| ID | Pri | Esperimento | Risorse | Gate / evidenza di decisione |
|---|---|---|---|---|
| **H0** | P0 | Port di busyaprime m1 (0.477) → `C477`: sorgenti e dataset con hash, esecuzione locale sul cluster su placeholder, export `frozen_candidate_evidence` + score neurali + output fragment check. Verifica codice di training dei pesi sanpier (eleggibilità). | Kaggle T4 per 1 submission; cluster CPU/GPU per replay | Parità CSV con il notebook pubblico sulle 12 query visibili; LB atteso 0.477 ± rumore. Richiede approvazione utente per la submission |
| **H1** | P0 | **Validazione calibrata sul LB.** Coorte "hidden-like": molecole Enveda-180 timsTOF tipo NP, strutturalmente disgiunte, con proxy tipo 1 (reference legittime), tipo 2 (tutte le reference della struttura rimosse, incluse esterne) e tipo 3 (struttura rimossa da pool e cache). Poi replay offline delle varianti pubbliche con LB noto: V0 0.465, V1 0.466, V2 0.468, w_mid 1.00 0.470, CUSTOM 0.472, m1 0.477, modello long 0.453, NX reranker 0.414, nostri G3 0.388 e G3-cons 0.451. | H100: pipeline ~2,7 h / 200 query (stima F0); il re-ranking è riutilizzabile dalla cache | Spearman offline↔LB ≥ 0.7 sulle ≥8 varianti e i tre crolli (0.414, 0.388, 0.453) riconosciuti come tali. Se fallisce: cambiare coorte/esclusioni, non i modelli |
| **H2** | P0 | Riaddestrare il modello sanpier v1 con la nostra esclusione H1 (stessa config, 3 seed), per avere uno scorer neurale senza esposizione sulla coorte H1 | 1 H100, ~1–3 h per seed | Riproduce le metriche pubbliche sul suo holdout; serve a H1 per varianti leak-free |
| **H3** | P0 (avvio) / P1 (integrazione) | **ICEBERG atlas NIST-trained.** (a) l'utente registra l'account; (b) scarico per formula dei candidati della coorte H1; (c) cosine/entropy fra spettri query e predetti; confronto contro ICEBERG/GLACIER MassSpecGym sullo stesso pool tipo 2; (d) stima dimensione per l'universo di formule da spedire (formule dei candidati PubChem-tier 157–1159 Da) | Rete + disco NFS; CPU; zero GPU per scoring | Rango della truth migliore dei forward attuali, con IC95 appaiato > 0; dimensione dataset Kaggle compatibile (privato). Poi ingresso leader-safe nei ranghi 2–25 |
| **H4** | P1 | Ranker indipendenti aggiuntivi nel RRF dei ranghi 2–25: MIST (+aug), MS2DeepScore 2.0, scorer H2 multi-seed | 1 H100 inferenza | Delta H1 appaiato positivo; nessuna perdita sul controllo tipo 1 > 0.002 |
| **H5** | P1 | **Encoder spettrale nostro**: DreaMS SSL backbone o transformer sanpier allargato, fine-tuning con (i) aggregazione multi-spettro per molecola, (ii) hard negative stessa formula, (iii) sovrapesatura del dominio timsTOF/Enveda-180, (iv) early stopping sulla coorte H1, non su holdout casuale | 1–2 H100 (DDP se il job 2658 parte), segmenti da 4 h con checkpoint | Batte H2 su H1 tipo 2 con IC95 > 0. Lezione da "modello long −0.019": il criterio è H1, non la loss di validazione |
| **H6** | P1 | Gate del rango 1: per ogni sorgente di evidenza (fragment check, atlas, neurale, MIST) misurare su H1 la precisione dei cambi di leader quando contraddice la pipeline. Regola: un cambio di leader è ammesso solo dove la precisione misurata supera 0,5 | CPU sulla cache H1 | Guadagno netto atteso positivo su rango 1 sia tipo 1 sia tipo 2 |
| **H7** | P1 | Fusione appresa *vincolata* (LightGBM/TabPFN) solo sui ranghi 2–25, addestrata sulla coorte H1 con split per identità; mai sul panel NP pubblico | CPU | Batte RRF w_mid 0.75 su H1; G3-cons ci ricorda che un ranker addestrato male peggiora anche la coda |
| **H8** | P0 | Audit economico: recall della truth nel pool per proxy tipo 1/2/3 e per sorgente; perdite al pruning; correzione massa elettrone; addotti non supportati | CPU | Tabella di dove si perdono i punti; orienta H3/H9/H10 |
| **H9** | P2 | Release recenti di GNPS/MassBank/MoNA/MSnLib: diff contro train per InChIKey14, nuove reference e nuove strutture candidate | Rete + CPU | Numero di nuove strutture/reference nel range di massa; aggiunta alla libreria solo con controllo tipo 1 |
| **H10** | P2 | Classe 3: analoghi/FRIGID solo se H8 mostra truth assenti dal pool in una quota rilevante | GPU per scoring | Copertura tipo 3 senza regressione tipo 1 |
| **H11** | P2 | Propagazione fra spettri di test (molecular networking) | CPU | Delta H1 > 0 |

## 6. Ordine e parallelismo

```
Giorno 0-2   H0 port C477 ──┐            H8 audit recall (CPU)
             H3a account atlas (utente)   H1 costruzione coorte + esclusioni
Giorno 2-5   H2 riaddestramento (GPU-1)   H1 pipeline sulla coorte (GPU-2)
             H3b-c download/scoring atlas (rete/CPU)
Giorno 5-7   H1 calibrazione LB → GO/NO-GO della metrica offline
Giorno 7-20  H5 encoder (GPU-1,2)  H4 ranker extra  H6 gate rango 1  H3d integrazione
Giorno 20-40 integrazione, 1-2 submission/settimana per componente validato, H9/H10 se giustificati
Ultima sett. congelamento, rehearsal 400 completo, selezione finali
```

Selezione finali (2 slot): una submission **C477 + soli componenti validati su H1**, una
**diversa** (es. con atlas/encoder nostro anche sul rango 1 tramite gate H6). Non scegliere
in base a differenze public ≤ 0.005.

## 7. Risorse GPU (verificate 28/10)

- **Job 2545**, dgx-23, 1×H100, 8 CPU, 32 GiB RAM, senza limite di tempo. La GPU è **condivisa**
  in questo momento con un training di un altro progetto dell'utente (`name-that-llm`,
  ~25 GB VRAM, 100% utilizzo). Coordinare prima di caricarla.
- **Job 2658**, 2×H100, 8 CPU, 64 GiB, **PENDING (Priority)**, sottomesso oggi 14:44.
- Cluster `ais4sum`: 8 nodi × 8 H100 = 64 GPU, **tutte allocate** al momento; fairshare 0.35.
  Altre allocazioni restano in coda finché non si liberano nodi; ogni nuovo `sbatch` richiede
  l'ok dell'utente.
- Kaggle: T4 per commit/submission; quota settimanale non leggibile (MCP non autenticato).
  Il rerun nascosto dura ore: max ~1–2 submission di ricerca al giorno realistiche.

Assegnazione proposta quando il 2658 parte: GPU-1 training (H2 → H5), GPU-2 pipeline/inferenza
(H1, H4); il job 2545 resta per CPU/replay leggeri finché è condiviso.

## 8. Regole che restano valide

Nessuna submission, upload di dataset/modelli, registrazione di account esterni o nuova
allocazione Slurm senza ok esplicito dell'utente per quella specifica azione. Split congelati
invariati; nuovi split versionati a parte. Risultati misurati separati dalle ipotesi.
Ogni promozione richiede IC95 appaiato > 0 su H1 e nessuna perdita > 0.002 sul controllo tipo 1.

## 9. Binario J — submission per le prime posizioni (revisione 28/10)

Leva principale: lo slot neurale della pipeline 0.477 è l'unico componente che ha mosso il
LB da 0.465 a 0.477, ed è un modello da 3 M parametri addestrato 8k step con negativi presi
**solo dal train**. Ipotesi di lavoro (dall'evidenza pubblica: il modello long ha diagnostico
offline 0.718 contro 0.484 ma LB −0.019): il modello impara a separare strutture del train,
mentre i candidati sbagliati del test sono soprattutto strutture PubChem fuori dal train
(classi 2/3). Il nostro scorer viene addestrato proprio su quella distinzione.

| ID | Cosa | Stato 28/10 |
|---|---|---|
| J0 | Fork privato del 0.477 (`mperni/casmi26-c477-public-port` v1) e submission automatica | notebook in esecuzione; finalizer `scripts/submit_kernel_when_ready.py` attivo |
| J1 | Cache di training sanpier (`jm_prepare.py`, strutture in parallelo, libreria/strumento conservati per spettro) | job CPU Slurm 2660 in corso |
| J2 | Banca negativi PubChem: per ogni formula del train 16 isomeri più documentati + 16 casuali, **assenti dal train** (`jm_build_pubchem_bank.py`) | in coda dopo J1 nello stesso job |
| J3 | `train_jm.py`: negativi PubChem nel softmax, 1–3 spettri per molecola mediati come in inferenza, termine fingerprint nel softmax, sovracampionamento timsTOF, holdout Enveda-180 con candidati realistici (isomeri train + PubChem). Config `jm_small` (dimensioni sanpier) e `jm_base` (8×512, ~30 M parametri) | codice pronto; job GPU 2662 in coda (dipende da J1/J2) |
| J4 | `build_jm_submission.py`: dataset privato con il bundle + clone C477 con `MODEL_PINS` aggiornati → submission | pronto |
| J5 | Atlas ICEBERG (pesi NIST'23): endpoint pubblico per formula **senza login** (`/download_mgf?formula=`), 20 energie × struttura, [M+H]+; ~40 KB/struttura, ~10 MB/s. Uso 1: centinaia di migliaia di strutture PubChem/NP fuori dal train come **dati di training simulati** per J3. Uso 2: evidenza diretta per le formule NP frequenti | downloader `scripts/cluster/atlas_download.py`, lista formule prioritaria (Enveda prima) |
| J6 | Ensemble di più seed/architetture dentro una sola `model.py` (stessa interfaccia `Scorer`) | da fare dopo i primi LB di J3 |
| J7 | Pesi della fusione (w_top/w_mid) e fragment check ricalibrati per il nostro scorer, solo se J3 cambia il comportamento | dopo J3 |

Cadenza: ogni modello che batte sanpier v1 sul nostro holdout realistico va in submission
(1–3 al giorno). Il LB pubblico resta rumoroso (±0.004 per molecola): si promuovono solo salti
netti o conferme ripetute.


## 10. Evidenza J5/J5b — 2026-10-28 16:11, Codex

Pipeline dati implementata e testata; primo lotto atlas esterno pronto: 16.995 spettri / 5.665 identità / 15 formule, overlap zero con il train canonico completo. Report e comandi: [J5 atlas](J5_atlas_data_2026-10-28.md). Questo abilita l’ablation J3+atlas; nessun miglioramento MRR ancora misurato. Espandere la raccolta dopo il confronto sullo stesso holdout.


## Evidenza J5c — 2026-10-28 22:23

[Report J5c](J5c_atlas_ranking_2026-10-28.md): sul diagnostic train-exposed, atlas nella coda JM dà delta MRR+0.00321, IC95[-0.00090,+0.00827], quindi non promosso. Catalogo completo15formule recupera19 truth perse dal campione training400/formula (74/142 vs55/142). Questo non sostituisce H1. Segue proposta K2 di Claude: replay C477 con JM su holdout JM fisso e audit contaminazione dei componenti pubblici.
