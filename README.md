# jojo_molecular — Enveda CASMI 2026

Joestar dinasty repo created to smash kaggle comps.

Code, experiment history and reproducible Kaggle notebook builders for molecule
identification from tandem mass spectra.

## Current status

- Public Flexon v89 reproduction: **0.440 MRR@25**, independently submitted.
- Our PubChem forward-consensus experiment: **0.440**, no measured improvement.
- Public recipes audited through **2026-10-22**: strongest verified public
  notebook score **0.464**, not reproduced here. Flexon's latest multi-energy
  treatment is 0.457 versus its best V47 at 0.462.
- Fastweb H100 preflight/tests passed according to the remote report; official
  training data and external assets still need staging. See the
  [selected GPU experiments](docs/FASTWEB_GPU_EXPERIMENT_PLAN.md).
- The proposed learned final fusion/ranker and a new generative model are
  **research plans, not newly trained models included in this repository**.

See [project state](docs/PROJECT_STATE.md), [master plan](CASMI26_MASTER_PLAN.md)
and [public notebook comparison](docs/PUBLIC_NOTEBOOK_GAP_2026-10-22.md).

## Start in the existing Fastweb GPU / VS Code allocation

For the already verified allocation, preserve the environment and follow the
[updated data/experiment plan](docs/FASTWEB_GPU_EXPERIMENT_PLAN.md). The setup
commands below are for a fresh checkout/environment. Goal 3 remains an existing
research regression run; competitive-pipeline evidence and G1/G2 now take priority.

```bash
git clone https://github.com/ManuelPr/jojo_molecular.git
cd jojo_molecular
bash scripts/cluster/setup.sh
bash scripts/cluster/run.sh preflight
```

If already cloned, use `git pull --ff-only` before setup. Setup requires Python
3.11–3.13 and network access to install missing dependencies; it reuses packages
from the base Python environment when possible. Use a cluster-provided Python /
PyTorch environment compatible with the allocated GPU and driver.

The preflight performs an actual CUDA forward/backward calculation and writes
an environment report. It needs no competition data and performs no Kaggle
submission. To start the existing bounded fingerprint-training experiment:

```bash
export CASMI_TRAIN_PATH=/absolute/path/to/train.parquet
export CASMI_OUTPUT_DIR=/absolute/path/to/persistent/results/goal3-first
bash scripts/cluster/run.sh goal3
```

This trains/evaluates the existing **Goal 3 research pipeline**, not the 0.440
notebook or the proposed new final ranker. Data, pretrained weights and generated
artifacts are not stored in Git. Follow the [Fastweb handoff](docs/FASTWEB_HANDOFF.md)
for data, scheduler usage, output files and the separate Kaggle reproduction.

## Tests

```bash
source .venv/bin/activate
python -m pytest tests/unit tests/integration -m 'not real_data'
```

## Sources and licences

The root licence covers original project contributions. Vendored code,
notebooks, datasets and models retain their upstream licences and attribution.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and each `third_party/` notice.
