from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from casmi26.dreams_probe import compute_official_dreams_embeddings


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute frozen upstream DreaMS embeddings; never trains or submits"
    )
    parser.add_argument("--spectra", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    if not args.spectra.is_file():
        raise SystemExit(f"Spectra file not found: {args.spectra}")
    if not args.checkpoint.is_file():
        raise SystemExit(f"Checkpoint not found: {args.checkpoint}")

    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    embeddings = compute_official_dreams_embeddings(
        args.spectra,
        checkpoint_path=args.checkpoint,
        batch_size=args.batch_size,
    )
    elapsed = time.perf_counter() - started
    embeddings_path = args.output / "dreams_embeddings.npy"
    np.save(embeddings_path, embeddings, allow_pickle=False)
    report = {
        "mode": "frozen_encoder_only",
        "training_performed": False,
        "spectra_path": str(args.spectra),
        "spectra_sha256": _sha256(args.spectra),
        "checkpoint_path": str(args.checkpoint),
        "checkpoint_sha256": _sha256(args.checkpoint),
        "embeddings_path": str(embeddings_path),
        "embedding_shape": list(embeddings.shape),
        "embedding_dtype": str(embeddings.dtype),
        "batch_size": args.batch_size,
        "elapsed_seconds": elapsed,
        "seconds_per_spectrum": elapsed / len(embeddings) if len(embeddings) else None,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }
    (args.output / "dreams_probe_runtime.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
