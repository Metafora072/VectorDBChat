# P10 PQ-Corridor Failure A0

## Claim under test

In a disk graph ANN search, in-memory PQ distances may send navigation into a different corridor than full-vector distances. The effect is paper-relevant only if the path difference causes measurable Recall@10 or I/O harm and a small amount of *early* exact-distance steering repairs it more efficiently than late steering or an ordinary larger-search control.

## Fixed setup

- SIFT1M, first 1,000 benchmark queries, exact top-100 ground truth.
- Existing DiskANN graph/SSD layout: `R=64`, build `L=100`, full float vectors on disk.
- Navigation-code validity control: the inherited 128-byte scalar PQ is lossless on integer-valued SIFT (`PQ residual median=P90=0`) and is retained as a zero-error negative control. The hypothesis test uses a 16-byte PQ trained on 10% of SIFT1M, while holding the graph and SSD file byte-identical.
- Search baseline: `L=100`, beam width 2, no node cache, one thread, Recall@10.
- The optional 512 MB full-vector array is an A0 oracle. Every navigation-only full-vector lookup is counted; it is not treated as free.
- Standard DiskANN already uses full vectors for final ranking of expanded nodes. `PQ-NAV` therefore denotes PQ steering plus the stock final exact ranking.

## Variants

1. `PQ-NAV`: stock steering.
2. `EXACT-NAV`: full-vector distance steers every candidate.
3. `EARLY-EXACT(h)`, `h in {1,2,4,8}`: exact steering only during the first `h` beam-expansion blocks.
4. `LATE-EXACT(4)`: exact steering begins four blocks before the median PQ stopping block. Actual exact-read counts are reported because paths have different lengths/degrees.
5. Larger-search controls: `(L,W)=(100,4),(150,4),(200,4)`. The closest control is selected by total bytes touched (`4 KiB * page reads + 512 B * exact-navigation reads`), with latency also reported rather than forced equal.

## Path and outcome measurements

- first expansion divergence;
- expanded-set Jaccard and expansion-bigram Jaccard;
- all-discovered/visited-set Jaccard;
- post-divergence re-entry into the baseline suffix;
- Recall@10, page reads, comparisons, hops, latency, and exact-navigation reads;
- query groups by PQ score residual and exact top-10 margin.

PQ residual is computed after the run from baseline trace scores versus exact squared L2 for the same expanded nodes. It is diagnostic only and is not used online by the method.

## Preregistered A0 gates

`KILL-P10-NO-CONSEQUENCE` if `EXACT-NAV` changes paths but improves aggregate Recall@10 by less than 0.5 percentage point **and** no preregistered residual/margin quartile improves by at least 2 points.

If that gate passes, `EARLY-EXACT` must recover at least 50% of the aggregate exact-navigation gain while using at most 25% of its exact reads. Otherwise the proposed locality is unsupported.

Even then, mark `HOLD-P10-NONUNIQUE` if a late-exact or larger-search control reaches recall within 0.25 point at no greater measured byte cost. A path difference alone is never sufficient.

The consequence and locality thresholds above were frozen before inspecting the 16-byte-PQ results. The initial 128-byte run cannot adjudicate P10 because it contains no quantization error; it is reported rather than discarded.

## Resource budget

CPU-only; one search thread for deterministic paths; about 0.8 GB resident memory in oracle modes; existing 0.8 GB disk index plus 0.5 GB full vectors; expected wall time under 10 minutes for all variants. No training or GPU.
