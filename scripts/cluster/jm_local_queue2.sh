#!/usr/bin/env bash
# After the small ablations finish, train the 30M base model on the shared GPU of job 2545.
set -uo pipefail
cd "$(dirname "$0")/../.."
while pgrep -f "artifacts/jm/small_b[01]" >/dev/null; do sleep 30; done
.venv/bin/python -u kaggle/jm_scorer/train_jm.py --config kaggle/jm_scorer/configs/jm_base.json \
  --output artifacts/jm/base_s1_local > artifacts/jm/base_s1_local.log 2>&1
