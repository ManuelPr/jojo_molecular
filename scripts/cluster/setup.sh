#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="${CASMI_VENV:-$REPO_DIR/.venv}"
BASE_PYTHON="${CASMI_BASE_PYTHON:-python3}"

"$BASE_PYTHON" -c 'import sys; assert (3, 11) <= sys.version_info[:2] < (3, 14), "Use Python 3.11, 3.12 or 3.13"'
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    "$BASE_PYTHON" -m venv --system-site-packages "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install -e "$REPO_DIR[goal3,dev]"
printf 'Environment ready: %s\n' "$VENV_DIR"
printf 'Next: bash scripts/cluster/run.sh preflight\n'
