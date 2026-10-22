# Historical public four-channel control

`upstream.py` is copied without modifications from
[shiferaxa/casmi26](https://github.com/shiferaxa/casmi26), commit
`c75b3fe090c80c8b56572a74d81447a30f9981b9`,
`kaggle/fork_base/notebook.py`. Retain LICENSE and NOTICE.

The source credits haideptry's four-channel notebook and prvsiyan's analog
propagation work. The direct Kaggle haideptry pull and prvsiyan version-32 pull
returned HTTP 403 on 2026-10-13. The public prvsiyan latest notebook was readable,
but had evolved beyond this control. This is therefore a reproduction of the
credited historical fork, not a claim of reproducing the currently advertised
Kaggle score or notebook version.

Builder: `scripts/build_public_baseline_bundle.py`. It lifts the original
prediction loop verbatim into `public_predict`; AST parity is unit-tested.
The wrapper performs offline asset checks, validation and scorer-aware output
deduplication. It does not introduce different ranker weights, candidate caps,
formula gating, fragmentation settings or pretrained models.

The final writer keeps the first occurrence of each official scorer identity,
preserves raw SMILES and ordering, and emits 1–25 guesses. It does not pad with
duplicate ethanol or add nearest-mass guesses. The original zero-window ethanol
fallback remains part of the control and is counted explicitly.

The eight ranker fits use the published training rows (no new fingerprint-model
training). Inputs are separately licensed CC-BY-NC-SA-4.0 by their owner. RDKit
retains its upstream license. All inputs are attached rather than committed.
`configs/public_baseline_manifest.json` contains exact asset hashes.

Compatibility adaptation: the public wheel is CPython 3.12, while the current
Kaggle runtime is 3.13. The control uses the same RDKit release, 2026.03.3,
through our previously verified CPython 3.13 wheel from the private asset dataset.

Validation uses only the fixed development manifest, never sealed membership.
It hides reference identities before scoring. The checkpoint and ranker row
producers do not expose a complete split manifest, so pretrained overlap is
unknown and the measured MRR is a diagnostic proxy, not an unbiased hidden-score
estimate. The reference universe differs from our E6 experiments; any comparison
is end-to-end rather than an isolated ranker ablation.

## Rebuild

Download versioned datasets into `artifacts/public_baseline/assets/<slug>`:

```powershell
kaggle datasets download prvsiyan/coconut-casmi26-candidates/2 -p artifacts/public_baseline/assets/coconut-casmi26-candidates --unzip
kaggle datasets download prvsiyan/casmi26-fp-models-v2/1 -p artifacts/public_baseline/assets/casmi26-fp-models-v2 --unzip
kaggle datasets download prvsiyan/casmi26-ranker-features/6 -p artifacts/public_baseline/assets/casmi26-ranker-features --unzip
.venv/Scripts/python.exe scripts/build_public_baseline_bundle.py
```

The build also needs the manifest-pinned CPython 3.13 RDKit wheel in
`kaggle/assets/`. It is available in the existing private asset dataset and
from the official package release. Build fails if the bytes/source differ
from the committed manifest; it cannot silently repin to newer assets.
The committed development-only config is sufficient; the old private Goal 5
artifact and sealed identities are not required.

After a terminal Kaggle run, download outputs and audit them:

```powershell
kaggle kernels output mperni/casmi26-public-baseline-control -p artifacts/public_baseline/kaggle_v2
.venv/Scripts/python.exe scripts/audit_public_baseline_outputs.py --output artifacts/public_baseline/kaggle_v2
```
