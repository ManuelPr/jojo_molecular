# Verifica allocazione Fastweb — 2026-10-22

Allocazione esistente Slurm **2541**, nodo `dgx-23`, job VS Code. Nessuna
nuova allocazione o submission Kaggle. Split congelati preservati.

## Risorse verificate

- Una NVIDIA H100 80GB HBM3, 81.559 MiB esposti da NVIDIA-SMI; inizialmente
  0 MiB occupati, utilizzo 0%. Driver 580.178.04, CUDA massima driver 13.0.
- 8 CPU logiche assegnate, affinity 9-10,64-65,121-122,176-177.
  Host: due Xeon Platinum 8480C, 112 core fisici / 224 thread.
- RAM job **32 GiB**, limite cgroup 34.359.738.368 byte; i circa 2 TiB
  mostrati da `free` appartengono all'host e non al job.
- Scheduler: `TimeLimit=UNLIMITED`, `EndTime=Unknown`, `Deadline=N/A`.
  `SLURM_JOB_END_TIME` contiene un timestamp del 2027: non e una scadenza
  confermata da Slurm e non va usato come garanzia di disponibilita.
- Repository su NFS `/home/mpernigotto/jojo_molecular`, circa 511 TiB liberi
  condivisi; quota personale non verificata. `/raid` e locale al nodo,
  circa 28 TiB liberi, non scelto come destinazione persistente.

## Ambiente e persistenza

Python di base `/usr/bin/python3`, versione 3.12.3, inizialmente senza torch
e senza ensurepip. Prima esecuzione dello setup fallita per ensurepip assente.
Creato `.venv` con virtualenv e `--system-site-packages`, quindi rieseguito
`scripts/cluster/setup.sh`. Virtualenv bootstrap scaricato in `/tmp`, ambiente
definitivo sul NFS. NVIDIA-SMI nel sandbox non vede il driver; il controllo
fuori sandbox sulla stessa allocazione rileva correttamente la GPU.

Setup concluso con successo. Ambiente risolto: PyTorch 2.14.1 (build CUDA
13.0), RDKit 2026.3.3, NumPy 2.5.4, pandas 3.1.0, PyArrow 23.0.1,
scikit-learn 1.9.1, LightGBM 4.7.0. `pip check` passato. Il comando richiesto
`scripts/cluster/run.sh preflight` e passato fuori sandbox, con vero
forward/backward CUDA e gradienti finiti, senza fallback CPU. Report
`preflight.json`, log `preflight.log`, installazione `setup.log`, versioni
`requirements-resolved.txt` nella directory di evidenze sotto indicata.

Percorsi persistenti relativi al repository:

- Ambiente: `.venv/`.
- Evidenze: `artifacts/cluster/fastweb-2541-20261022/`.
- Dati da predisporre: `data/train.parquet` (attualmente assente).
- Risultati Goal 3 futuri: una directory nuova sotto `artifacts/cluster/`.

## Dati e prossimo esperimento

Nessun parquet o peso `.pt`, `.pth`, `.ckpt`, `.safetensors` trovato nella
home personale, esclusi cache, venv e directory VS Code. Nessun asset CASMI
nello spazio di gruppo `/work/ai-safety4sum`, vuoto. Non e una ricerca esaustiva
su tutti i filesystem condivisi del cluster. I 16 dataset fissati in
`configs/flexon_v89_assets.json` non risultano predisposti nel checkout;
mancano anche i pesi ICEBERG, GLACIER, FPNet e DreaMS.

Goal 3 **non eseguito**, per assenza di `train.parquet`; nessun tempo,
picco di memoria o risultato scientifico di training misurato. Non richiede
i 16 asset v89. Quando il parquet ufficiale sara predisposto, usare:

```bash
export CASMI_TRAIN_PATH="$PWD/data/train.parquet"
export CASMI_OUTPUT_DIR="$PWD/artifacts/cluster/goal3-fastweb-2epochs"
bash scripts/cluster/run.sh goal3 --fingerprint-epochs 2 --bootstrap-samples 50
```

L'esecuzione CUDA deve avvenire con accesso al dispositivo dell'allocazione.
Conservare log e misurare wall time, RSS e picco VRAM durante il run.
Hash SHA256 di `configs/goal3_frozen_identities.txt` prima delle verifiche:
`8a1445fbe1f762c464b13364d8f6927baf72d4e7a2d8fa9be39a65ece26364b4`.

## Validazione del nuovo ranker finale

Servono dati etichettati e asset/versioni della pipeline competitiva reale,
adattatori portabili per i suoi percorsi e simulatori, e tabelle per query e
candidato con identita scorer, provenienza, evidenze e label. Conservare gli
split congelati; escludere le identita delle query dalle reference per il
protocollo tipo 2 mantenendole nei cataloghi, affiancando controlli library.
Documentare overlap dei pretrained e tenere separata la coorte sealed.
Misurare recall prima/dopo pruning e rango prima/dopo fusione; addestramento e
calibrazione solo sul development. Goal 3 verifica la pipeline esistente e
non costituisce questa validazione o una replica del public 0,440.

## Test finali

`OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 .venv/bin/python -m pytest tests/unit tests/integration -m 'not real_data'`
ha concluso con **252 passed, 2 skipped, 1 deselected in 64,86 s**.
I due skip dipendono dall'artifact grande Goal 4 non incluso nel checkout;
il test real-data e escluso. Inclusi test PyTorch e integrazione Goal 3 su
fixture sintetiche; questi non misurano performance sui dati ufficiali.
Un FutureWarning segnala la futura migrazione dell'API GradScaler, senza
fallimenti. Log completo `tests.log` e report JUnit `tests.xml` persistenti.
Hash split finale identico a quello iniziale. `git diff --check` passato.
