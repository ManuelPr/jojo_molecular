# Starter / F0 / G1 — stato verificato il 22 ottobre 2026

Letti CASMI26_MASTER_PLAN.md e FASTWEB_GPU_EXPERIMENT_PLAN.md.
Slurm sacct riporta 2541 CANCELLED, fine 2026-10-22T17:27:43
(timestamp scheduler). La sessione corrente è nel 2545 su dgx-23;
il suo uso è stato esplicitamente autorizzato dall’utente in chat.
2545 RUNNING, 8 CPU, 32 GiB, 1 GPU, TimeLimit=UNLIMITED,
EndTime=Unknown: nessuna durata residua finita garantita.
Nessuna allocazione richiesta.

Quota personale NFS non determinabile: utility quota assente; df mostra
510 TiB condivisi, che non costituiscono quota personale. Prima di grandi
trasferimenti occorre ottenere la quota dal servizio storage/amministratore.

## Asset

Eseguito plan_research_downloads.py --group starter --format json.
Piano persistente: artifacts/cluster/starter-20261022/download-plan.json.
Manifest: artifacts/cluster/starter-20261022/manifest.json.
Somma dimensioni API: 4.342.989.049 byte (non spazio espanso verificato).
Train/test/sample, FPNet V5 e panel V10 tutti mancanti; nessun download
eseguito, nessun SHA256 di dati disponibile. Versioni previste nel manifest.
Le dimensioni API provengono dal config, non da una nuova interrogazione API.
CLI installata isolatamente in /tmp/casmi-kaggle-tool, senza modificare .venv.
Credenziali standard e variabili Kaggle assenti al controllo; fornita all’utente
procedura getpass per salvarle fuori dal repository, senza mostrarle nei log.

Preflight data-aware NON eseguito: train.parquet assente. Non usate fixture.

## F0 e G1

Porting F0 bloccato: sorgente Gu V492 V1 scriptVersionId=361010883 e suoi
mount storici non presenti localmente. I controlli vendorizzati v89 e
public_four_channel restano distinti; non sostituiscono il controllo 0,464.
Lo snapshot ricerca V5/V10 non certifica i mount storici. F0 richiede inoltre
asset di pipeline e simulatori non compresi nello starter.

Contratto di esportazione da applicare al porting: una riga per query,
candidato scorer e spettro, con provenienza e stadio/pruning, split, label,
score FP/ranker/library/prior, addotto reale e proxy, CE, score ICEBERG e
GLACIER con flag missing/failed, hash dati/modelli. Pool congelato condiviso
per i tre trattamenti G1; nessuna sostituzione di missing con zero.
Reference escluse per identità scorer, FPNet solo fold corrispondente escluso;
overlap non verificati degli altri pretrained esplicitamente diagnostici.

Smoke G1 NON eseguito. Copertura, MRR@25, RAM, VRAM e tempo/coppia non
misurati; nessuna stima totale numerica sostenibile. Dopo il pilot:
T_totale = T_setup + T_retrieval + N_coppie / coppie_al_secondo + T_fusione,
contando ogni CE separatamente. Fermarsi prima della run completa.
Nessun G2/G4 o submission avviato.

## Integrità split

- goal3_frozen_identities.txt: 8a1445fbe1f762c464b13364d8f6927baf72d4e7a2d8fa9be39a65ece26364b4
- goal5_prior_final_identities.txt: 3e90354780237c69cb328012edeabe0938d41993ee207e54f4c21cf5dcd58fac

Hash invariati rispetto al controllo iniziale della sessione.

## Aggiornamento dopo configurazione credenziali

Questa sezione sostituisce lo stato operativo dei blocchi sopra: autenticazione
Kaggle verificata tramite elenco file ufficiali, senza stampare il token.
CLI isolata: /tmp/casmi-kaggle-tool; la venv di training non è stata modificata.
Quota interrogata anche con quota 4.06 estratto in /tmp (nessuna installazione
sistema): `Cannot connect to RPC quota service`. Resta sconosciuta, non illimitata.

Starter COMPLETO, 4.342.989.049 byte non compressi, identico al totale API.
Train: 3.033.286.496 byte; SHA256
`9423f90ec08b941a9646b535bf0606183e86ff0c5a297978f5a70693d41bcd98`.
FPNet V5: tutti i 57 file presenti; 55/55 checksum pubblicati corrispondenti.
Panel V10 scaricato. Il manifest registra SHA256 e dimensione di ciascun file.
L'archivio FPNet V5 ha dato 404: recuperati i singoli file della stessa V5.
La CLI ha poi raggiunto HTTP 429 su GetDatasetMetadata; recupero completato
con API diretta sequenziale, senza cambiare versione. Nessun processo di
trasferimento è rimasto avviato.

Preflight con CASMI_TRAIN_PATH al vero train.parquet: PASS, 2.539.608 righe,
etichette disponibili, CUDA forward/backward e gradienti finiti sulla H100.
Report: artifacts/cluster/data-preflight-2545-20261022/preflight.json.

### Preparazione F0 e simulatori

Scaricato sorgente Gu V492: il pull con /1 ha dato 403, quello senza suffisso
ha prodotto ESATTAMENTE lo SHA256 V1 già registrato nell'inventario:
`3b05fe5620f0bfe3acb319c782761acb61c61d283d8835b415a4d671cd841aa4`.
Quindi il sorgente fissato è riproducibile; i mount storici restano non legati
alle rispettive versioni. Il metadata ricevuto elenca slug senza versioni.

Nuovo scripts/cluster/prepare_f0_source.py: controlla il pin, estrae senza
esecuzione i tre moduli engine e glb_core/glb_driver, verifica gli hash N1A
dichiarati dal sorgente e compila i moduli. Testato sul notebook reale e sul
rifiuto di un input alterato prima di scrivere output. Artefatti sotto
artifacts/cluster/f0-gu-v492-v1-prepared/, con source-manifest.json.
È preparazione del porting, NON un porting end-to-end già eseguibile.
La venv non deve essere sottoposta ai bootstrap pip del notebook originale.

Scaricato anche un sottoinsieme esplicito V6: 79 file ICEBERG/GLACIER,
128.031.297 byte dichiarati. Hash dei file presenti corrispondenti ai manifest
interni: GLACIER 38 match, ICEBERG 39 match, zero mismatch; per ciascun
pacchetto dataset-metadata.json non è incluso nel sottoinsieme/API selezionata.
Anche gl_runner.py corrisponde al pin N1 del notebook. Il manifest V6 generale
è storico e non è un inventario completo dei file V6 correnti: non usarlo da
solo per certificare tutta la versione. Non scaricati i restanti asset full.

### Prove di caricamento, non smoke G1

Input vuoto esplicito: zero candidati e zero predizioni. Dipendenze installate
solo in artifacts/cluster/simulator-load-2545-20261022/site con --target.
RDKit simulatore 2025.03.6; scorer principale 2026.03.3 invariato. Primo tentativo
GLACIER fallito per tqdm mancante, risolto con tqdm==4.67.3 nel solo sito isolato.
I runner usano i propri shim/stub per moduli assenti; nessuna parità di
predizione è stata verificata. Entrambi riportano numba=False.

| Modello | Stato CUDA load | Tempo load | RSS massimo processo | Picco VRAM allocata torch |
|---|---|---:|---:|---:|
| GLACIER | ok | 6,85 s | 1.224.208 KiB | 0,06 GiB |
| ICEBERG | ok | 6,21 s | 1.131.464 KiB | 0,03 GiB |

Numeri di solo caricamento, non dimensionamento di inferenza.
Cgroup job_2545: limite 34.359.738.368 byte, memory.peak letto
5.825.609.728 byte, zero eventi oom/oom_kill. Picco cumulativo del job,
include altri processi: non attribuibile a G1.

### Lavoro ancora necessario

F0 necessita ancora di pool strutturali/caches, full1, A+B, altri modelli e
prior PubChem completi, adattamento dei percorsi e rimozione reference per
identità, crosswalk delle esclusioni fold. Nessuna tabella F0 è stata esportata.
Il panel scaricato contiene tabelle diagnostiche preesistenti, non output del
nostro controllo: non sono state sostituite alle evidenze F0 richieste.
Il margine personale di almeno 100 GiB per gli asset full non è verificato.

G1 comparativo NON ESEGUITO: copertura, MRR identity-disjoint, tempo/coppia e
stima totale non disponibili. Non si può estrapolare throughput da input vuoto.
Overlap pretrained Full1/A+B/simulatori non risolti: reference-disjoint da solo
non certifica unseen-structure. Nessuna metrica o miglioramento inventato.
Nessuna run completa, G2/G4, submission, nuova allocazione o modifica split.
Git diff --check passato. Stato e decisioni aggiornati senza cancellare le
modifiche preesistenti dei documenti.


## Ripresa completata — 23 ottobre 2026

Risolti i blocchi operativi F0/G1 descritti sopra. Staging, porting e pilot
conclusi: proxy con maggiore copertura ma MRR peggiore, nessuna promozione.
[Report aggiornato](FASTWEB_F0_G1_RESULTS_2026-10-23.md).
