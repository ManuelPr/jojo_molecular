# Fastweb / Slurm handoff — 2026-10-22

The user already has a GPU-backed VS Code allocation. Use that allocation's
terminal for setup and the first preflight. This handoff does not submit a
cluster job or a Kaggle competition submission automatically.

## 1. Clone and choose Python

```bash
git clone https://github.com/ManuelPr/jojo_molecular.git
cd jojo_molecular
python3 --version
nvidia-smi
df -h .
bash scripts/cluster/setup.sh
bash scripts/cluster/run.sh preflight
```

If the site's GPU image already includes a working CUDA PyTorch, run setup with
that Python (`CASMI_BASE_PYTHON=/path/to/python`). The venv uses
`--system-site-packages` to retain it. Package installation requires network or
an approved local wheel mirror. For offline compute nodes, prepare the venv
in a compatible network-enabled environment on persistent shared storage.
An incompatible GPU architecture / driver / PyTorch is reported by the actual
CUDA forward/backward probe; do not assume any pip wheel supports the device.

For an environment outside the checkout, set `CASMI_VENV=/absolute/path/to/venv`
for both setup and run. No allocation-specific host, account, partition,
reservation or container image is assumed by these scripts.

## 2. Stage data on persistent storage

Git contains code and small configs, not competition data or model weights.
Supply the official `train.parquet` obtained through the user's Kaggle access,
after competition terms have already been accepted. Credentials remain outside
this repository. Kaggle access is unnecessary for preflight and unit tests.

```bash
export CASMI_TRAIN_PATH=/absolute/path/to/train.parquet
export CASMI_OUTPUT_DIR=/absolute/path/to/persistent/results/goal3-first
bash scripts/cluster/run.sh goal3
```

`goal3` invokes `scripts/run_goal3.py --device cuda` with its existing bounded
defaults (300,000 scanned rows, 12 fingerprint epochs, up to 50,000 catalog
structures). It runs the existing fingerprint/ranking research experiments;
it is **not** a new trained final fusion model and does not reproduce 0.440.
It needs training parquet and committed frozen identities, not all 16 v89
external datasets. Results include `goal3_results.json`, timing/leakage reports
and fingerprint checkpoints. Additional CLI args are forwarded, e.g.:

```bash
bash scripts/cluster/run.sh goal3 --fingerprint-epochs 2 --bootstrap-samples 50
```

Use a fresh output directory for each experiment. Increasing dataset sizes
changes memory/runtime requirements; measure the bounded experiment first.
For the existing CPU validation protocols:

```bash
export CASMI_OUTPUT_DIR=/absolute/path/to/persistent/results/validation-first
bash scripts/cluster/run.sh validation
```

## 3. Scheduler usage

Inside an already allocated GPU / VS Code job, run `bash .../run.sh` directly;
another `sbatch` is unnecessary for that allocation. Check job expiry and use
persistent output storage.

For a separate batch allocation, `scripts/cluster/casmi.sbatch` requests one
GPU, eight CPU cores, 32 GiB RAM and four hours. These are initial bounded-run
requests, not guaranteed performance requirements. From the repository root:

```bash
# Add the actual site-provided --account / --partition / --reservation flags.
sbatch scripts/cluster/casmi.sbatch preflight
# After successful preflight, with data/output variables exported:
sbatch scripts/cluster/casmi.sbatch goal3
```

The site's GPU-resource syntax and allocation policy may require adapting the
template. No site configuration was inferred from a hostname. Logs default to
`slurm-JOBID.out`; monitor with `squeue -u "$USER"` and `tail -f slurm-JOBID.out`.

## 4. What the 0.440 notebook needs

The exact public recipe is preserved in `third_party/flexon_v89/upstream.ipynb`
with attribution. `scripts/build_flexon_v89_reproduction.py` reconstructs its
Kaggle bundle using 16 pinned datasets from `configs/flexon_v89_assets.json`.
Its code expects `/kaggle/input` and `/kaggle/working`, Python 3.12 and the
documented Kaggle environment. **It is not a portable Fastweb entry point.**
Do not equate a Goal 3 training run with that notebook's 0.440. For future
cluster adaptation, first resolve all pinned weights/data, portable paths,
simulator dependencies and environment parity. The builder writes files only;
Kaggle upload/submission are separate explicit operations.

## 5. Next scientific work

The learned final-ranker and generative extensions discussed in chat remain
planned work. Start by constructing labelled candidate/evidence tables using
the actual competitive pipeline, with structure identities excluded from
reference spectra for type-2 validation. Public pretrained-model overlap must
be reported. Train/calibrate on development data and retain a sealed evaluation
cohort. Increasing GPU count does not fix label leakage or candidate coverage.

No private cluster transcript, credentials, raw datasets or run outputs are
part of this Git handoff. Original source/licence notices remain with vendored
code; root MIT terms do not relicense the external components.
