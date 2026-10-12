# Project state

Lo stato operativo autorevole è in
[docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

Al checkpoint del 2026-10-12 i Goal 1–4 sono completi; Goal 5 è **in corso** e
Goal 6 non è iniziato. Sono pronti codice e test per C1, retrieval scalabile,
protocollo domain-matched A/B/C e DreaMS frozen adapter. C1 contiene 271.439
strutture canoniche; le metriche E7–E12 complete non sono ancora disponibili.

L'unico job attivo è Goal 5 Kaggle v4, avviato alle 13:22:34 Europe/Rome e
verificato `RUNNING` alle 15:31:34 dopo 2 h 09 min 00,6 s. Nessuna submission e
nessuna VM a pagamento sono state avviate. Il workflow deciso è: locale per
codice/unit test, Kaggle per smoke e inferenza, VM esterna per elaborazioni
lunghe.
