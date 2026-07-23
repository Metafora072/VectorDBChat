# PQ-RP-128D-A0

## Goal

Characterize the Recall–Performance frontier of ordinary PQ navigation on one byte-identical SIFT1M DiskANN graph. This experiment proposes no new algorithm.

## Fixed controls

- dataset: official SIFT1M, 1,000,000 base vectors, 128 dimensions;
- queries: official 10,000 query vectors; canary uses their first 1,000 rows;
- graph/SSD index: the byte-identical P10 `sift1m_disk.index`;
- `K=10`, `W=4`, no node cache, one search thread, synchronous Linux I/O;
- identical entry point, full-vector final ranking, warm-up source and warm-up count;
- navigation representations: ordinary PQ 8B, 16B and 32B; full-vector `EXACT-NAV` oracle;
- coarse search list: `L={50,100,150,200,300}`.

No selective exact distance, residual refinement, mixed precision, OPQ, RPQ, LVQ, RaBitQ, or mechanism tuning is permitted.

## Ground truth

Use the official 10K×100 SIFT ground-truth IDs. DiskANN's truthset reader also requires distances, so exact squared-L2 distances are computed only for those official `(query,id)` pairs and appended without changing IDs. The first 1K official top-10 sets must agree with the independently brute-forced P07 truthset.

## Canary gate

Run PQ16 and Exact on the first 1K queries for all five L values, twice after the same 200-query warm-up.

Proceed to full only if:

1. PQ16 `L={100,150,200}` Recall@10 reproduces P10's W4 values `{96.51,98.44,99.14}%` within 0.05 percentage point;
2. Exact `L=100` is at least 99.70%, consistent with P10's 99.76% W2 oracle;
3. every run contains 5,000 per-query rows and all required counters;
4. for each mode/L, repeat-to-repeat p50 latency differs by at most 25%; otherwise investigate cache/loading pollution before full.

No full run is allowed if this gate fails.

## Full run

For each of PQ8, PQ16, PQ32 and Exact, execute all five L values in one loaded process. Run three warm-up-controlled repetitions. Recall is taken from repetition 1; all repetitions retain returned IDs, but performance is summarized by the median of repetition-level QPS/p50/p95/p99 and mean counter values.

Only if a 95%–99.5% Recall curve knee lies strictly between coarse L points may one local midpoint be added. No midpoint is run pre-emptively.

## Required metrics

- Recall@10;
- QPS;
- per-query p50/p95/p99 latency;
- CPU_us and IO_us;
- comparisons/query, hops/query and `n_ios/query`;
- SSD bytes/query (`4096*n_ios`);
- navigation DRAM bytes/query (`128*4*n_exact_nav_reads` for Exact, zero for PQ);
- combined touched bytes/query, reported together with its two components;
- process peak RSS from `/usr/bin/time -v`;
- PQ resident bytes from the compressed-code file size;
- full-vector oracle resident bytes;
- query scratch bytes only if a reliable allocation-derived number is available.

## Analysis

Report per-code Pareto frontiers; maximum and residual PQ-to-Exact Recall gap; marginal comparisons/I/O/latency per recovered Recall point; code-resident and total observed DRAM; and the Recall interval with remaining headroom. Do not turn the characterization into a method claim.

