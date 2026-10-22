"""Check the actual execution environment without downloading data or submitting jobs."""
from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import shutil
import sys


def check_runtime(*, require_cuda: bool = False, train: Path | None = None) -> dict:
    errors: list[str] = []
    report: dict = {
        "python": platform.python_version(),
        "platform": platform.system(),
        "packages": {},
        "cuda_available": False,
        "gpu_forward_backward_passed": False,
    }
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        errors.append("Use Python 3.11, 3.12 or 3.13.")
    for package in ("numpy", "pandas", "pyarrow", "rdkit", "scikit-learn", "lightgbm", "torch"):
        try:
            report["packages"][package] = version(package)
        except PackageNotFoundError:
            report["packages"][package] = None
            if package != "torch":
                errors.append(f"Missing dependency: {package}")
    if report["packages"]["rdkit"] not in {"2026.3.3", "2026.03.3"}:
        errors.append("Official metric requires RDKit 2026.03.3.")
    try:
        import torch

        report["torch_cuda_build"] = torch.version.cuda
        report["cuda_available"] = bool(torch.cuda.is_available())
        if report["cuda_available"]:
            report["gpus"] = [
                {"index": i, "name": torch.cuda.get_device_properties(i).name,
                 "vram_bytes": torch.cuda.get_device_properties(i).total_memory}
                for i in range(torch.cuda.device_count())
            ]
            # An import or nvidia-smi alone does not establish kernel compatibility.
            x = torch.randn(32, 32, device="cuda", requires_grad=True)
            loss = (x @ x.T).square().mean()
            loss.backward()
            torch.cuda.synchronize()
            if not bool(torch.isfinite(loss)) or not bool(torch.isfinite(x.grad).all()):
                raise RuntimeError("Non-finite CUDA result or gradients")
            report["gpu_forward_backward_passed"] = True
    except (ImportError, OSError, RuntimeError, AssertionError) as exc:
        report["torch_error"] = str(exc)
        if require_cuda:
            errors.append(f"CUDA probe failed: {exc}")
    if require_cuda and not report["gpu_forward_backward_passed"]:
        errors.append("A working CUDA GPU is required; check the allocation and PyTorch build.")
    if train is not None:
        if not train.is_file():
            errors.append(f"Training parquet does not exist: {train}")
        else:
            try:
                from casmi26.data import ParquetSpectrumReader

                reader = ParquetSpectrumReader(train)
                report["train"] = {"path": str(train.resolve()), "rows": reader.num_rows,
                                   "has_training_labels": reader.is_train}
                if not reader.is_train or reader.num_rows == 0:
                    errors.append("Provide a nonempty training parquet with structure labels.")
            except (ImportError, OSError, ValueError, KeyError) as exc:
                errors.append(f"Training parquet check failed: {exc}")
    report["errors"] = errors
    report["passed"] = not errors
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-cuda", action="store_true")
    parser.add_argument("--train", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/cluster/preflight.json"))
    args = parser.parse_args()
    report = check_runtime(require_cuda=args.require_cuda, train=args.train)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(args.output.parent)
    report["output_free_bytes"] = usage.free
    if usage.free < 2 * 1024**3:
        report["warnings"] = ["Less than 2 GiB free at output location; provision space before data runs."]
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
