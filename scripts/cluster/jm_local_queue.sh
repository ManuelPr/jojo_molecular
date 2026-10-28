#!/usr/bin/env bash
# Sequential JM runs on the GPU of the current allocation, after the training cache exists.
set -uo pipefail
cd "$(dirname "$0")/../.."
until [ -f data/fastweb/jm_cache_v1/spectra.parquet ] && [ -f data/fastweb/jm_cache_v1/pubchem_bank/bank.parquet ]; do sleep 60; done
C=kaggle/jm_scorer/configs/jm_small.json
.venv/bin/python -u kaggle/jm_scorer/train_jm.py --config $C --output artifacts/jm/small_b0_sanpierlike \
  --set pubchem_negatives=0 tims_boost=1.0 tims_spectrum_prob=0.0 spectra_per_molecule=1 fp_in_softmax=0.0 \
  > artifacts/jm/small_b0_sanpierlike.log 2>&1
.venv/bin/python -u kaggle/jm_scorer/train_jm.py --config $C --output artifacts/jm/small_b1_ours \
  > artifacts/jm/small_b1_ours.log 2>&1
