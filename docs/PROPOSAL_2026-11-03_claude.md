# Proposta Claude, 3 novembre 2026: generatore largo sopra la linea pubblica 0.480

Stato: noi 0.477 (C477). Public: heliosli 0.481, bgunshui/alexchilton neural ensemble 0.480, midx 0.479. LB: 1° 0.521,
10° 0.489, 20° 0.484 (oro ≈ top 19 su ~4 500 squadre). Serve ≈ +0.010–0.015 sopra la linea pubblica.

## 1. Survey (parte Claude)

Notebook in `artifacts/notebook_survey_2026-11-03/`. Tutti i notebook ≥ 0.479 usano **lo stesso pipeline congelato**
(`FROZEN_SHA256 d1e757c2…`, stesso `runner.py`) di C477: le differenze stanno solo nello strato finale.

| Notebook | Public | Differenza rispetto a C477 |
|---|---:|---|
| baidalinadilzhan midx exact dedup fill | 0.479 | (a) leader move del fragment check sempre applicato (non più bloccato se gli insiemi differiscono); (b) **prior di documentazione** sui rank 2–25: `1/(3+br)+0.75/(3+nr)+0.10·pop/20+0.05·spec·[lib_max≥0.87]+0.02·np` da `pool_popularity.csv`; (c) dedup per metric identity + riempimento con outsider valutati; (d) vecchio leader fissato al rank 2 dopo un leader move |
| bgunshui / alexchilton neural ensemble | 0.480 | midx + secondo scorer (kernel `bgunshui/casmi26-scorer-train-public`, kit sanpier) in ensemble z-score 0.5/0.5 con lo scorer pubblico; da solo in sostituzione 0.460 (come i nostri JM: **sostituire perde, affiancare non perde**) |
| easonyanyan v33 | ~0.480 | stessa ricetta, w_mid 0.80, gate 0.80, più outsider: tuning sul LB |
| nofreewill audit | – | utilità di dedup per metric identity; nessun guadagno dichiarato |
| chr1snv MassSpecToSmiles | – | de novo sperimentale, nessuno score |

Il run-to-run del pipeline è ±0.002 (time guard), quindi 0.479/0.480/0.481 sono la stessa linea.

## 2. Dati (parte Claude)

Dataset Kaggle nuovi (fine ottobre–2 novembre): LOTUS NP candidates, COCONUT 202611, PubChemLite/ExtLib compatti, vari
checkpoint di scorer e FPNet, `prvsiyan/casmi26-generation-code`. Niente spettri nuovi rilevanti: GNPS/MassBank dopo lo
snapshot del train aggiungono ~2.4 k identità (già usate per K6). Il recupero del tipo 2 non è il collo di bottiglia
(verità nel pool 96%), quindi cataloghi in più valgono poco. **La leva resta la generazione per il tipo 3.**

## 3. Evidenza nuova: i replay del generatore largo (mai riportati prima)

Generatore largo nel main engine: `EngineCfg(generate=True, gen_n_analog=24, gen_max_per_parent=200, gen_max_total=1000)`
(default 6/60/150). Banchi non esposti, metric identity ufficiale, bootstrap 5 000. Replica del base su T1 = identica
(Δ 0.000): i Δ non sono rumore di esecuzione.

| Banco | C477 → genwide | IC 95% | migl./pegg. |
|---|---:|---|---|
| T1 tipo 1 (250 NP timsTOF) | −0.007 | [−0.021, +0.005] | 5/9 |
| K6 tipo 2 pulito (288) | +0.012 | [0.000, +0.025] | 22/24 |
| **K6 tipo 3 pulito (735)** | **+0.035** | **[+0.027, +0.045]** | **90/17** |
| K7 NP tipo 3 (151) | +0.008 | [+0.002, +0.016] | 9/0 |
| K7 XL (60/400/4000) | +0.008 | [+0.000, +0.017] | 9/3 → non scala oltre 24/200/1000 |

I cambi di rank 1 su T1 (8) non sono candidati generati: sono candidati di catalogo che salgono perché il main engine
normalizza su liste più grandi.

**Interazione con lo strato midx** (emulato offline, `scripts/unseen/eval_docprior_layer.py`,
`artifacts/K6/docprior_layer_v1.json`): il prior di documentazione da solo dà T1 +0.003, K6 tipo 2 +0.006, tipo 3 −0.001,
K7 +0.002, coerente con il +0.002 del public (0.477→0.479). Il generatore largo **si somma** al prior:

| Banco | base+doc → genwide+doc | IC 95% |
|---|---:|---|
| T1 | −0.003 | [−0.015, +0.008] |
| K6 tipo 2 | +0.012 | [0.000, +0.026] |
| K6 tipo 3 | **+0.034** | [+0.026, +0.043] |
| K7 NP tipo 3 | +0.009 | [+0.002, +0.017] |

Con mix 35/30/35 (stima da T1 0.953, K6 tipo 2 0.41, tipo 3 0.04 e public 0.477): **atteso +0.012…+0.015** sul public.

## 4. Proposta

**P1 (principale): linea pubblica 0.480 + generatore largo.** Notebook bgunshui/alexchilton 0.480 verbatim (stessi
dataset e kernel source) più l'hook `genwide` già scritto per C477 (`scripts/build_c477_genwide.py`): patch del
`runner.py` in modo che le celle 36–37 del pipeline costruiscano il main engine con il generatore largo. Nient'altro.
Se l'ancora non c'è, il kernel va in errore (niente fallback silenzioso).

**P2 (controllo pulito): C477 + generatore largo** (bundle `kaggle/c477_genwide_bundle`, già costruito il 31/10 e mai
inviato). Misura la leva da sola contro il nostro 0.477; insieme a P1 separa l'effetto del generatore da quello dello
strato pubblico.

Decisione: P1 e P2 inviate entrambe. Il confronto è P2 vs C477 e P1 vs 0.480; un Δ ≤ 0.002 è rumore e non va
interpretato (regola utente).

## 5. Rischi

- **Runtime**: la cella 39 (liste Engine 1) passa da 671 s a 2 249 s su T1 (250 query); il run T1 completo da 3 885 s a
  5 720 s. Sul test (~400 molecole, T4 a 4 CPU) stimo +45…90 min su un rerun di ~3–4 h: dentro le 9 h, ma i time guard
  del pipeline potrebbero saltare stadi opzionali (±0.002).
- **Mix del test**: se il tipo 3 fosse < 15% il guadagno scende a ~+0.004. Il costo su T1 (−0.003…−0.007) è il caso peggiore.
- Il neural ensemble 0.480 dipende dall'output di un kernel pubblico (bgunshui): va pinnato alla versione corrente.

## 6. Dopo (se P1 regge)

Generatore mirato al dominio NP (modifiche di gruppi funzionali tipiche: glicosilazione, metilazione, idrossilazione,
acilazione) valutato su K6/K7 tipo 3, e protezione del rank 1 su liste con match di libreria forte (lib_max ≥ 0.87)
per azzerare il costo T1.
