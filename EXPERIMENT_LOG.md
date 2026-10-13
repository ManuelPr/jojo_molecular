# Experiment log

EXP-018 completa forensics locale C0/C1 sul proxy domain-matched: catalog recall
0,5745 contro 1,0; Recall@1000 0,5745 contro 1,0; mass-only MRR@25 0,4069
contro 0,3801. Il sealed non è stato aperto e non sono stati avviati training,
kernel o submission. Artifact: `artifacts/zero_score_recovery/forensics.json`.

Il registro autorevole è in
[docs/EXPERIMENT_LOG.md](docs/EXPERIMENT_LOG.md).

Gli ultimi run sono EXP-013–015. Goal 5 v2 ha conservato C1 ma ha raggiunto il
limite dopo circa 11 h 58 min; v3 è fallita dopo 2 h 50 min 54,6 s per un
anchor E12 esterno alla union pool; il bug è corretto e testato. V4 è poi
terminata `COMPLETE` dopo 8 h 21 min 46,64 s. E8–E12 non sono promossi:
coverage e Hit@5/10 aumentano, ma Hit@1 peggiora e i delta MRR non sono stabili.
Nessun nuovo run è stato avviato.

EXP-016 verifica il preflight E6. EXP-017 registra l'unica submission ufficiale:
Goal 4 v4, ref `57109254`, stato `COMPLETE`, public MRR@25 visualizzato 0,000 e
rank 3139/3140. Nessun tuning o secondo invio; priorità diagnostica alla
candidate coverage/novelty open-world.

EXP-019 registra il runner fail-fast e il rehearsal recovery v2: C1 da 271.439
strutture, E6 congelato, 400×25 output validi e runtime 1.119,35 s. EXP-020
registra la seconda submission autorizzata `57135939`: `COMPLETE`, public
0,000, rank 3189/3193. Il passaggio C0→C1 non risolve il public set; nessun
terzo invio e nessun tuning leaderboard.
