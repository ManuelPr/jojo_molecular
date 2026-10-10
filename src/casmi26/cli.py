from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import ParquetSpectrumReader, PreprocessConfig, preprocess_spectrum
from .pipeline import MiniTrainConfig, run_mini_training
from .submission import validate_submission


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="casmi26")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-data", help="Inspect and preprocess parquet rows")
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.add_argument("--max-rows", type=int, default=1000)

    train_parser = subparsers.add_parser("mini-train", help="Run the bounded end-to-end baseline")
    train_parser.add_argument("--train", type=Path, required=True)
    train_parser.add_argument("--test", type=Path, required=True)
    train_parser.add_argument("--output", type=Path, required=True)
    train_parser.add_argument("--submission", type=Path)
    train_parser.add_argument("--max-molecules", type=int, default=128)
    train_parser.add_argument("--max-scan-rows", type=int, default=300000)
    train_parser.add_argument("--top-k", type=int, default=25)
    train_parser.add_argument("--seed", type=int, default=2026)

    validate_parser = subparsers.add_parser("validate-submission")
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument("--sample", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect-data":
        reader = ParquetSpectrumReader(args.path)
        processed = 0
        retained_peaks = 0
        invalid = 0
        for record in reader.iter_records(max_rows=args.max_rows):
            try:
                spectrum = preprocess_spectrum(record, PreprocessConfig())
                processed += 1
                retained_peaks += len(spectrum.mz)
            except ValueError:
                invalid += 1
        result = {
            "path": str(args.path),
            "rows": reader.num_rows,
            "is_train": reader.is_train,
            "sampled": processed + invalid,
            "processed": processed,
            "invalid": invalid,
            "mean_retained_peaks": retained_peaks / processed if processed else 0.0,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "mini-train":
        config = MiniTrainConfig(
            seed=args.seed,
            max_molecules=args.max_molecules,
            max_scan_rows=args.max_scan_rows,
            top_k=args.top_k,
        )
        metrics = run_mini_training(
            args.train,
            args.test,
            args.output,
            config=config,
            submission_path=args.submission,
        )
        print(json.dumps(metrics, indent=2, sort_keys=True))
        return 0


    expected = None
    if args.sample:
        import pandas as pd

        expected = pd.read_csv(args.sample)["molecule_id"].astype(str).tolist()
    validation = validate_submission(args.path, expected_molecule_ids=expected)
    print(json.dumps(validation.to_dict(), indent=2, sort_keys=True))
    return 0 if validation.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

