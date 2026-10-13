# Next steps — Goal 5 checkpoint

## Sequenza recovery aggiornata

1. Conservare Goal 5 v4 `COMPLETE`, log e artifact già recuperati; non
   promuovere E8–E12 e non rilanciare il notebook.
2. Rendere fail-fast la futura pipeline candidata eliminando
   fallback di esperimento/feature/peso e aggiungendo fingerprint runtime.
3. Sulla VM, riusare C1 e misurare E6 congelato con la ladder reference
   127/512/2.000/2.748. Non aprire il sealed fino al congelamento.
4. Costruire C2 COCONUT e C3 ChEBI/LIPID MAPS solo dopo il risultato C1;
   misurare separatamente catalog recall, Candidate Recall e ranking.
5. Fare un unico rehearsal Kaggle di sola inferenza con artifact precomputati.
6. Fermarsi prima della seconda submission e chiedere nuova approvazione.

Dettagli in [RECOVERY_EXPERIMENT_PLAN.md](RECOVERY_EXPERIMENT_PLAN.md). Goal 6
resta vietato.

Ultimo aggiornamento: 2026-10-12

## Stato

Goal 5 è incompleto ma salvato in un checkpoint riproducibile. Goal 6 non deve
iniziare. Non avviare nuovi esperimenti o kernel Kaggle finché il workflow non è
stato riorganizzato.

## Prossima operazione breve consentita

Il kernel Goal 5 v4 è terminale e gli artifact sono già archiviati. Non
rilanciarlo e non effettuare submission. La prossima modifica breve è rendere
fail-fast il runner futuro; gli esperimenti lunghi riprendono soltanto dopo la
predisposizione della VM.

## Lavoro Goal 5 ancora necessario

1. Rendere fail-fast il runner futuro e aggiungere fingerprint di input/output.
2. Isolare l'effetto reference con ladder 127/512/2.000/2.748 su VM.
3. Migliorare il reranking C1 mirando a Hit@1 senza modificare E6 tramite LB.
4. Eseguire il probe DreaMS frozen soltanto in un ambiente Python 3.11 isolato,
   dopo aver preparato wheelhouse e checkpoint con hash.
5. Valutare C2 (COCONUT) e poi C3 (ChEBI/LIPID MAPS); nessun
   database esterno è stato ancora importato.
6. Preparare un rehearsal Kaggle di sola inferenza e, solo dopo risultati
   completi, formulare la decisione sul Goal successivo.

## Workflow da predisporre prima di riprendere

### Locale

Codice, unit test, compile check e validazione degli artifact su subset piccoli.
Nessun preprocessing completo.

### Kaggle

Solo smoke bounded e inferenza offline. Target operativo: smoke entro 15–30
minuti; l'inferenza Goal 4 osservata richiede circa 25 minuti, circa 36,5 minuti
incluso il benchmark di selezione. Evitare rebuild e benchmark multi-ora.

### VM esterna

Per un run Goal 5 completo usare inizialmente CPU, non GPU: 16–32 vCPU, 32–64
GB RAM e almeno 20 GB di disco di lavoro, con cache/artifact persistenti. Stima
di budget: 4–8 ore se C1 e feature riutilizzabili sono già presenti; 8–12 ore
se è necessario ricostruire la canonicalizzazione completa. Sono budget di
planning, da verificare con uno smoke e checkpoint intermedi, non promesse.

Nessuna VM a pagamento può essere avviata senza approvazione esplicita.

## Criterio di ripresa

Riprendere gli esperimenti solo dopo aver definito:

- immagine/lockfile della VM;
- upload e checksum di C1 e dei manifest di split;
- checkpoint per stage e resume;
- logging periodico di runtime/RSS;
- stop-rule e costo massimo;
- trasferimento finale degli artifact alla pipeline Kaggle di inferenza.

## Calibrazione E6 completata

La versione Kaggle Goal 4 v4 è stata inviata una sola volta dopo approvazione:
submission `57109254`, stato `COMPLETE`, public MRR@25 visualizzato 0,000 e
rank 3139/3140 allo snapshot del 2026-10-12. E6 resta congelato e non va
modificato in risposta al singolo public score.

Prima di proporre una seconda submission occorre produrre evidenza offline che
il candidate generator recuperi strutture non presenti nel catalogo train-only.
Non usare il leaderboard per distinguere ipotesi di coverage, ranking o
novelty. L'eventuale nuovo invio richiede una nuova approvazione esplicita.

## Aggiornamento dopo la seconda submission

La recovery C1 + E6 `57135939` è `COMPLETE` con public 0,000. Non ripetere C1
e non fare una terza submission. Prossime attività, in ordine:

1. predisporre la VM esterna con checkpoint, checksum e budget;
2. costruire C2 = C1 + COCONUT e misurare coverage/ranking offline;
3. eseguire la ladder reference 127/512/2.000/2.748 con E6 congelato;
4. riesaminare il percorso hidden-only solo tramite log e test consentiti;
5. aprire un nuovo gate prima di qualsiasi ulteriore submission.

Goal 6 resta non iniziato. Kaggle rimane limitato a smoke e inferenza.
