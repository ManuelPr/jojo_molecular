# Goal 5 — Domain-shift validation

## Scope

Goal 4 remains frozen.  This protocol creates a separate, instrument-matched
validation from `ingest_lib == enveda-np-examples` and never feeds the already
consulted Goal 4 final identities back into model selection.

The implementation is in `src/casmi26/domain_validation.py` and
`src/casmi26/goal5_pipeline.py`.  The authoritative membership is committed by
the SHA-256 hash in the Goal 5 result artifact; the normal exported manifest
redacts sealed identities and spectra.

## Independent review of the public claim

Repository audited: <https://github.com/shiferaxa/casmi26>, commit
`c75b3fe090c80c8b56572a74d81447a30f9981b9`, Apache-2.0.

The repository does contain the claimed evidence, but it is self-reported
experiment history rather than an independently reproducible leaderboard
calibration dataset:

- it describes 1,184 `enveda-np-examples` timsTOF spectra covering 250
  structures;
- three rankers scored 0.663, 0.736 and 0.758 on its class-2 split and then
  0.292, 0.331 and 0.339 on the public leaderboard, preserving their order;
- a random held-out training split predicted the opposite ordering;
- the same log explicitly reports a counterexample: changing analog similarity
  power improved class-2 MRR by about 0.028 (0.758 to 0.786) but decreased the
  public score from 0.339 to 0.336;
- its first class-3 result was invalid as a structure-absent estimate because
  COCONUT contained alternate records that canonicalized to the targets.  The
  author later moved class-3 analysis to a verified COCONUT-overlap cohort.

Conclusion: the source supports `enveda-np-examples` as a more relevant
development proxy than random training molecules, not as an unbiased estimator
of the hidden test score.  It is optimistic, small, and cannot validate
feature-level deltas around 0.03 on its own.  This project therefore uses it
with a new sealed split and reports A/B/C separately.

## Protocol

Queries must match both:

- source `enveda-np-examples`;
- instrument `timsTOF` after case/punctuation normalization.

Selection uses identity, provenance and a seeded hash only.  It never uses a
candidate rank or model score.  Every eligible identity requires at least one
independent reference acquisition with different content.  A SHA-256 content
hash is computed from precursor and normalized peaks, independent of row ID,
source label and instrument label.

The eligible identities are split once with seed 2027:

- 80% development;
- 20% sealed;
- at least one identity in each partition.

The 16 Goal 4 final identities in
`configs/goal5_prior_final_identities.txt` are excluded before membership is
constructed.  Sealed identities are absent from every development reference
library.  Opening the sealed manifest requires an explicit API flag.

### Visibility conditions

| Condition | Reference spectra of query identity | Structure in candidate catalog | Meaning |
|---|---:|---:|---|
| A — library-visible | yes, independent content only | yes | spectral-library ceiling |
| B — structure-known, spectra-hidden | no | yes | realistic structural retrieval/ranking |
| C — structure-absent | no | no | candidate-generation ceiling / novelty need |

All three conditions use identical query spectra within a stage.  Condition C
must have exact-structure recall zero by construction; any non-zero result is a
hard audit failure, not a success.

## Automatic audits

The audit fails closed on:

- query/reference row overlap;
- query/reference spectral-content overlap;
- same-identity reference leakage in B or C;
- validation identity present in the C catalog;
- validation identity missing from the B catalog;
- sealed identity in a development reference library;
- reuse of a Goal 4 final identity;
- wrong query source or instrument;
- missing source provenance;
- unknown or duplicated spectrum IDs;
- changed dataset fingerprint or inconsistent paired membership.

Sixteen focused unit tests cover construction, redaction, deterministic
membership and deliberate leakage mutations.

## Diagnostics reported

For train-reference, hidden test and domain cohort the run records:

- instrument, source, adduct and ion-mode counts;
- precursor and neutral-mass distributions;
- collision-energy mean and span;
- peak-count and median m/z-spacing distributions;
- spectra per molecule;
- low-relative-intensity fractions at 0.1% and 1%;
- base-peak log intensity when available;
- pairwise KS distance for numeric features;
- total-variation distance and unseen-category mass for categorical features.

The low-intensity values are explicitly noise-floor proxies derived from
normalized intensities, not detector electronic-noise measurements.

## Representativeness decision

The domain cohort can be called **instrument- and provenance-matched**, not
test-representative without qualification.  It shares the declared timsTOF
acquisition family and natural-product provenance with the expected test
domain, but selection into a public examples library, chemical coverage and
availability of repeated spectra remain different.  Only the public
leaderboard can later calibrate the absolute score, and it must not be used for
repeated hyperparameter tuning.

Quantitative membership, shift statistics and E7–E12 metrics are populated
from the private offline Kaggle artifact `goal5_results.json`; no official
submission is part of this protocol.

## Membership misurata al checkpoint

Il piano redatto dal run v3/v4 contiene 234 identità eleggibili, suddivise in
188 development e 46 sealed, e 1.097 spettri query. Dopo il cap introdotto per
evitare di materializzare inutilmente tutte le acquisizioni train, la reference
library contiene 2.932 spettri prima delle mask A/B/C; v2 ne aveva caricati
54.950. La membership non è cambiata e il commitment sealed è:

`a1aa831fe34de659c58c1f3e3aba746525297d6a960b149402f7db9dc9e0e959`.

Le statistiche di shift complete e le metriche E7–E12 non sono ancora
disponibili. La v3 ha fallito durante la prima valutazione development perché
l'ordine di anchor E12 conteneva tre candidati non presenti nella union pool.
La correzione filtra l'anchor sull'unione effettiva ed è coperta da un test di
regressione; la v4 che la esercita è ancora in corso al checkpoint.
