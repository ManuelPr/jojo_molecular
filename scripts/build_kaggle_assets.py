from __future__ import annotations

import argparse
from pathlib import Path
import shutil


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--rdkit-wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("kaggle/assets"))
    parser.add_argument(
        "--extra-file",
        type=Path,
        action="append",
        default=[],
        help="Additional small offline asset to copy (repeatable)",
    )
    args = parser.parse_args()

    project_wheels = sorted(args.dist.glob("casmi26_baseline-*.whl"))
    if len(project_wheels) != 1:
        raise SystemExit(f"Expected exactly one project wheel in {args.dist}, found {project_wheels}")
    if not args.rdkit_wheel.is_file():
        raise SystemExit(f"RDKit wheel not found: {args.rdkit_wheel}")

    args.output.mkdir(parents=True, exist_ok=True)
    project_target = args.output / project_wheels[0].name
    rdkit_target = args.output / args.rdkit_wheel.name
    for pattern in ("casmi26_baseline-*.whl", "rdkit-*.whl"):
        for old_wheel in args.output.glob(pattern):
            if old_wheel.resolve() != args.rdkit_wheel.resolve():
                old_wheel.unlink()
    if project_wheels[0].resolve() != project_target.resolve():
        shutil.copy2(project_wheels[0], project_target)
    if args.rdkit_wheel.resolve() != rdkit_target.resolve():
        shutil.copy2(args.rdkit_wheel, rdkit_target)
    copied_extras = []
    for extra in args.extra_file:
        if not extra.is_file():
            raise SystemExit(f"Extra asset not found: {extra}")
        target = args.output / extra.name
        if extra.resolve() != target.resolve():
            shutil.copy2(extra, target)
        copied_extras.append(extra.name)
    print(
        f"Prepared {args.output} with {project_wheels[0].name}, "
        f"{args.rdkit_wheel.name}, extras={copied_extras}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
