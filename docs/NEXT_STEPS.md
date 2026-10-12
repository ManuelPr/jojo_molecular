# Next steps — Goal 5 checkpoint

Ultimo aggiornamento: 2026-10-12

## Stato

Goal 5 è incompleto ma salvato in un checkpoint riproducibile. Goal 6 non deve
iniziare. Non avviare nuovi esperimenti o kernel Kaggle finché il workflow non è
stato riorganizzato.

## Prossima operazione breve consentita

Controllare una sola volta lo stato del kernel Goal 5 v4 già attivo:

- se è terminale, scaricare log e artifact senza rilanciarlo;
- se è ancora `RUNNING` oltre 4 ore, proporre l'interruzione;
- non consentire a questo benchmark di superare 8 ore;
- prima di cancellare, registrare stato, durata, versione e tutto ciò che Kaggle
  rende recuperabile.

Non aprire manualmente il sealed stage e non effettuare submission.

## Lavoro Goal 5 ancora necessario

1. Ottenere un artifact E7–E12 completo su development e sealed.
2. Validare E8/E9 candidate-order equality e misurare Recall@25/100/1000 di C1.
3. Calcolare paired delta, bootstrap, Hit@1/5/10, conditional/oracle MRR,
   breakdown same-formula e costi di retrieval/ranking.
4. Completare le diagnostiche domain-shift fra reference train, cohort
   `enveda-np-examples`/timsTOF e test placeholder.
5. Eseguire il probe DreaMS frozen soltanto in un ambiente Python 3.11 isolato,
   dopo aver preparato wheelhouse e checkpoint con hash.
6. Valutare C2 (prima LIPID MAPS o COCONUT) solo dopo aver misurato C1; nessun
   database esterno è stato ancora importato.
7. Preparare un rehearsal Kaggle di sola inferenza e, solo dopo risultati
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
