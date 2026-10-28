# J5c — evidenza atlas e perdita di copertura dovuta al campionamento

Codex, 28 ottobre 2026, branch `codex/j5c-atlas-scoring`.
Il confronto è terminato su CPU. **Non promuovere la fusione atlas–JM** con queste
sole evidenze: il piccolo delta sul modello JM ha IC95 che include zero, e la coorte
è esposta al training. È stato invece verificato e risolto, per le 15 formule del
pilot, il problema di riusare un campione di training come catalogo di ranking.

## Protocollo e limiti

- 142 molecole, 15 formule, selezionate dai dati di training della competizione.
- Solo `[M+H]+` in modalità positiva; almeno 3 picchi dopo pulizia/rimozione precursore.
- Massimo 4 acquisizioni per molecola, con deduplicazione degli input spettrali e
  selezione deterministica distribuita sulle sorgenti. Quando disponibili, si usano
  soltanto le acquisizioni `enveda-np-examples` della molecola.
- Formula nota usata per selezionare il pool: **diagnostica con formula oracle**,
  non inferenza end-to-end sul test.
- Pool congelato dalle 15 shard J5 v2: 206–400 strutture per formula. Nessuna truth
  inserita a posteriori. Le identità assenti contribuiscono zero alla MRR.
- Cosine con matching greedy uno-a-uno, intensità sqrt, tolleranza 0,02 Da,
  massimo 128 picchi; rimozione ±0,5 Da attorno al precursore di query e reference.
  Nessuna correzione della massa dell'elettrone applicata al train.
- Tre energie simulate per candidato: confronto max-CE e nearest-CE (energia ignota
  → max); media degli score tra acquisizioni. Parametri fissati prima del benchmark.
- RRF della coda: `1/(3+rank_neural) + 0.25/(3+rank_atlas)`, primo candidato
  del neurale preservato. Non è la pipeline C477 e non ne misura la performance.
- **Tutte le 142 identità sono nel training di sanpier e JM-base**; nessuna è nel
  holdout JM da 9.092 identità. L'overlap con il training ICEBERG non è determinato.
  Artifact: `artifacts/J5c/query_exposure.json`.
- Le sole 3 query Enveda-NP eleggibili sono tutte assenti anche dai file atlas raw.
  Quindi **nessuna conclusione predittiva sul dominio Enveda-NP** è supportata.

## Ranking misurato sul campione congelato

55 truth sono presenti nel pool, 87 assenti. MRR@25:

| Metodo | Tutte le 142 molecole | Solo 55 truth presenti |
|---|---:|---:|
| Sanpier v1 pubblico | 0,014978 | 0,038671 |
| Sanpier + atlas nella coda | 0,017379 | 0,044868 |
| JM-base, checkpoint 12k | 0,030063 | 0,077616 |
| JM-base + atlas nella coda | 0,031307 | 0,080828 |
| Atlas max-CE | 0,038565 | 0,099568 |
| Atlas nearest-CE | 0,032589 | 0,084139 |

Il delta JM-base+atlas − JM-base sulle 55 coperte è **+0,003212**, bootstrap
appaiato per molecola, 5.000 campioni, IC95 **[−0,000897; +0,008265]**.
Sulle 142 complessive: **+0,001244**, IC95 **[−0,000383; +0,003165]**.
Atlas risolve un errore top-1 del neurale, ma questo singolo caso non giustifica
un cambio del leader in produzione. I punteggi assoluti restano bassi.

Fonti dei risultati:

- `artifacts/J5c/full_v1/results.json`: confronto con sanpier.
- `artifacts/J5c/jm_base_replay/results.json`: confronto con JM-base.
- `molecule_results.csv`, `candidate_evidence.parquet` nei rispettivi run.
- `artifacts/J5c/full_v1/queries.parquet`: acquisizioni effettive e provenienza.

JM-base è valutato mediante replay degli **stessi candidati, query e score atlas**.
La verifica con pesi/config sanpier attraverso il codice modello JM restituisce
**differenza massima degli score 0,0** (`artifacts/J5c/replay_parity/results.json`).
I pesi pubblici sono verificati contro SHA upstream; il checkpoint JM e i sorgenti
sono identificati dagli hash dei manifest. Runtime: circa 92 s per il confronto
completo sanpier/atlas, 80 s per il replay JM, su CPU (2 thread Torch).

## Copertura: campione di training e catalogo completo

L'audit degli MGF originali normalizza gli SMILES secondo la metrica e distingue:

| Stato della truth | Molecole |
|---|---:|
| Presente nel campione v2 | 55 |
| Presente nel raw ma persa nel campione | 19 |
| Assente nei file raw scaricati per quella formula | 68 |

L'assenza nel file non dimostra assenza da PubChem né impossibilità di generazione.
Non attribuiamo queste 68 assenze a NIST senza una membership verificata.

È stato materializzato un catalogo separato:
`data/fastweb/iceberg_atlas/h_plus_ranking_full15_v1/`.
Contiene **9.740 identità / 29.220 spettri / 15 formule**. Il cap impostato a 100.000
non elimina alcuna struttura nelle formule osservate; tutti i manifest registrano
`cap_dropped_structures=0`. Cinque identità non idempotenti vengono escluse dai
controlli già definiti in J5; nessuna delle 19 truth recuperabili è persa.

L'audit del catalogo materializzato conferma **74/142 truth**: recall **52,11%**,
contro **38,73%** del campione. Sono recuperate esattamente 19 identità senza
inserimenti dipendenti dalla truth. **La MRR sul catalogo completo non è stata
misurata**: più candidati possono rendere il ranking più difficile.

Artifact: `artifacts/J5c/coverage_v1/coverage.json`, `coverage_by_molecule.csv`,
`full_pool_conversion.json`, `full_pool_audit.json`. Sono verificati hash, conteggi,
assenza di cap loss, picchi finiti/ordinati e presenza effettiva delle truth.

## Codice e riproduzione

- `src/casmi26/atlas_ranking.py`: preprocessing, cosine, aggregazione CE, ranking
  deterministico, RRF con protezione del leader, bootstrap appaiato.
- `scripts/cluster/benchmark_atlas_ranking.py`: benchmark pubblico a pool fisso.
- `scripts/cluster/replay_atlas_neural.py`: replay con checkpoint JM sul benchmark congelato.
- `scripts/cluster/audit_atlas_coverage.py`: audit raw vs campione.
- `tests/unit/test_atlas_ranking.py`: parità cosine con implementazione di riferimento,
  matching ambiguo, precursor removal, CE, aggregazione, tie, leader e bootstrap.

```bash
.venv/bin/python -m pytest tests/unit/test_atlas_ranking.py tests/unit/test_spectral_evidence.py -q
# 19 passati; separatamente 17 passati con test_atlas.py.

# Ogni benchmark/replay richiede una directory nuova.
.venv/bin/python scripts/cluster/benchmark_atlas_ranking.py --out artifacts/J5c/reproduce
.venv/bin/python scripts/cluster/replay_atlas_neural.py \
  --benchmark artifacts/J5c/reproduce --bundle artifacts/jm/base_s1_local_snap12k \
  --out artifacts/J5c/reproduce_jm
.venv/bin/python scripts/cluster/audit_atlas_coverage.py \
  --benchmark artifacts/J5c/reproduce --out artifacts/J5c/reproduce_coverage

.venv/bin/python scripts/cluster/atlas_to_parquet.py \
  --only-formulas artifacts/J5c/formulas.txt \
  --out data/fastweb/iceberg_atlas/h_plus_ranking_full15_v1 \
  --max-structures 100000 --workers 2 --report artifacts/J5c/reproduce_pool.json
```

## Decisioni e seguito

1. **Non promuovere** la fusione testata a submission, né tararne ulteriormente i pesi
   su questa coorte esposta al training.
2. Conservare un catalogo di scoring separato dal campione/filtraggio per training.
   In particolare, le shard `external_v3` escludono le identità train e non sono una
   libreria generale di inference.
3. I candidati senza predizioni atlas devono restare nel pool principale; l'assenza
   della predizione non è evidenza contro la struttura.
4. K2 proposto da Claude: replay C477 con JM su holdout fissato non visto da JM,
   riportando separatamente la contaminazione dei componenti pubblici. La H100 2545
   è nuovamente occupata da Qwen: nessuna GPU è stata usata da Codex per J5c.
