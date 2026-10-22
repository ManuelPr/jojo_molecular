#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${CASMI_VENV:-$REPO_DIR/.venv}/bin/python"
MODE="${1:-preflight}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ ! -x "$PYTHON" ]]; then
    printf 'Missing environment. Run: bash scripts/cluster/setup.sh\n' >&2
    exit 2
fi
cd "$REPO_DIR"
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-${SLURM_CPUS_PER_TASK:-4}}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-$OMP_NUM_THREADS}"
export CASMI_OUTPUT_DIR="${CASMI_OUTPUT_DIR:-$REPO_DIR/artifacts/cluster/${SLURM_JOB_ID:-interactive}-$(date -u +%Y%m%dT%H%M%SZ)}"

case "$MODE" in
    preflight|goal3|validation) ;;
    *) printf 'Usage: bash scripts/cluster/run.sh {preflight|goal3|validation} [extra arguments]\n' >&2; exit 2 ;;
esac
mkdir -p "$CASMI_OUTPUT_DIR"
ARGS=(--output "$CASMI_OUTPUT_DIR/preflight.json")
if [[ -n "${CASMI_TRAIN_PATH:-}" ]]; then ARGS+=(--train "$CASMI_TRAIN_PATH"); fi
if [[ "$MODE" != validation ]]; then ARGS+=(--require-cuda); fi

if [[ "$MODE" == preflight ]]; then
    exec "$PYTHON" scripts/cluster_preflight.py "${ARGS[@]}" "$@"
fi
if [[ -z "${CASMI_TRAIN_PATH:-}" ]]; then
    printf 'Set CASMI_TRAIN_PATH to the absolute path of train.parquet.\n' >&2
    exit 2
fi
"$PYTHON" scripts/cluster_preflight.py "${ARGS[@]}"
case "$MODE" in
    goal3)
        exec "$PYTHON" scripts/run_goal3.py --train "$CASMI_TRAIN_PATH" \
            --output "$CASMI_OUTPUT_DIR" --device cuda "$@"
        ;;
    validation)
        exec "$PYTHON" scripts/run_validation.py --train "$CASMI_TRAIN_PATH" \
            --output "$CASMI_OUTPUT_DIR" "$@"
        ;;
esac
