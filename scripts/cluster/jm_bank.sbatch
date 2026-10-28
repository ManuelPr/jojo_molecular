#!/usr/bin/env bash
# CPU-only job: train structure table, then the PubChem negative bank (independent of prepare.py).
#SBATCH --job-name=casmi-jm-bank
#SBATCH --partition=ais4sum
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=160G
#SBATCH --time=06:00:00
#SBATCH --output=artifacts/cluster/jm-bank-%j.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python -u scripts/cluster/jm_train_molecules.py --workers "$SLURM_CPUS_PER_TASK"
.venv/bin/python -u scripts/cluster/jm_build_pubchem_bank.py --workers "$SLURM_CPUS_PER_TASK" \
  --molecules data/fastweb/jm_cache_v1/train_molecules.parquet
