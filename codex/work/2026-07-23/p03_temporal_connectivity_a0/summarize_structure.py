#!/usr/bin/env python3
"""Summarize paired P03 structure metrics without crossing the query gate."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-seeds", default=3, type=int)
    args = parser.parse_args()

    records = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    by_seed = defaultdict(dict)
    for record in records:
        variant = record["label"].split("_")[0]
        by_seed[int(record["seed"])][variant] = record

    paired = {seed: variants for seed, variants in by_seed.items() if {"static", "time", "shuffle"} <= variants.keys()}
    cell_summaries = []
    for source in range(4):
        for target in range(4):
            if source == target:
                continue
            ratios, absolute_losses = [], []
            for variants in paired.values():
                time = variants["time"]["matrix_source_mass"][source][target]
                shuffled = variants["shuffle"]["matrix_source_mass"][source][target]
                ratios.append(time / shuffled if shuffled else 1.0)
                absolute_losses.append(shuffled - time)
            if ratios:
                cell_summaries.append({
                    "source": source,
                    "target": target,
                    "time_over_shuffle": ratios,
                    "median_ratio": float(np.median(ratios)),
                    "max_ratio": float(np.max(ratios)),
                    "median_absolute_mass_loss": float(np.median(absolute_losses)),
                })

    stable_cells = [
        cell for cell in cell_summaries
        if cell["median_ratio"] <= 0.8
        and cell["max_ratio"] < 0.9
        and cell["median_absolute_mass_loss"] >= 0.005
    ]
    complete = len(paired) >= args.expected_seeds
    if not complete:
        verdict = "SANITY-ONLY" if args.expected_seeds == 1 else "INCOMPLETE"
    elif stable_cells:
        verdict = "GO-P03-QUERY-EFFECT"
    else:
        verdict = "KILL-P03-NO-TEMPORAL-EFFECT"

    summary = {
        "paired_seeds": sorted(paired),
        "expected_seeds": args.expected_seeds,
        "descriptive_structure_gate": {
            "criterion": "cross-cell median TIME/SHUFFLE <=0.8, every seed <0.9, median source-mass loss >=0.005",
            "stable_cells": stable_cells,
        },
        "all_cross_cell_summaries": cell_summaries,
        "verdict": verdict,
        "note": "This gate only decides whether grouped-query measurement is allowed; it is not a paper-level PASS.",
    }
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
