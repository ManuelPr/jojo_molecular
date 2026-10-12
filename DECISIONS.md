# Decision log

Il registro autorevole è in [docs/DECISIONS.md](docs/DECISIONS.md).

ADR-024 stabilisce locale per codice/test, Kaggle per smoke e inferenza, VM
esterna per elaborazioni lunghe. ADR-025 congela Goal 5 come incompleto: nessun
Goal 6, nessun nuovo run Kaggle, nessuna promozione E7–E12 senza artifact
terminale. Il job v4 già attivo segue una stop-rule di proposta a 4 ore e un
limite operativo di 8 ore, preservando log e artifact prima di cancellare.
