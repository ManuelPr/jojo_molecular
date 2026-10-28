#!/usr/bin/env bash
# CPU-only job: JM scorer training cache, then the PubChem negative bank.
#SBATCH --job-name=casmi-jm-prep
#SBATCH --partition=ais4sum
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=192G
#SBATCH --time=08:00:00
#SBATCH --output=artifacts/cluster/jm-prep-%j.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python -u scripts/cluster/jm_prepare.py --workers "$SLURM_CPUS_PER_TASK"
.venv/bin/python -u scripts/cluster/jm_build_pubchem_bank.py --workers "$SLURM_CPUS_PER_TASK"
