from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a minimal Kaggle script-kernel bundle")
    parser.add_argument("--entrypoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--code-file-name")
    parser.add_argument("--dataset-source", action="append", default=[])
    parser.add_argument("--competition-source", action="append", default=[])
    parser.add_argument("--extra-file", type=Path, action="append", default=[])
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args()
    if not args.entrypoint.is_file():
        raise SystemExit(f"Entrypoint not found: {args.entrypoint}")
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / (args.code_file_name or args.entrypoint.name)
    shutil.copy2(args.entrypoint, target)
    for extra in args.extra_file:
        if not extra.is_file():
            raise SystemExit(f"Extra file not found: {extra}")
        extra_target = args.output / extra.name
        if extra_target == target:
            raise SystemExit(f"Extra file collides with entrypoint: {extra.name}")
        shutil.copy2(extra, extra_target)
    metadata = {
        "id": args.id,
        "title": args.title,
        "code_file": target.name,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": bool(args.gpu),
        "enable_internet": False,
        "dataset_sources": args.dataset_source,
        "competition_sources": args.competition_source,
        "kernel_sources": [],
        "model_sources": [],
    }
    (args.output / "kernel-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Prepared Kaggle kernel bundle in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
