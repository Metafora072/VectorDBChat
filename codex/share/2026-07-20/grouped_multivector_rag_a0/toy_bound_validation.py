#!/usr/bin/env python3
"""Tiny, dependency-free validation for page-level MaxSim bounds."""

import json
import math
import random


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return [x / n for x in a]


def metadata(page):
    d = len(page[0])
    c = [sum(x[j] for x in page) / len(page) for j in range(d)]
    rho = max(norm([x[j] - c[j] for j in range(d)]) for x in page)
    return c, rho


def page_upper(q, meta):
    c, rho = meta
    return min(1.0, dot(q, c) + rho)  # ||q|| = 1, cosine/IP <= 1


def exact_token_score(q, pages):
    return max(dot(q, x) for page in pages for x in page)


def bounds(queries, pages, read_ids):
    metas = [metadata(p) for p in pages]
    lbs = []
    ubs = []
    for q in queries:
        seen = [dot(q, x) for p, page in enumerate(pages) if p in read_ids for x in page]
        lb = max(seen, default=-1.0)
        unread = [page_upper(q, metas[p]) for p in range(len(pages)) if p not in read_ids]
        lbs.append(lb)
        ubs.append(max([lb] + unread))
    return sum(lbs), sum(ubs)


def random_unit(rng, d):
    return unit([rng.gauss(0.0, 1.0) for _ in range(d)])


def clustered_page(rng, center, count, noise):
    return [unit([v + rng.gauss(0.0, noise) for v in center]) for _ in range(count)]


def certify_top1(queries, docs):
    read = [set() for _ in docs]
    reads = 0
    while True:
        bs = [bounds(queries, pages, read[i]) for i, pages in enumerate(docs)]
        leader = max(range(len(docs)), key=lambda i: bs[i][0])
        if bs[leader][0] >= max((bs[i][1] for i in range(len(docs)) if i != leader), default=-math.inf):
            exact_winner = max(
                range(len(docs)),
                key=lambda i: sum(exact_token_score(q, docs[i]) for q in queries),
            )
            return reads, leader == exact_winner
        target = max(range(len(docs)), key=lambda i: bs[i][1] - bs[i][0])
        unread = [p for p in range(len(docs[target])) if p not in read[target]]
        if not unread:
            raise RuntimeError("uncertified despite fully read target")
        metas = [metadata(p) for p in docs[target]]
        page = max(unread, key=lambda p: sum(page_upper(q, metas[p]) for q in queries))
        read[target].add(page)
        reads += 1


def main():
    rng = random.Random(20260720)
    d = 8
    sound_trials = 2_000
    violations = 0
    old_formula_violations = 0
    for _ in range(sound_trials):
        pages = [[random_unit(rng, d) for _ in range(8)] for _ in range(4)]
        queries = [random_unit(rng, d) for _ in range(3)]
        read = {rng.randrange(4)}
        lb, ub = bounds(queries, pages, read)
        exact = sum(exact_token_score(q, pages) for q in queries)
        violations += int(not (lb - 1e-12 <= exact <= ub + 1e-12))

        # Claude draft's LB + max(unread upper) construction, evaluated per token.
        metas = [metadata(p) for p in pages]
        old_ub = 0.0
        for q in queries:
            seen = max(dot(q, x) for p in read for x in pages[p])
            unread = max(page_upper(q, metas[p]) for p in range(4) if p not in read)
            old_ub += seen + unread
        old_formula_violations += int(old_ub + 1e-12 < exact)

    # Explicit signed counterexample to the draft additive upper bound.
    signed_counterexample = {
        "seen_max": -0.8,
        "unread_upper": -0.7,
        "true_max": -0.7,
        "draft_additive_ub": -1.5,
        "correct_max_ub": -0.7,
    }

    queries = [unit([1.0, 0.2] + [0.0] * (d - 2)), unit([0.2, 1.0] + [0.0] * (d - 2))]
    clustered_docs = []
    for doc_id in range(8):
        pages = []
        for page_id in range(8):
            if doc_id == 0 and page_id < 2:
                center = queries[page_id]
            else:
                center = random_unit(rng, d)
            pages.append(clustered_page(rng, center, 16, 0.03))
        clustered_docs.append(pages)
    clustered_reads, clustered_ok = certify_top1(queries, clustered_docs)

    diverse_docs = [
        [[random_unit(rng, d) for _ in range(16)] for _ in range(8)]
        for _ in range(8)
    ]
    diverse_reads, diverse_ok = certify_top1(queries, diverse_docs)

    page_bytes = 4096
    fp16_meta_bytes = 2 * d + 4
    fp32_meta_bytes = 4 * d + 4
    result = {
        "corrected_bound": {"trials": sound_trials, "violations": violations},
        "draft_formula": {
            "random_signed_trials_with_violation": old_formula_violations,
            "explicit_counterexample": signed_counterexample,
        },
        "top1_certificate": {
            "clustered": {
                "pages_read": clustered_reads,
                "total_pages": 64,
                "fraction": clustered_reads / 64,
                "correct": clustered_ok,
            },
            "diverse": {
                "pages_read": diverse_reads,
                "total_pages": 64,
                "fraction": diverse_reads / 64,
                "correct": diverse_ok,
            },
        },
        "metadata_accounting_d8": {
            "page_bytes": page_bytes,
            "centroid_plus_radius_fp16_bytes": fp16_meta_bytes,
            "centroid_plus_radius_fp32_bytes": fp32_meta_bytes,
            "fp16_fraction": fp16_meta_bytes / page_bytes,
            "fp32_fraction": fp32_meta_bytes / page_bytes,
        },
        "metadata_accounting_d128": {
            "page_bytes": page_bytes,
            "centroid_plus_radius_all_fp16_bytes": 2 * 128 + 2,
            "fp16_centroid_fp32_radius_bytes": 2 * 128 + 4,
            "centroid_plus_radius_fp32_bytes": 4 * 128 + 4,
            "all_fp16_fraction": (2 * 128 + 2) / page_bytes,
            "mixed_fraction": (2 * 128 + 4) / page_bytes,
            "fp32_fraction": (4 * 128 + 4) / page_bytes,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
