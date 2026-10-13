# Project state

Recovery audit completato: sul proxy domain-matched development C0 copre
108/188 truth (57,45%), C1 188/188. C1 raggiunge Recall@25/100/1000
89,89/99,47/100%, ma mass-only MRR@25 0,3801 per l'aumento dei distractor. Non
emerge un errore sistematico massa/addotto. La causa più probabile del public
0,000 è coverage/selection bias closed-world. Goal 5 v4 è `COMPLETE` dopo
8 h 21 min 46,64 s; artifact recuperati, E8–E12 non promossi. Vedi
[docs/ZERO_SCORE_ROOT_CAUSE.md](docs/ZERO_SCORE_ROOT_CAUSE.md).

Lo stato operativo autorevole è in
[docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

I Goal 1–4 sono completi; Goal 5 ha ora un artifact terminale E7–E12 ma nessun
modello promosso, e Goal 6 non è iniziato. C1 contiene 271.439 strutture
canoniche. Le metriche complete confermano più coverage ma non un miglioramento
stabile di MRR/Hit@1.

Goal 5 Kaggle v4 è `COMPLETE`; log effettivo 8 h 21 min 46,64 s, artifact
recuperati una volta e nessun relaunch. Nessuna VM a pagamento è stata avviata.
Il workflow resta: locale per codice/unit test, Kaggle per smoke e inferenza,
VM esterna per elaborazioni lunghe.

La prima submission ufficiale E6 v4 è `COMPLETE`: ref `57109254`, public
MRR@25 visualizzato 0,000, rank 3139/3140 allo snapshot. Non è stato creato un
nuovo commit né eseguito tuning. Il risultato indica che la validation
closed-world non calibra la candidate coverage hidden; E6 resta congelato.
Dettagli in [docs/FIRST_SUBMISSION_PRECHECK.md](docs/FIRST_SUBMISSION_PRECHECK.md).

Recovery aggiornata: il commit `cbf6416` introduce canonicalizzazione conforme
allo scorer, runner fail-fast e inferenza C1 + E6 congelato. Il rehearsal v2 è
`COMPLETE` in 1.119,35 s con 400×25 output validi. La seconda submission
autorizzata `57135939` è `COMPLETE` ma resta a public 0,000, rank 3189/3193.
Il solo bug C0 non spiegava quindi l'intero fallimento. Nessuna terza
submission e nessun Goal 6; prossimo lavoro lungo su VM: COCONUT e ladder
reference.
