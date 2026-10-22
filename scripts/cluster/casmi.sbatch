#!/usr/bin/env bash
# Generic template: supply the site's account, partition and reservation to sbatch.
#SBATCH --job-name=casmi26-research
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gpus=1
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=slurm-%j.out

set -euo pipefail
REPO_DIR="${CASMI_REPO_DIR:-${SLURM_SUBMIT_DIR:?Submit from the repository root}}"
exec bash "$REPO_DIR/scripts/cluster/run.sh" "$@"
