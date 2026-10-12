# Decision log

## ADR-001 - Tre protocolli, non un singolo holdout

**Data:** 2026-10-09  
**Stato:** accettata

Usare library holdout, molecule-disjoint e novelty holdout come protocolli separati. Un solo split same-identity sovrastima la generalizzazione e non distingue ranking da copertura del catalogo.

## ADR-002 - Leakage audit bloccante prima del fit

**Data:** 2026-10-09  
**Stato:** accettata

Il fit non parte se identita, contenuto spettrale, candidate roster, osservazioni del ranker o provenance delle feature violano il protocollo. I manifest canonici sono artifact di prima classe.

## ADR-003 - Nearest mass come controllo forte

**Data:** 2026-10-09  
**Stato:** accettata

Mantenere nearest mass in ogni studio. Nel run v4 supera retrieval union e ranker nel molecule-disjoint, quindi un modello complesso deve dimostrare un delta appaiato rispetto a questo controllo, non soltanto rispetto al caso casuale.

## ADR-004 - Non promuovere il ranker corrente

**Data:** 2026-10-09  
**Stato:** accettata

Il ranker migliora il library holdout, ma non il molecule-disjoint. Questo e coerente con overfitting al regime same-identity. Rimane una baseline e un test d'integrazione.

## ADR-005 - Fingerprint isomer-aware prima di modelli pesanti

**Data:** 2026-10-09  
**Stato:** accettata

Il prossimo esperimento e un spectrum-to-fingerprint baseline con hard negatives same-formula. Candidate Recall@25 e gia 1 nel catalogo bounded, mentre 13/32 errori del ranker hanno un competitor same-formula. DreaMS e ICEBERG/GLACIER restano milestone successive e richiedono evidenza incrementale.

## ADR-006 - Novelty come ramo esplicito

**Data:** 2026-10-09  
**Stato:** accettata

Il closed-world ranker ottiene necessariamente zero quando il target e assente dal catalogo. La novelty generation deve avere interfacce, metriche e budget propri e confluire nell'ensemble soltanto dopo filtri chimici e mass consistency.

## ADR-007 - Locale leggero, Kaggle per smoke, VM per scala

**Data:** 2026-10-09  
**Stato:** accettata

Lo sviluppo locale e limitato a codice e test CPU. Kaggle esegue smoke e validazioni bounded offline; il training completo si sposta su una VM grande solo dopo un risultato go/no-go positivo. Nessuna submission automatica.

## ADR-008 - Controlled e realistic sono benchmark diversi

**Data:** 2026-10-09  
**Stato:** accettata

Il catalogo controlled puo consultare e garantire il target e serve esclusivamente a misurare ranking condizionato. Il realistic deve derivare soltanto da informazioni disponibili in inferenza, conservare una trace di costruzione target-blind e fallire se rileva injection. I risultati dei due protocolli non possono essere aggregati o presentati come equivalenti.

Motivo: con 4.096 candidati controlled il Recall@25 e 1,0000 e la mediana same-formula e 0; con 49.620 candidati realistic il Recall@25 e 0,8750 e la mediana same-formula e 10,5.

## ADR-009 - Non promuovere il fingerprint encoder Goal 3

**Data:** 2026-10-09  
**Stato:** accettata

Il compact peak encoder e implementativamente valido ma non generalizza: mean sample Jaccard 0,0893 contro 0,2120 del KNN, early stopping all'epoca 1 in tutti i fold e peso fingerprint selezionato pari a zero in E2/E3. Nel realistic E4 ed E5 peggiorano E0 e gli intervalli non sostengono un vantaggio.

Non aumentare dimensione, profondita o attenzione. Prima servono learning curve su piu identita, rappresentazioni candidate migliori, gestione della sparsita dei bit e un obiettivo piu vicino al ranking same-formula.

## ADR-010 - Ritardare ICEBERG/GLACIER

**Data:** 2026-10-09  
**Stato:** accettata

ICEBERG/GLACIER non vengono integrati nella fase successiva immediata. Un forward scorer aggiungerebbe costo e confondenti mentre il segnale fingerprint di base e negativo e quattro target su 32 non raggiungono ancora la top-25 realistic. L'integrazione forward diventa ammissibile dopo un delta fingerprint positivo e ripetibile oppure dopo una chiara evidenza che la rappresentazione candidata, non lo spettro encoder, e il collo di bottiglia.

## ADR-011 - Canonicalizzazione bloccante del catalogo Goal 4

**Data:** 2026-10-10  
**Stato:** accettata

Applicare RDKit 2026.03.3 con canonicalizzazione tautomerica e richiedere che
l'InChIKey14 ricalcolato coincida con la chiave fornita prima di indicizzare una
struttura. Il rehearsal ha trovato 425 mismatch su 49.620 record unici. Usare lo
stesso catalogo filtrato in validation e inference; registrare i reject, senza
correggerli usando identità validation o test.

## ADR-012 - Promuovere analog propagation soltanto come reranker del pool fisso

**Data:** 2026-10-10  
**Stato:** accettata

Il segnale analogico deve operare sul top-100 nearest-mass senza aggiungere
candidati. Le reference sono identity-OOF in training e non contengono identità
o hash validation. La formula del target, i descrittori query-only e gli score
del leaderboard non sono feature. La promozione definitiva usa delta appaiato
rispetto a E0 e final holdout, non il controlled benchmark.

Il run canonico v4 soddisfa il gate: E6 ottiene delta MRR@25 +0,016369 sul
development (IC95% [+0,001938; +0,033939]), +0,026794 su all-validation
(IC95% [+0,003121; +0,061990]) e +0,037218 sul final, dove l'intervallo ampio
attraversa zero. E6 sostituisce E0 come baseline competitiva, mantenendo E0
come controllo obbligatorio.

## ADR-013 - Neutral loss e fragment compatibility isolati non sono baseline

**Data:** 2026-10-10  
**Stato:** accettata

E1 ed E2 vengono conservati come ablation, non come sistemi promossi. La
compatibilità formula/neutral loss è quasi costante fra isomeri; il fragment
matching diventa candidato-specifico soltanto tramite una reference o una
predizione forward. Un peso nullo scelto sul development è un risultato valido,
non un motivo per forzare la feature nel ranker.

## ADR-014 - Non scegliere LightGBM dal solo final piccolo

**Data:** 2026-10-10  
**Stato:** accettata

La selezione dei modelli avviene sulle 16 identità development. Un E5 forte per
caso sulle 16 identità final ma negativo/instabile sul development non viene
promosso. Il final rimane audit indipendente e non può essere usato per cambiare
feature o iperparametri nello stesso goal.

## ADR-015 - Espansione catalogo per tier, non PubChem full

**Data:** 2026-10-10  
**Stato:** accettata

Misurare nell'ordine current, LIPID MAPS, ChEBI, COCONUT e union Tier 1.
PubChem entra solo come artifact structure-only prefiltrato con provenance e
review dei termini. Ogni tier deve riportare coverage e ranking separatamente;
un catalogo più grande non è automaticamente migliore.

## ADR-016 - Escludere reference duplicate delle query anche in inferenza

**Data:** 2026-10-10  
**Stato:** accettata

Prima dello scoring nascosto, calcolare hash del contenuto normalizzato delle
query e rimuovere ogni reference coincidente, senza consultare identità test.
La v3 è stata correttamente bloccata dal controllo; la v4 ha escluso una
reference su 128 e ha completato. Disabilitare la guardia avrebbe introdotto
library lookup non dichiarato.

## ADR-017 - Non promuovere E5 dal final holdout

**Data:** 2026-10-10  
**Stato:** accettata

E5 raggiunge 0,494942 sul final di 16 query, ma nel development scende da
0,349104 a 0,263413 con delta -0,085691 e IC95% interamente negativo. La
selezione final-driven sarebbe leakage da model selection; E5 resta una
baseline diagnostica.

## ADR-018 - Goal 5 focalizzato sul retrieval analogico

**Data:** 2026-10-10  
**Stato:** accettata

Seguire Scenario C: scalare la library analogica, indicizzarla e provare DreaMS
congelato. Misurare Tier 1 coverage in parallelo. ICEBERG/GLACIER entra solo
dopo un probe economico sul residuo same-formula; nessun grande training viene
autorizzato dalla conclusione di Goal 4.

## ADR-019 - E6 congelato come controllo di regressione Goal 5

**Data:** 2026-10-10
**Stato:** accettata

Il commit `04a6a89ae7fc6c32d4a65f6f63450864f5a00abc`, gli hash dei dati,
il manifest, le metriche E0/E6 e il CSV v4 sono un contratto immutabile. Le
estensioni Goal 5 vivono in nuovi moduli e confrontano ogni challenger con E6 a
parità di stage. Nessun risultato Goal 4 viene ricalcolato retroattivamente.

## ADR-020 - Validation domain-matched in tre condizioni e holdout sigillato

**Data:** 2026-10-10
**Stato:** accettata

Usare `enveda-np-examples`/timsTOF come proxy di dominio, non come stima
imparziale del test. Separare A library-visible, B structure-known/spectra-hidden
e C structure-absent. Escludere fisicamente i 16 final Goal 4, gli hash delle
query e le identità sealed dalle reference development. Il sealed viene aperto
una sola volta dopo aver fissato E7-E12.

## ADR-021 - Indici esatti prima di ANN

**Data:** 2026-10-10
**Stato:** accettata

Per massa e formula usare array ordinati, posting list, `searchsorted`, mmap e
checksum. Per gli analoghi usare un prefilter esatto sulla massa neutra prima
dello scorer Goal 4 invariato. FAISS/HNSW non è giustificato per una query
monodimensionale e non può sostituire il fallback nearest-mass; sarà rivalutato
solo per un canale vettoriale che risulti un collo di bottiglia misurato.

## ADR-022 - DreaMS è environment-blocked, non model-rejected

**Data:** 2026-10-10
**Stato:** accettata

Non installare DreaMS direttamente nell'ambiente di scoring Python 3.13/RDKit
2026.03.3. L'upstream pinna Python 3.11 operativo, Torch 2.2.1, NumPy 1.25,
PyArrow 15 e RDKit 2023.9.6 e richiede un checkpoint da 1,24 GB. Il probe dovrà
girare in un wheelhouse Python 3.11 isolato ed esportare embedding verificati.
L'assenza del run non è evidenza negativa sulla qualità del modello.

## ADR-023 - Nessun prior di database senza evidenza inference-safe

**Data:** 2026-10-10
**Stato:** accettata

E11 resta non eseguito. La frequenza di una struttura nel train o la presenza
in una sorgente non diventa automaticamente un prior chimico generalizzabile;
può riflettere sampling della library e peggiorare novelty. Un prior entrerà
solo con provenance, definizione disponibile in inferenza e delta stabile su
development e sealed.

## ADR-024 - Kaggle per smoke e inferenza, VM per elaborazioni lunghe

**Data:** 2026-10-12
**Stato:** accettata

Lo sviluppo locale resta limitato a codice, compile check e unit test. Kaggle
viene usato per smoke test ridotti e inferenza offline compatibile con la
competizione, non per canonicalizzazione completa o benchmark di molte ore. I
rebuild del catalogo, la preparazione delle reference e gli esperimenti E7–E12
completi vanno spostati su una VM esterna con artifact persistenti. Nessuna VM a
pagamento viene avviata senza approvazione esplicita.

Motivo: Goal 5 v2 ha consumato circa 11 h 58 min quasi interamente nella
canonicalizzazione prima del limite Kaggle; v3 ha impiegato 2 h 50 min 55 s per
raggiungere la prima valutazione development. Il costo non è adatto al ciclo di
debug Kaggle.

## ADR-025 - Goal 5 congelato a checkpoint incompleto

**Data:** 2026-10-12
**Stato:** accettata

Non iniziare Goal 6 e non promuovere E7–E12 finché non esiste un artifact
terminale con metriche development e sealed. Il kernel v4 già attivo può
terminare, ma non va sostituito da un nuovo run Kaggle. Se supera 4 ore senza
artifact terminale, proporre la cancellazione; 8 ore è il limite operativo per
questo benchmark. L'eventuale cancellazione deve preservare log, versione e
artifact recuperabili.

## ADR-026 - Prima submission dalla versione Goal 4 E6 già completata

**Data:** 2026-10-12

**Stato:** accettata

Usare `mperni/casmi26-goal4-spectral-ranking`, versione 4, come prima
submission ufficiale. Non creare una nuova versione e non incorporare Goal 5:
la v4 è `COMPLETE`, offline, associata alla competizione e ha output/hash/runtime
già verificati. Il modello resta E6 con `analog_score`, peso 0,5 e reranking
same-formula dell'anchor mass.

La submission rimane bloccata fino ad approvazione esplicita. Dopo l'invio si
registra un solo punto di calibrazione; il public leaderboard non viene usato
per modificare E6 o scegliere iperparametri.
