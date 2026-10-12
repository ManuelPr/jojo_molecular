# Decision log

ADR-028 adotta recovery coverage-first: C1 con E6 congelato, scaling reference
e soltanto dopo C2/C3 su VM. Il runner candidato deve essere fail-fast. Goal 5
v4 è terminato `COMPLETE`, ma E8–E12 non sono promossi né rilanciati.

Il registro autorevole è in [docs/DECISIONS.md](docs/DECISIONS.md).

ADR-024 stabilisce locale per codice/test, Kaggle per smoke e inferenza, VM
esterna per elaborazioni lunghe. ADR-025 congela Goal 5 come incompleto: nessun
Goal 6, nessun nuovo run Kaggle, nessuna promozione E7–E12 senza artifact
terminale. Il job v4 già attivo segue una stop-rule di proposta a 4 ore e un
limite operativo di 8 ore, preservando log e artifact prima di cancellare.

ADR-026 seleziona per la prima submission il kernel Goal 4 E6 versione 4 già
completato. Nessun nuovo commit Kaggle e nessun tuning; l'invio richiede
approvazione esplicita. ADR-027 registra l'esito pubblico 0,000 e stabilisce che
la prossima evidenza debba riguardare candidate coverage/novelty open-world,
senza modificare E6 o fare tuning sul leaderboard.
