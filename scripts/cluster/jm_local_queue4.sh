#!/usr/bin/env bash
# After B2 (PID given) exits, train base seed 2 with a 16k-step cosine schedule for the ensemble.
set -uo pipefail
cd "$(dirname "$0")/../.."
while kill -0 "$1" 2>/dev/null; do sleep 30; done
.venv/bin/python -u kaggle/jm_scorer/train_jm.py --config kaggle/jm_scorer/configs/jm_base.json \
  --output artifacts/jm/base_s2_local --set seed=20261029 steps=16000 \
  > artifacts/jm/base_s2_local.log 2>&1
