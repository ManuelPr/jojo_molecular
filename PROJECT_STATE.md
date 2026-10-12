# Project state

Lo stato operativo autorevole è in
[docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

Al checkpoint del 2026-10-12 i Goal 1–4 sono completi; Goal 5 è **in corso** e
Goal 6 non è iniziato. Sono pronti codice e test per C1, retrieval scalabile,
protocollo domain-matched A/B/C e DreaMS frozen adapter. C1 contiene 271.439
strutture canoniche; le metriche E7–E12 complete non sono ancora disponibili.

L'unico job attivo è Goal 5 Kaggle v4, avviato alle 13:22:34 Europe/Rome e
verificato `RUNNING` alle 15:31:34 dopo 2 h 09 min 00,6 s. Nessuna VM a
pagamento è stata avviata. Il workflow deciso è: locale per codice/unit test,
Kaggle per smoke e inferenza, VM esterna per elaborazioni lunghe.

La prima submission ufficiale E6 v4 è `COMPLETE`: ref `57109254`, public
MRR@25 visualizzato 0,000, rank 3139/3140 allo snapshot. Non è stato creato un
nuovo commit né eseguito tuning. Il risultato indica che la validation
closed-world non calibra la candidate coverage hidden; E6 resta congelato.
Dettagli in [docs/FIRST_SUBMISSION_PRECHECK.md](docs/FIRST_SUBMISSION_PRECHECK.md).
