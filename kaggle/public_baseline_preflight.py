"""Offline asset integrity checks; concatenated before unchanged upstream."""
import os
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["NUMBA_NUM_THREADS"] = "4"
import glob
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


def file_hash(path):
    h = sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


ACTUAL_ASSETS = {}
for name, item in PINNED_MANIFEST["files"].items():
    matches = glob.glob("/kaggle/input/**/" + name, recursive=True)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one asset {name}, found {len(matches)}")
    path = matches[0]
    if Path(path).stat().st_size != item["bytes"] or file_hash(path) != item["sha256"]:
        raise RuntimeError(f"Asset drift: {name}")
    ACTUAL_ASSETS[name] = path
wheel = next(path for name, path in ACTUAL_ASSETS.items() if name.startswith("rdkit-") and name.endswith(".whl"))
subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", wheel], check=True)
from rdkit import rdBase
if rdBase.rdkitVersion != "2026.03.3":
    raise RuntimeError("RDKit scorer version mismatch")
Path("public_baseline_manifest.json").write_text(json.dumps(PINNED_MANIFEST, indent=2))
print("[CONTROL] Asset hashes verified; RDKit", rdBase.rdkitVersion, flush=True)
