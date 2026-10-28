# J5/J5b — dati atlas pronti per l'ablation dello scorer

Codex, 28 ottobre 2026. Branch `codex/j5-atlas-data`.
Coordinamento con Claude in `docs/COLLAB_BOARD.md`; training J1–J3 resta di Claude.

## Risultato misurato

Sono disponibili **16.995 spettri simulati, 5.665 identità canoniche, 15 formule** in
`data/fastweb/iceberg_atlas/h_plus_external_v2/*.parquet` (5.488.036 byte complessivi).
Il confronto con tutte le **274.195 identità** di
`data/fastweb/jm_cache_v1/train_molecules.parquet` ha overlap **zero**.
L'hash della tabella di esclusione è
`861e148133635d293d316f833d327ced9f37e2865dabdc52ca3c2b1df2fbce6c`.

| Misura | Valore | Artifact |
|---|---:|---|
| Spettri MGF letti nelle 15 formule | 196.000 | `artifacts/J5/pilot_conversion_v2.json`, `np_batch_conversion.json` |
| Identità eleggibili prima del campionamento | 9.745 | stessi manifest |
| Identità non selezionate dal cap di training | 4.007 | `np_batch_conversion.json` |
| Identità con normalizzazione non idempotente escluse | 3 | manifest degli shard |
| Identità / spettri dopo conversione | 5.735 / 17.205 | `artifacts/J5/batch_quality_audit.json` |
| Identità già nel train, successivamente rimosse | 70 | `artifacts/J5/full_train_overlap.json` |
| Identità / spettri consegnati per training esterno | 5.665 / 16.995 | `artifacts/J5/external_training_shards.json` |
| Overlap finale col train | 0 | `artifacts/J5/external_filter_audit.json` |
| Test automatici | 36 passati | `artifacts/J5/tests.txt` |

Il controllo sulle strutture train con le stesse formule, normalizzate direttamente dai
loro SMILES, concorda con il confronto sulla tabella completa: 70 overlap.
Tutte le righe convertite passano le funzioni `peaks` e `metadata` del codice sanpier.
La conversione delle 13 formule C29/C30 ha impiegato circa 92 secondi con 2 processi CPU;
il pilot delle altre due formule circa 90 secondi, con lo stesso numero di processi.
Non è stato misurato alcun incremento MRR e non è stato avviato un training da Codex.

## Implementazione

- `src/casmi26/atlas.py`: parser MGF in due passate; memoria dei picchi limitata alle
  acquisizioni selezionate; somma dei picchi con massa identica senza ulteriore arrotondamento;
  controllo dei metadati, formula e addotto `[M+H]+`; identità ufficiale RDKit 2026.03.3.
- `scripts/cluster/atlas_to_parquet.py`: selezione deterministica di massimo 400 identità
  per formula, mediante hash di seed e identità canonica; tre energie ai quantili
  0,25/0,50/0,80 della griglia; esclusioni opzionali; manifest e ripresa con controllo hash.
- `scripts/cluster/atlas_download.py`: download streaming, cap applicato anche ai byte
  effettivi senza Content-Length, controllo integrità MGF/gzip, file temporanei,
  hash, URL, timestamp e dimensioni raw/compresse distinte nei nuovi record del manifest.
- `scripts/cluster/audit_atlas_shards.py`: controllo hash, identità, duplicati,
  provenienza simulata, feature sanpier e overlap con il train per formula.
- `scripts/cluster/filter_atlas_shards.py`: derivazione di shard separati escludendo
  identità canoniche, con hash degli shard genitori e della lista di esclusione.

Schema compatibile con il preparatore: `normalized_smiles`, `smiles`, `ms2_mzs`,
`ms2_normalized_intensities`, `precursor_mz`, `adduct`, `ionization_mode`,
`collision_energy_ev`, `ingest_lib`, `instrument_type`. Sono presenti anche identità
canonica e originale atlas, formula, molecule/spectrum ID e `is_simulated`.

Il downloader era già attivo per opera di Claude e non è stato interrotto: quel processo
continua a usare il codice caricato prima delle modifiche. La nuova versione è stata
verificata con un download pubblico reale di C27H30O16: **10.819.070 byte raw,
4.140 spettri**, limite 15 MB; ricevuta in `artifacts/J5/live_download/receipt.json`.
All'inventario intermedio erano già presenti 627 formule / 3.251.780.423 byte compressi;
475 formule erano state saltate dal downloader originale per il limite di dimensione.
Lo snapshot è `artifacts/J5/download_inventory.json`, non un totale finale della raccolta.
Fonte dell'atlante: <https://iceberg-ms.mit.edu/>. Il sito descrive predizioni PubChem
ed esclusione delle strutture NIST'23; valgono le verifiche regolamentari registrate
nel piano esperimenti. Il tentativo di rileggere la discussione Kaggle via web in questa
sessione non è riuscito: nessuna nuova autorizzazione regolamentare è stata dedotta.

## Problema scientifico trovato e corretto

Per 11.040 spettri delle 15 formule, l'identità atlas grezza cambia dopo la normalizzazione
ufficiale. Non usare quindi il solo header INCHIKEY per deduplicazione/esclusioni.
Inoltre, i limiti standard di enumerazione RDKit rendono tre identità selezionate non
idempotenti: canonicalizzare nuovamente lo SMILES esportato cambierebbe ancora la chiave.
Questi casi sono esclusi e registrati, senza alterare i default della metrica.
Un caso reale è coperto da test di regressione:
`YYZRAUMZRSHSLQ` diventerebbe `HNHGBIVMXGITIJ` nel preparatore.

I primi artifact `pilot_conversion.json` e `identity_audit.json` descrivono il pilot
prima della correzione; gli shard pilota sono stati rigenerati. I riferimenti correnti
sono `pilot_conversion_v2.json`, `batch_quality_audit.json` e
`external_training_shards.json`.

## Riproduzione e passaggio al training

```bash
.venv/bin/python -m pytest tests/unit/test_atlas.py tests/unit/test_atlas_download.py tests/unit/test_chemistry.py -q

.venv/bin/python scripts/cluster/atlas_to_parquet.py \
  --only-formulas artifacts/J5/pilot_formulas.txt --workers 2 \
  --report artifacts/J5/replay_pilot.json
.venv/bin/python scripts/cluster/atlas_to_parquet.py \
  --only-formulas artifacts/J5/np_batch_formulas.txt --workers 2 \
  --report artifacts/J5/replay_np_batch.json

.venv/bin/python scripts/cluster/audit_atlas_shards.py \
  --src data/fastweb/iceberg_atlas/h_plus_parquet_v2 \
  --train data/fastweb/competition/train.parquet \
  --report artifacts/J5/replay_quality.json

# Il filtro richiede una directory di output nuova.
.venv/bin/python scripts/cluster/filter_atlas_shards.py \
  --src data/fastweb/iceberg_atlas/h_plus_parquet_v2 \
  --out data/fastweb/iceberg_atlas/h_plus_external_replay \
  --exclude-identities data/fastweb/jm_cache_v1/train_molecules.parquet \
  --report artifacts/J5/external_replay.json
```

Claude può usare la lista `external_paths` in `artifacts/J5/training_handoff.json`
per preparare una **cache nuova** con il suo preparatore; la cache J1 in costruzione
resta separata. Tenere fisso lo split del controllo e rendere esplicito il peso dei
positivi sintetici nel sampler. Rimuovere anche eventuali identità di futuri holdout
esterni assenti dal train attuale. Il solo schema compatibile non prova l'integrazione
del trainer: quella verifica è il passo successivo del proprietario J3.

Il campione di 15 formule non rappresenta l'universo chimico né copertura completa
per evidence retrieval. Il cap 400 è un campionamento per training: gli MGF completi
restano disponibili per scoring o campioni più grandi. Le formule saltate per dimensione
richiedono un recupero pianificato; non confondere `too_large` con assenza nell'atlante.
La priorità scientifica è confrontare J3 contro J3+atlas sul medesimo holdout.
