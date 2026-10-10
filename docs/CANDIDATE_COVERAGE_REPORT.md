# Goal 4 — Candidate coverage e database expansion

Ultimo aggiornamento: 2026-10-10

## Esito

Il catalogo realistico sorgente contiene 49.620 strutture deduplicate per
InChIKey14 ed è costruito dalle prime 300.000 righe train con un ordine hash
deterministico che non consulta le identità validation. La canonicalizzazione
RDKit 2026.03.3 rimuove 425 record incoerenti, lasciando **49.195 strutture**.
Sul cohort congelato contiene 32/32 target e il nearest-mass li recupera tutti
entro rank 78:

| Metrica | Valore |
|---|---:|
| Catalog recall | 1,0000 |
| Candidate Recall@25 | 0,8750 |
| Candidate Recall@100 | 1,0000 |
| Candidate Recall@1000 | 1,0000 |
| Target consultati/prioritizzati | 0 / 0 |
| Target iniettati | 0 |

Recall@100=1 non deriva da un backstop oracle. I quattro miss top-25 sono
gruppi exact-mass/same-formula molto grandi:

| Query | Truth rank | Competitor exact-mass | Competitor same-formula |
|---|---:|---:|---:|
| `DSRJKXYSTOZVCB` | 29 | 42 | 42 |
| `FCWDQPSWCREWIQ` | 46 | 70 | 70 |
| `FZFSTIVUFMTJEG` | 37 | 45 | 45 |
| `GPNBPHAIMUWFGE` | 78 | 82 | 82 |

Questa evidenza identifica un problema di ranking entro tie group nel catalogo
corrente. Non dimostra che la coverage resti perfetta sul test Kaggle o dopo
un'espansione esterna. La validation è tratta dalla stessa sorgente strutturale
del catalogo e contiene soltanto 32 identità.

## Audit implementato

`goal4_audit.py` calcola, senza modificare i pool:

- massa, dimensione pool e distribuzione del truth rank;
- candidati nell'intero catalogo entro 5, 10, 20 e 50 ppm;
- competitor same-formula e proxy di isomeria costituzionale;
- breakdown per massa, addotto, strumento, source e numero di spettri;
- MRR@25, Hit@1/5/10, Recall@25/100/1000, conditional e oracle MRR;
- tassonomia per-query degli errori;
- controlli fail-closed su target consultation, prioritization, injection e
  candidati fuori catalogo.

Il controlled benchmark Goal 3 rimane conservato separatamente. Il suo catalogo
da 4.096 strutture consulta 128 target e registra 32 injection validation; può
misurare ranking condizionato, non performance end-to-end.

## Cataloghi esterni

Le informazioni sono snapshot datati e devono essere ricontrollate al momento
della build di un artifact redistribuibile.

| Catalogo | Scala osservata | Licenza/situazione | Priorità | Decisione |
|---|---:|---|---:|---|
| COCONUT | download CSV 191–208 MB; SDF 288–692 MB | curated dataset dichiarato CC0; provenance delle fonti da conservare | 1 | primo catalogo natural-product da misurare |
| ChEBI | oltre 195.000 entry | CC BY 4.0 | 1 | usare SDF strutturale, attribuzione e filtri qualità |
| LIPID MAPS LMSD | 50.586 strutture | SDF/RDF CC BY 4.0; TSV strutturale CC0 | 1 | ablation mirata a basso costo sui lipidi |
| PubChem Compound | 124.663.543 compound | termini NCBI/NLM e provenance contributor-specific da riesaminare | 2 | niente dump full in Kaggle; solo artifact structure-only prefiltrato con regola generale |

Fonti ufficiali:

- COCONUT: <https://coconut.naturalproducts.net/about> e
  <https://coconut.naturalproducts.net/download>;
- ChEBI: <https://www.ebi.ac.uk/chebi/about> e
  <https://www.ebi.ac.uk/chebi/downloads>;
- LIPID MAPS: <https://www.lipidmaps.org/databases> e
  <https://www.lipidmaps.org/databases/lmsd/download>;
- PubChem: <https://pubchem.ncbi.nlm.nih.gov/docs/statistics> e
  <https://pubchem.ncbi.nlm.nih.gov/docs/downloads>.

La registry versionata è in `candidate_catalogs.py`. PubChem è marcato
`review_required`; nessun database esterno massivo è stato scaricato in Goal 4.

## Indicizzazione implementata

Il modulo `candidate_catalogs.py` fornisce:

1. canonical record con InChIKey14, massa, formula, SMILES e provenance;
2. deduplica InChIKey14 che conserva l'unione completa delle source;
3. esclusione fisica delle identità novelty prima della build;
4. indice exact-mass ordinato con `searchsorted` e tie-break deterministico;
5. filtro opzionale per formula;
6. persistenza NumPy e apertura `mmap_mode='r'`;
7. fingerprint bit-packed e resource accounting.

La stima lower-bound per massa `float64`, InChIKey14, formula, SMILES,
metadata e Morgan-2048 bit-packed è circa 394 byte/struttura, prima di overhead
parser/indici e al netto della compressione:

| Tier | Strutture usate nella stima | Lower-bound |
|---|---:|---:|
| Corrente canonico | 49.195 | 0,018 GiB |
| ChEBI, upper proxy | 195.000 | 0,072 GiB |
| LIPID MAPS | 50.586 | 0,019 GiB |
| PubChem full | 124.663.543 | 45,74 GiB |

PubChem full non è compatibile con una materializzazione RDKit in RAM Kaggle.
La build corretta è streaming/chunked, con deduplica preventiva, colonne massa e
ID memory-mapped e caricamento di SMILES/fingerprint soltanto dopo la ricerca
per range di massa.

## Esperimenti di espansione ordinati

L'ordine approvato per il prossimo studio di coverage è:

1. current 49.195 canonico;
2. current + LIPID MAPS;
3. current + ChEBI;
4. current + COCONUT;
5. union Tier 1;
6. PubChem structure-only con cap progressivi e review dei termini.

Per ogni tier vanno misurati separatamente overlap, nuove identità, catalog
recall, Recall@25/100/1000, numero di candidati 5/10/20/50 ppm, competitor
same-formula, MRR a ranker fissato, storage, latenza e peak RSS. Il novelty
holdout deve rimuovere i target prima dell'indicizzazione. Un catalogo viene
promosso solo se il guadagno di coverage compensa il peggioramento di ranking e
il costo operativo.

## Limiti

- La coverage esterna non è stata inventata: senza scaricare e canonicalizzare
  i cataloghi non esistono valori affidabili di overlap o Recall.
- Same-formula con diverso InChIKey14 è un proxy forte ma non una prova
  ontologica completa di isomeria costituzionale.
- Il benchmark corrente è solo `enveda-180`/`timsTOF`; i breakdown piccoli non
  sostengono generalizzazioni cross-domain.
- Una selezione PubChem costruita dopo aver osservato le masse del test nascosto
  sarebbe metodologicamente rischiosa; la regola di build deve essere generale,
  predefinita e consentita dalle regole della competizione.
