# External candidate coverage analysis

**Rettifica API 2026-10-13:** la recovery `57135939` è un crash del rerun hidden
con score assente, non un secondo zero. Non misura l'effetto di C1 sul hidden;
le deduzioni storiche che dipendono da quel presunto score sono superate.

Data: 2026-10-12  
Stato: C0/C1 misurati; C2/C3/PubChem non ancora materializzati

## Protocollo

Il confronto usa le 188 identità di sviluppo del protocollo domain-matched Goal
5 (`enveda-np-examples`, timsTOF, 876 spettri). Il sealed holdout di 46 identità
non è stato aperto. La candidate generation usa soltanto massa neutra ricavata
da precursor m/z e addotto; nessuna truth viene inserita o prioritarizzata.

Le metriche riportate sono mass-only e servono a separare:

1. catalog recall: truth fisicamente presente nel tier;
2. candidate recall: truth recuperata entro K;
3. ranking: posizione della truth fra i distractor.

Non sono metriche E6 spettrali e non vanno confrontate direttamente con il
public leaderboard.

## Risultati misurati

| Tier | Strutture canoniche | Catalog recall | Recall@25 | Recall@100 | Recall@1000 | MRR@25 | Conditional MRR@25 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0: prime 300k righe / E6 | 49.195 | 57,45% | 56,91% | 57,45% | 57,45% | 0,4069 | 0,7082 |
| C1: train completo | 271.439 | 100% | 89,89% | 99,47% | 100% | 0,3801 | 0,3801 |
| C2: C1 + COCONUT | non costruito | non misurato | non misurato | non misurato | non misurato | non misurato | non misurato |
| C3: C2 + ChEBI + LIPID MAPS | non costruito | non misurato | non misurato | non misurato | non misurato | non misurato | non misurato |
| PubChem selettivo | non definito | non misurato | non misurato | non misurato | non misurato | non misurato | non misurato |

C1 aggiunge copertura per 80/188 query (42,55 punti percentuali). Le 80 nuove
truth hanno provenance sovrapposta in più library; fra le fonti osservate:
`enveda-np-examples` 80, `riken` 77, `gnps` 68, `pluskal_ms2` 67, `mona` 66,
`msdial` 66, `massbank` 54 e `masaryk` 1. I conteggi non sono mutuamente
esclusivi.

Il costo dell'espansione è misurabile: i competitor con formula uguale passano
in media da 1,55 in C0 a 14,18 in C1 (mediana da 0 a 5, massimo da 47 a 220).
Per questo MRR mass-only scende da 0,4069 a 0,3801 anche se la coverage diventa
completa. C1 è necessario per coverage, ma non sufficiente per ranking.

## Caratteristiche dei tier esterni

### C2 — COCONUT

COCONUT è il primo tier esterno coerente con il dominio natural-product. Il
[portale ufficiale di download](https://coconut.naturalproducts.net/download)
indica licenza CC0 e, nell'istantanea consultata, CSV lite 191 MB, CSV completo
207,9 MB, SDF lite 287,6 MB e SDF completo 691,7 MB.

Import richiesto:

- conservare ID, source release e record originale;
- neutralizzare/canonicalizzare con la stessa pipeline RDKit di C1;
- rifiutare mixture, strutture invalide e masse non finite con contatori;
- deduplicare per InChIKey14 senza perdere la provenance;
- costruire indice mass/formula mmap e checksum manifest;
- misurare coverage incrementale prima di valutare il ranking.

### C3 — ChEBI e LIPID MAPS

[ChEBI](https://www.ebi.ac.uk/chebi/downloads) pubblica dump SDF periodici; la
[pagina ufficiale](https://www.ebi.ac.uk/chebi/about) specifica CC BY 4.0. Va
conservata l'attribuzione nella provenance dell'artifact.

[LIPID MAPS](https://www.lipidmaps.org/databases?tab=lmpd) riportava 50.572
strutture LMSD nell'istantanea consultata. Il download SDF compresso indicava
circa 21,19 MB, CC BY 4.0 e aggiornamento 2026-10-06. È piccolo e pertinente ai
lipidi, ma il beneficio va misurato per classe/adducto e non assunto.

### PubChem selettivo

PubChem può essere utile solo come tier successivo e selettivo. La
[pagina ufficiale dei download](https://pubchem.ncbi.nlm.nih.gov/assay/assaydownload.cgi)
espone download bulk, ma la provenance dei contributori può avere condizioni
specifiche: non si deve etichettare indiscriminatamente l'intero corpus come
public domain.

Un sottoinsieme lecito deve essere definito prima di osservare il test hidden
con criteri generali, per esempio massa ufficiale supportata, elementi ammessi,
carica/mixture, organicità, stereochimica e qualità del record. Versione,
query/criteri e licenza per fonte devono entrare nel manifest.

## Costi e architettura degli artifact

Il rebuild C0 locale ha impiegato 568,3 s per 49.195 strutture a causa della
canonicalizzazione tautomerica. Il caricamento mmap C1, già costruito e con
checksum, ha richiesto 0,61 s. È quindi corretto riutilizzare C1 e spostare gli
import C2/C3 sulla VM.

Configurazione iniziale consigliata per C2/C3:

- 16–32 vCPU;
- 64 GB RAM;
- 100–250 GB disco persistente per raw, normalized, indici e checkpoint;
- nessuna GPU necessaria;
- checkpoint per sorgente e per shard;
- output Parquet/Arrow compresso più array mass/formula mmap;
- log di throughput, reject, overlap e peak RSS.

PubChem richiederà uno studio di sizing separato e non deve essere scaricato
integralmente prima di aver dimostrato il valore di C2/C3.

## Criteri di accettazione per un tier

Un tier entra nella pipeline solo se:

- aumenta catalog recall su development domain-matched e su un holdout non usato
  per la selezione;
- non usa identità target per la costruzione o priorità dell'indice;
- ha licenza e release manifestate;
- preserva Candidate Recall@1000 e misura il delta @25/@100;
- il reranker recupera almeno parte della MRR persa per i nuovi distractor;
- runtime, RSS e dimensione sono compatibili con inferenza Kaggle offline;
- la deduplica InChIKey14 e i checksum sono riproducibili.

## Limite dell'analisi corrente

C2, C3 e PubChem non sono stati scaricati o indicizzati sul laptop, in accordo
con il workflow richiesto. Qualunque valore di coverage per questi tier sarebbe
inventato. Il prossimo risultato quantitativo deve provenire da artifact VM
versionati, non da una submission leaderboard.

## Risultato Goal 5 v4 con E6 congelato

Il job terminale v4 ha valutato C0/C1 con la logica E6 congelata e una reference
library leakage-safe fino a 2.748 spettri in development A. Sul development:

| Condizione | Tier | MRR@25 | Hit@1 | Hit@5 | Hit@10 | Recall@25 | Recall@100 |
|---|---|---:|---:|---:|---:|---:|---:|
| A | C0/E7 | 0,4179 | 0,3457 | 0,5053 | 0,5319 | 0,5691 | 0,5745 |
| A | C1/E8 | 0,4581 | 0,3032 | 0,6809 | 0,7926 | 0,8989 | 0,9947 |
| B | C0/E7 | 0,4107 | 0,3404 | 0,5000 | 0,5213 | 0,5691 | 0,5745 |
| B | C1/E8 | 0,4082 | 0,2500 | 0,6223 | 0,7766 | 0,8989 | 0,9947 |

Sul sealed, E8−E7 è +0,0065 MRR in A e −0,0187 in B; entrambi gli IC95%
attraversano ampiamente zero. Il catalogo esteso migliora nettamente Hit@5/10 e
coverage, ma riduce Hit@1 in tutte le celle A/B. Questo è il vincolo centrale
per C2/C3: il valore di un tier esterno dipenderà dalla capacità di reranking,
non soltanto dalla membership.

## Calibrazione pubblica C1

La pipeline C1 + E6 congelato è stata inviata una sola volta come recovery
submission `57135939`. Nonostante C1 porti il catalog recall del proxy
domain-matched da 57,45% a 100%, il public MRR@25 è rimasto 0,000. Il risultato
non misura direttamente il catalog recall hidden, ma dimostra che l'espansione
C0→C1 non è sufficiente per la competizione. C2 COCONUT diventa quindi il
prossimo test di coverage più economico; deve essere costruito e validato su VM,
non selezionato tramite un terzo tentativo leaderboard.
