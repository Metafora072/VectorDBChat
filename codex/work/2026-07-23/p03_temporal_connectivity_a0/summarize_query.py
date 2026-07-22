#!/usr/bin/env python3
"""Apply the preregistered grouped-query harm gate."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    by_seed = defaultdict(dict)
    for record in records:
        by_seed[int(record["seed"])][record["label"].split("_")[0]] = record
    paired = {seed: variants for seed, variants in by_seed.items() if {"static", "time", "shuffle"} <= variants.keys()}

    groups = []
    passed = []
    for cohort in range(4):
        recall_losses, comparison_ratios, visited_ratios, entry_ratios = [], [], [], []
        for variants in paired.values():
            time = variants["time"]["cohorts"][cohort]
            shuffled = variants["shuffle"]["cohorts"][cohort]
            recall_losses.append(shuffled["recall_at_10"] - time["recall_at_10"])
            comparison_ratios.append(time["comparisons_mean"] / shuffled["comparisons_mean"])
            visited_ratios.append(time["visited_mean"] / shuffled["visited_mean"])
            entry_ratios.append(time["target_entry_expansion_mean"] / shuffled["target_entry_expansion_mean"])
        recall_pass = bool(bool(recall_losses) and np.median(recall_losses) >= 0.01 and min(recall_losses) >= 0.005)
        comparison_pass = bool(bool(comparison_ratios) and np.median(comparison_ratios) >= 1.05 and min(comparison_ratios) >= 1.02)
        visited_pass = bool(bool(visited_ratios) and np.median(visited_ratios) >= 1.05 and min(visited_ratios) >= 1.02)
        summary = {
            "cohort": cohort,
            "recall_losses": recall_losses,
            "comparison_ratios": comparison_ratios,
            "visited_ratios": visited_ratios,
            "target_entry_ratios_descriptive": entry_ratios,
            "recall_pass": recall_pass,
            "comparison_pass": comparison_pass,
            "visited_pass": visited_pass,
        }
        groups.append(summary)
        if recall_pass or comparison_pass or visited_pass:
            passed.append(summary)

    verdict = "GO-P03-ORACLE" if len(paired) == 3 and passed else "HOLD-P03-STRUCTURE-ONLY"
    output = {
        "paired_seeds": sorted(paired),
        "gate": "Recall loss median>=0.01 and every seed>=0.005, or work ratio median>=1.05 and every seed>=1.02",
        "cohorts": groups,
        "passing_cohorts": passed,
        "verdict": verdict,
        "note": "Transition and target-entry differences are descriptive and cannot pass the query-harm gate alone.",
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
