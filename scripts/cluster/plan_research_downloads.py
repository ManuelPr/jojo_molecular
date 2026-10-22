"""Print pinned Fastweb research downloads; never download or execute commands.

Run this with any Python 3.11+ interpreter. Kaggle credentials and a working CLI
are needed only when the printed commands are executed separately.
"""
from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path, PurePosixPath


REPO = Path(__file__).resolve().parents[2]


def download_plan(manifest: dict, root: PurePosixPath, group: str) -> list[dict]:
    rows = []
    for item in manifest["assets"]:
        if group == "starter" and item["group"] != "starter":
            continue
        target = root / item["directory"]
        if item["kind"] == "competition_file":
            command = ["kaggle", "competitions", "download", item["competition"],
                       "-f", item["file"], "-p", str(target)]
        elif item["kind"] == "dataset":
            version = item["version"]
            if not isinstance(version, int) or version < 1:
                raise ValueError(f"An explicit positive version is required: {item['source']}")
            command = ["kaggle", "datasets", "download",
                       f"{item['source']}/{version}", "-p", str(target), "--unzip"]
        else:
            raise ValueError(f"Unknown asset kind: {item['kind']}")
        rows.append({"directory": str(target), "api_bytes": item["api_bytes"],
                     "command": command})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=PurePosixPath, required=True,
                        help="Destination path on Linux/Fastweb, even if planning on Windows")
    parser.add_argument("--group", choices=("starter", "full"), default="starter")
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    parser.add_argument("--manifest", type=Path,
                        default=REPO / "configs/fastweb_research_assets_2026-10-22.json")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    plan = download_plan(manifest, args.root, args.group)
    if args.format == "json":
        print(json.dumps({"executes_downloads": False, "group": args.group,
                          "api_total_bytes": sum(x["api_bytes"] for x in plan),
                          "downloads": plan}, indent=2))
        return
    print("# Plan only. Review quota, credentials and licences before executing.")
    print("# API file sizes exclude extra caches, outputs and archive overhead.")
    print(f"# Selected API bytes: {sum(x['api_bytes'] for x in plan):,}")
    for row in plan:
        print(shlex.join(["mkdir", "-p", row["directory"]]))
        print(shlex.join(row["command"]))
    print("# Inspect official downloads for ZIP packaging and extract train.parquet if needed.")
    print("# Record local SHA256 hashes; a version pin alone does not verify downloaded bytes.")


if __name__ == "__main__":
    main()
