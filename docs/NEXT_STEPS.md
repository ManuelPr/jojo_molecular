# Next steps — Goal 5

Ultimo aggiornamento: 2026-10-10

## Decisione

Goal 4 seleziona principalmente lo Scenario C: E6 analog propagation migliora
E0 sul development e su all-validation, mentre neutral loss, fragment-only e
LambdaRank non forniscono un vantaggio ripetibile. Il collo di bottiglia
immediato è la qualità e la scala del retrieval analogico, con un problema
secondario di coverage esterna non ancora misurata.

## Priorità 1 — Libreria spettrale e retrieval analogico

1. Costruire un indice leakage-safe su un numero crescente di identità train,
   conservando identity e content-hash exclusion.
2. Misurare learning curve a 128, 512, 2.048 e tutte le reference ammissibili.
3. Confrontare exact precursor, shifted precursor, modified cosine, entropy e
   neutral-loss retrieval con gli stessi preprocessing e pool.
4. Calibrare confidence e gate soltanto sul development; mantenere final
   congelato.
5. Ridurre il costo attuale di circa 3,75 s/molecola con prefiltri di massa,
   sparse peak index o ANN, senza cambiare i candidati valutati nell'ablation.

Go: delta paired positivo contro E0 su almeno due split/semi o un intervallo
all-validation positivo, senza regressione materialmente maggiore sul final.

## Priorità 2 — DreaMS come probe congelato

Usare DreaMS pretrained soltanto per embedding e retrieval, senza fine-tuning
grande. Confrontarlo con E6 a reference library, candidate pool e protocolli
identici. Promuoverlo solo se migliora MRR/Hit@1 e/o riduce il costo a parità di
quality. Nessun Transformer da addestrare da zero.

## Priorità 3 — Coverage Tier 1

Canonicalizzare e misurare, in ordine, LIPID MAPS, ChEBI e COCONUT. Per ogni
tier registrare overlap, catalog recall, Recall@25/100/1000, densità ppm,
competitor same-formula, MRR con E6 congelato, spazio, RAM e latenza. PubChem
full resta escluso finché non esistono regola di prefiltraggio generale e
review dei termini.

## Priorità 4 — Residuo same-formula

E6 lascia ancora 9/16 errori final same-formula. Dopo avere stabilizzato
retrieval e coverage, eseguire un piccolo probe ICEBERG/GLACIER pretrained per
forward spectral reranking. Non avviare training completo finché il probe non
dimostra un delta candidato-specifico rispetto a E6.

## Ramo novelty

Novelty generation rimane separata dal closed-world ranking. Va valutata con
validità chimica, mass/formula consistency, novelty, diversity e coverage su un
holdout che esclude fisicamente i target dal catalogo; non può essere giustificata
dalla MRR closed-world.

## Calibrazione leaderboard

Il CSV v4 è pronto ma non inviato. Dopo eventuale approvazione, effettuare una
sola submission di calibrazione e registrare kernel/dataset version, hash CSV,
score locale, public score e runtime. Non riutilizzare il leaderboard per
tuning iterativo.

## Ambiente e budget

- Locale: codice e unit test soltanto.
- Kaggle T4: smoke ed esperimenti bounded offline.
- VM grande: configurazione futura, nessun avvio senza un go sperimentale.
- Vietati submission automatiche, VM a pagamento e training neurali grandi.
