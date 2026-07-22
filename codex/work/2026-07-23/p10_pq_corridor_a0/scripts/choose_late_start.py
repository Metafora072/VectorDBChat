#!/usr/bin/env python3
import argparse
import csv
import statistics

parser = argparse.ArgumentParser()
parser.add_argument("metrics")
parser.add_argument("--exact-blocks", type=int, required=True)
args = parser.parse_args()
with open(args.metrics, newline="") as handle:
    hops = [int(row["n_hops"]) for row in csv.DictReader(handle)]
print(max(0, int(statistics.median(hops)) - args.exact_blocks))
