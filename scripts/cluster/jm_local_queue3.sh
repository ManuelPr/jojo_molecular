#!/usr/bin/env bash
# After base_s1_local (PID given) exits and the train+atlas cache exists, train B2 = base + atlas spectra.
set -uo pipefail
cd "$(dirname "$0")/../.."
while kill -0 "$1" 2>/dev/null; do sleep 30; done
until [ -f data/fastweb/jm_cache_v2_atlas/spectra.parquet ] && [ -e data/fastweb/jm_cache_v2_atlas/pubchem_bank/bank.parquet ]; do sleep 60; done
.venv/bin/python -u kaggle/jm_scorer/train_jm.py --config kaggle/jm_scorer/configs/jm_base.json \
  --output artifacts/jm/base_atlas_s1_local \
  --set 'work="/home/mpernigotto/jojo_molecular/data/fastweb/jm_cache_v2_atlas"' external_molecule_weight=0.5 real_spectrum_prob=1.0 \
  > artifacts/jm/base_atlas_s1_local.log 2>&1
