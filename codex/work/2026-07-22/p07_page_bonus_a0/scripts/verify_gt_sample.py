#!/usr/bin/env python3
"""Independently brute-force a few query rows to verify GT/query ordering."""

import argparse
import struct

import numpy as np


def matrix_memmap(path, dtype):
    with open(path, "rb") as f:
        nrows, dim = struct.unpack("<II", f.read(8))
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(nrows, dim))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--qids", type=int, nargs="+", required=True)
    parser.add_argument("--k", type=int, default=100)
    parser.add_argument("--block", type=int, default=100000)
    args = parser.parse_args()

    base = matrix_memmap(args.base, np.float32)
    queries = matrix_memmap(args.queries, np.float32)
    with open(args.gt, "rb") as f:
        gt_n, gt_k = struct.unpack("<II", f.read(8))
    gt_ids = np.memmap(args.gt, dtype=np.uint32, mode="r", offset=8, shape=(gt_n, gt_k))
    if args.k > gt_k:
        raise ValueError("requested verification k exceeds GT width")

    for qid in args.qids:
        candidate_ids = np.empty(0, dtype=np.int64)
        candidate_dists = np.empty(0, dtype=np.float32)
        query = np.asarray(queries[qid])
        for start in range(0, len(base), args.block):
            block = np.asarray(base[start : start + args.block])
            diff = block - query
            dists = np.einsum("ij,ij->i", diff, diff)
            local_k = min(args.k, len(dists))
            local = np.argpartition(dists, local_k - 1)[:local_k]
            candidate_ids = np.concatenate((candidate_ids, local.astype(np.int64) + start))
            candidate_dists = np.concatenate((candidate_dists, dists[local]))
            keep = np.argpartition(candidate_dists, min(args.k, len(candidate_dists)) - 1)[: args.k]
            candidate_ids = candidate_ids[keep]
            candidate_dists = candidate_dists[keep]
        order = np.argsort(candidate_dists, kind="stable")
        exact = candidate_ids[order]
        stored = np.asarray(gt_ids[qid, : args.k], dtype=np.int64)
        set_matches = len(set(exact.tolist()) & set(stored.tolist()))
        print(
            f"qid={qid} top1_exact={exact[0]} top1_gt={stored[0]} "
            f"ordered_id_matches={np.count_nonzero(exact == stored)}/{args.k} "
            f"set_matches={set_matches}/{args.k}"
        )
        # Equal-distance ties may be ordered differently by BLAS vs NumPy;
        # membership is what the P07 analysis consumes.
        if set_matches != args.k or exact[0] != stored[0]:
            raise SystemExit(f"GT verification failed for qid {qid}")


if __name__ == "__main__":
    main()
