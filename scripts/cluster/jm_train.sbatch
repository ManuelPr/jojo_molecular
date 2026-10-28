#!/usr/bin/env bash
# One JM scorer training run on one H100: sbatch jm_train.sbatch CONFIG OUTPUT [key=json ...]
#SBATCH --job-name=casmi-jm-train
#SBATCH --partition=ais4sum
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:1
#SBATCH --mem=96G
#SBATCH --time=14:00:00
#SBATCH --output=artifacts/cluster/jm-train-%j.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
config=$1; output=$2; shift 2
.venv/bin/python -u kaggle/jm_scorer/train_jm.py --config "$config" --output "$output" --set "$@"
