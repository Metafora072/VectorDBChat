#!/usr/bin/env python3
"""CLI for authorized W0 preparation; full measurement is intentionally absent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from w0prep.models import compare_model_canaries, run_model_canary
from w0prep.projection import run_projection
from w0prep.workload import prepare_workload, seal_existing_source_failure


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config" / "w0_preparation.json",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-workload")
    seal_failure = subparsers.add_parser("seal-source-failure")
    seal_failure.add_argument("--source", required=True)
    canary = subparsers.add_parser("model-canary")
    canary.add_argument("--model", choices=("minilm", "nomic"), required=True)
    canary.add_argument("--output", type=Path, required=True)
    compare = subparsers.add_parser("compare-canaries")
    compare.add_argument("--first", type=Path, required=True)
    compare.add_argument("--second", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    projection = subparsers.add_parser("projection")
    projection.add_argument("--output", type=Path, required=True)
    subparsers.add_parser("measurement")
    args = parser.parse_args()

    if args.command == "measurement":
        raise SystemExit(
            "measurement is disabled: GPT has not issued PASS-W0-PRELAUNCH"
        )
    if args.command == "prepare-workload":
        result = prepare_workload(args.config.resolve())
    elif args.command == "seal-source-failure":
        result = seal_existing_source_failure(args.config.resolve(), args.source)
    elif args.command == "model-canary":
        config = json.loads(args.config.read_text(encoding="utf-8"))
        result = run_model_canary(config, args.model, args.output)
    elif args.command == "compare-canaries":
        result = compare_model_canaries(args.first, args.second, args.output)
    else:
        result = run_projection(args.config.resolve(), args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
