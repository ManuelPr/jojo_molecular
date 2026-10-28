#!/usr/bin/env bash
# CPU-only job: convert every downloaded atlas formula to train-like shards (Codex parser), excluding train identities.
#SBATCH --job-name=casmi-atlas-conv
#SBATCH --partition=ais4sum
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=128G
#SBATCH --time=06:00:00
#SBATCH --output=artifacts/cluster/atlas-conv-%j.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
export OMP_NUM_THREADS=1
.venv/bin/python -u scripts/cluster/atlas_to_parquet.py \
  --src data/fastweb/iceberg_atlas/h_plus --out data/fastweb/iceberg_atlas/h_plus_external_v3 \
  --max-structures 400 --workers "$SLURM_CPUS_PER_TASK" \
  --exclude-identities data/fastweb/jm_cache_v1/train_molecules.parquet \
  --report artifacts/J5/external_v3_report.json
