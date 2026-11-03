"""Score one extra sanpier-kit bundle on finished K2 replays, writing k2_export/neural_<arm>.parquet next to the existing
arms (same candidates, evidence and query spectra as the other neural_*.parquet; candidates.parquet is not touched).

Usage: score_extra_arm.py --arm bgunshui --bundle data/fastweb/bgunshui_bundle --device cuda:0 RUN [RUN ...]
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm', required=True)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--device', default='cuda')
    p.add_argument('runs', nargs='+', type=Path)
    a = p.parse_args()
    sys.path[:0] = [str(ROOT/'artifacts/k2_replay/src')]
    import neural_scores
    for run in a.runs:
        target = run/'k2_export'/f'neural_{a.arm}.parquet'
        if target.is_file():
            print('exists', target, flush=True)
            continue
        neural_scores.score(str(a.bundle), 'final_model.pt', str(run/'frozen_candidate_evidence.parquet'),
                            str(run/'effective_query_spectra.parquet'), str(target), a.device)
        print('scored', target, flush=True)


if __name__ == '__main__':
    main()
