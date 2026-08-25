from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import run_suite
from .workloads import PRESET_WIDTHS


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic spatial relation benchmarks")
    parser.add_argument("--preset", choices=tuple(PRESET_WIDTHS), default="small")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = run_suite(args.preset)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)


if __name__ == "__main__":
    main()
