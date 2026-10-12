from __future__ import annotations

import argparse
import json
from pathlib import Path

from casmi26.goal5_baseline import verify_goal4_v3_v4_replication


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify frozen Goal 4 E6 baseline")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(
        json.dumps(
            verify_goal4_v3_v4_replication(args.repository_root),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
