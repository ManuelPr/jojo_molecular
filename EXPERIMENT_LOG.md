# Experiment log

Il registro autorevole è in
[docs/EXPERIMENT_LOG.md](docs/EXPERIMENT_LOG.md).

Gli ultimi run sono EXP-013–015. Goal 5 v2 ha conservato C1 ma ha raggiunto il
limite dopo circa 11 h 58 min; v3 è fallita dopo 2 h 50 min 54,6 s per un
anchor E12 esterno alla union pool; il bug è corretto e testato. V4 era ancora
`RUNNING` dopo 2 h 09 min 00,6 s al checkpoint. Nessun risultato E7–E12 incompleto
è promosso e nessun nuovo run è stato avviato.

EXP-016 verifica il preflight E6. EXP-017 registra l'unica submission ufficiale:
Goal 4 v4, ref `57109254`, stato `COMPLETE`, public MRR@25 visualizzato 0,000 e
rank 3139/3140. Nessun tuning o secondo invio; priorità diagnostica alla
candidate coverage/novelty open-world.
