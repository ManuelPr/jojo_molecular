"""Build versioned, identity-normalized training shards from ICEBERG atlas MGF.

Use --exclude-identities for canonical held-out identity lists (or a molecules
parquet to exclude every identity in that file). Integration must also exclude
all spectra of validation identities when assigning the final training split.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from casmi26.atlas import convert_file, read_exclusions  # noqa: E402

_OPTIONS = {}


def initialize(options):
    global _OPTIONS
    _OPTIONS = options


def convert(path):
    return convert_file(path, **_OPTIONS)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", type=Path, default=ROOT / "data/fastweb/iceberg_atlas/h_plus")
    p.add_argument("--out", type=Path, default=ROOT / "data/fastweb/iceberg_atlas/h_plus_parquet_v2")
    p.add_argument("--ce-quantiles", default="0.25,0.5,0.8")
    p.add_argument("--max-structures", type=int, default=400, help="deterministic sample per formula")
    p.add_argument("--min-peaks", type=int, default=3)
    p.add_argument("--seed", type=int, default=20261028)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--exclude-identities", type=Path, nargs="*", default=[])
    p.add_argument("--only-formulas", type=Path, help="restrict to these formula filenames")
    p.add_argument("--limit-files", type=int)
    p.add_argument("--force", action="store_true", help="rebuild stale shards")
    p.add_argument("--report", type=Path, required=True, help="run manifest outside the shared download directory")
    a = p.parse_args()
    if a.workers < 1 or (a.limit_files is not None and a.limit_files < 1):
        p.error("workers and limit-files must be positive")
    files = sorted(a.src.glob("*.mgf.gz"))
    if a.only_formulas:
        formulas = set(a.only_formulas.read_text().split())
        files = [f for f in files if f.name.removesuffix(".mgf.gz") in formulas]
    if a.limit_files:
        files = files[:a.limit_files]
    if not files:
        p.error("no downloaded formula files selected")
    exclusions, provenance = read_exclusions(a.exclude_identities)
    options = dict(out=a.out, quantiles=tuple(map(float, a.ce_quantiles.split(","))),
                   max_structures=a.max_structures, min_peaks=a.min_peaks, seed=a.seed,
                   excluded=exclusions, exclusion_sources=provenance, force=a.force)
    counts, reports = Counter(), []
    a.report.parent.mkdir(parents=True, exist_ok=True)
    run = dict(started_utc=datetime.now(timezone.utc).isoformat(), command=sys.argv,
               state="running", file_count=len(files), exclusions=provenance)
    a.report.write_text(json.dumps(run, indent=2) + "\n")
    try:
        with ProcessPoolExecutor(a.workers, initializer=initialize, initargs=(options,)) as pool:
            for report in pool.map(convert, files):
                counts.update(report["counts"])
                reports.append(dict(input=report["input"], output=report["output"],
                                    output_sha256=report["output_sha256"], cache_hit=report["cache_hit"]))
                print(json.dumps(dict(files_done=len(reports), files_total=len(files), counts=dict(counts))), flush=True)
        run["state"] = "complete"
    except Exception as exc:
        run.update(state="failed", error=str(exc))
        raise
    finally:
        run.update(finished_utc=datetime.now(timezone.utc).isoformat(), counts=dict(counts), shards=reports,
                   structure_count_scope="sum across shards; global uniqueness must be checked at merge")
        a.report.write_text(json.dumps(run, indent=2) + "\n")


if __name__ == "__main__":
    main()
