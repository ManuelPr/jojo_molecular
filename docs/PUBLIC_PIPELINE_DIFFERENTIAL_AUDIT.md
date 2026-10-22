# Audit differenziale delle due submission problematiche

**Rettifica API 2026-10-13:** `57109254` ha public score `0.000` senza errore;
`57135939` ha score assente e `error_description`: "Your notebook hit an
unhandled error while rerunning your code. Note that the hidden dataset can be
larger/smaller/different than the public dataset". Lo stato API COMPLETE da
solo non implica un rerun riuscito. La seconda non misura il risultato di C1.

Data: 2026-10-13. Scope: codice locale, artifact dei rehearsal, documentazione
e sorgenti pubbliche. Nessun training, VM, job Kaggle o nuova submission.

## Conclusione

**E6 non riproduce la baseline pubblica competitiva Analog Propagation.**
È un esperimento ridotto di analog propagation e nearest-mass. Il crash della
seconda submission impedisce di misurare l'effetto di C1 sul test nascosto.
Non dimostra che tutte le truth public siano assenti da C1. Esiste evidenza
di un guasto nel rerun hidden, ma il messaggio generico non identifica la causa.
La causa esatta resta aperta. Le differenze architetturali sono invece provate.

## Confronto concreto

| Componente | Prima submission 57109254 | Seconda 57135939 | Baseline pubblica documentata |
|---|---|---|---|
| Catalogo | C0, 49.195 strutture | C1, 271.439 strutture | Train + COCONUT, circa 710–712 mila |
| Reference nel rehearsal | 127 spettri | 127 spettri | Libreria train estesa e rappresentanti per struttura |
| Analogi usati | Top 5 | Top 5 | Top 100 |
| Candidate retrieval | Top 100 nearest-mass | Identico | Finestra ppm; pruning versionato |
| Direct library evidence nel punteggio | Nessun canale separato | Identico | Similarità entropy per struttura |
| Spectrum-to-fingerprint | Nessun checkpoint usato | Identico | FPNet pretrained |
| Fragmentation e ranker | Fusione lineare massa/analog | Identica | MetFrag-lite e ranker multicanale appreso |
| Formula | Riordina solo la formula del primo nearest-mass | Identico | Più evidenze per valutare i candidati |

Fonte del riferimento: [log dell'autore shiferaxa/casmi26](https://raw.githubusercontent.com/shiferaxa/casmi26/main/docs/plan.md).
I risultati sono autodichiarati, non riprodotti da noi: library-only 0,119;
fork multicanale da 0,290 a 0,339. L'autore riporta benefici dall'ampliamento
del pruning e un caso in cui la validation casuale predice l'ordine sbagliato
dei ranker. Il log contiene rettifiche: leggere le conclusioni aggiornate,
non assumere definitive le sue ipotesi iniziali.

Il repository [gnshx](https://github.com/gnshx/Enveda-CASMI-2026---Molecule-ID-From-Mass-Spectra)
descrive anche fingerprint prediction, database esterni, ranker e forward
rescoring. Conferma che la pipeline descritta è molto diversa da E6;
0,420 è uno score dichiarato dall'autore, non verificato da noi sul leaderboard.

La [pagina ufficiale Kaggle](https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra)
è stata consultata ma il web reader non ne espone il corpo. Non sono stati
ricontrollati direttamente leaderboard, notebook prvsiyan o regolamento corrente.
Gli esiti delle nostre submission provengono dagli artifact/documenti locali.

## Nuove verifiche riproducibili

```powershell
.venv/Scripts/python.exe scripts/audit_submission_ranking_limits.py
```

Output: `artifacts/zero_score_recovery/ranking_limits.json`.

- C1 cambia tutte le 400 liste del rehearsal e 282 prime scelte rispetto a C0
  (confronto stringhe SMILES). Non è stato semplicemente riusato il CSV visibile.
  Questo non verifica il CSV del rerun hidden.
- Recovery: 127 reference e 5 analoghi restituiti per ognuna delle 400 query.
- Errore massa del candidato numero 100: mediana 13,98 ppm, p90 64,87 ppm,
  massimo 342,03 ppm. Sono errori rispetto alla massa query del placeholder,
  non alla truth hidden. Top-100 fisso include candidati lontani in zone sparse
  e può escludere isomeri corretti nelle zone dense.
- Fixture sintetica: truth al rank massa 30, formula diversa dall'anchor,
  rank evidenza 1 → rank finale **30**, fuori dai primi 25.
- Fixture sintetica: 100 candidati a massa uguale, truth al rank massa 100
  per tie-break sull'ID e rank evidenza 1 → rank finale **67**, peso 0,5.
  Gli altri score di evidenza sono uguali a zero.

Le due fixture provano limiti dell'algoritmo, non la loro frequenza nel hidden.
Isomeri con la stessa formula hanno massa identica: il tie-break sull'InChIKey
non è evidenza chimica, ma E6 dà comunque peso a quell'ordine nella fusione.
Il vincolo sulla formula anchor è deliberato: può essere una scelta modellistica
dannosa senza essere un errore di sintassi.

## Evidenze e incertezze

Dimostrati: C0 incompleto sul proxy; validation Goal 4 piccola e selezionata
nello stesso universo; reference ridotte; canali pubblici principali assenti;
limiti di ranking sopra. Il bug di rimozione stereochimica è stato corretto,
ma non cambiava nessuno dei 10.000 slot della prima submission.

Non dimostrati: assenza totale delle truth hidden da C1; zero matematico
anziché arrotondato; correttezza semantica del rerun hidden. Il resoconto
pubblico di library-only train con score positivo è un indizio contro la
spiegazione solo coverage, non un confronto a parità di codice/versione/split.
Un CSV accettato prova validità sintattica, non correttezza delle predizioni.

## Esperimento successivo discriminante

Prima di ampliare ancora il database, confrontare sul development domain-matched
con C1 fisso: mass-only, E6 congelato, direct library retrieval con reference
estese e baseline pubblica con asset/versioni fissati. Separare membership,
Recall@100, Recall@25 dopo ranking e MRR. Misurare truth fuori dalla formula
anchor, gruppi a massa uguale e candidati nella finestra ppm.

Isolare poi numero reference, top-5/top-100 analoghi, vincolo anchor e pareggi
di massa. Seguire il workflow VM già deciso per esperimenti pesanti, senza
modificare contemporaneamente catalogo, reference e ranking.

Per coverage esterna usare un holdout di identità assenti da C1, con COCONUT
costruito indipendentemente e chiavi normalizzate con lo scorer ufficiale.
Condition C che rimuove fisicamente ogni copia della truth senza offrirla
tramite un catalogo esterno dà zero per costruzione e non misura questa capacità.
Nessuna terza submission prima di un confronto offline informativo.
