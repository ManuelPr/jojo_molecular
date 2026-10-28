#!/usr/bin/env bash
# CPU-only job: JM cache v2 = competition train (source 0) + atlas external v3 (source 1), parallel prepare.
#SBATCH --job-name=casmi-jm-prep-atlas
#SBATCH --partition=ais4sum
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=240G
#SBATCH --time=06:00:00
#SBATCH --output=artifacts/cluster/jm-prep-atlas-%j.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
W=data/fastweb/jm_cache_v2_atlas
mkdir -p $W
.venv/bin/python -u scripts/cluster/jm_prepare_sharded.py \
  data/fastweb/competition/train.parquet:0 data/fastweb/iceberg_atlas/h_plus_external_v3:1 \
  --work $W --workers "$SLURM_CPUS_PER_TASK"
ln -sfn ../jm_cache_v1/pubchem_bank $W/pubchem_bank
